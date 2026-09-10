"""Tests for gitutil.py: the five self-checks and base-ref discovery with its validations.

They run against real git subprocesses, with no mocking. Each test builds its own
throwaway temporary repository.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import gitutil as G

PREDICT_REL = "docs/plans/demo/impact-prediction-20260101.md"
CODE_ROOT_REL = "backend"


def _run(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout


def make_repo(tmpdir: Path, mainline: str = "master") -> Path:
    """Build a bare repository to act as origin plus a working repo (with the mainline and feature branches already created).

    Returns the path of the working repo. Callers commit further on the feature branch as needed.
    """
    origin = tmpdir / "origin.git"
    repo = tmpdir / "repo"

    subprocess.run(["git", "init", "--bare", "-b", mainline, str(origin)],
                    check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", mainline, str(repo)],
                    check=True, capture_output=True)
    _run(repo, "config", "user.name", "Test")
    _run(repo, "config", "user.email", "test@example.com")
    _run(repo, "remote", "add", "origin", str(origin))

    (repo / "README.md").write_text("init\n", encoding="utf-8")
    (repo / CODE_ROOT_REL).mkdir(parents=True, exist_ok=True)
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "init")
    _run(repo, "push", "origin", mainline)

    _run(repo, "checkout", "-b", "feature")
    return repo


def commit_predict_file(repo: Path, relpath: str = PREDICT_REL, content: str = "predict\n") -> str:
    """Commit the prediction file on its own on the feature branch (prediction only, simulating the kickoff commit P). Returns that commit's sha."""
    full = repo / relpath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _run(repo, "add", relpath)
    _run(repo, "commit", "-m", "kickoff: impact prediction")
    return _run(repo, "rev-parse", "HEAD").strip()


def commit_py_change(repo: Path, relpath: str, content: str, message: str = "impl") -> str:
    full = repo / relpath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _run(repo, "add", relpath)
    _run(repo, "commit", "-m", message)
    return _run(repo, "rev-parse", "HEAD").strip()


class TestGitWrapper(unittest.TestCase):
    def test_success_returns_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            out = G.git(repo, "rev-parse", "HEAD")
            self.assertEqual(len(out.strip()), 40)

    def test_failure_raises_selfcheckerror(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            with self.assertRaises(G.SelfCheckError):
                G.git(repo, "rev-parse", "not-a-real-ref")

    def test_check_false_swallows_failure(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            # With check=False a failing command does not raise; stdout is returned as
            # is (which is not guaranteed to be empty)
            try:
                G.git(repo, "rev-parse", "not-a-real-ref", check=False)
            except G.SelfCheckError:
                self.fail("check=False must not raise SelfCheckError")


class TestIsAncestor(unittest.TestCase):
    """Telling "definitely not an ancestor" (exit code 1) apart from "git failed" (any other exit code)."""

    def test_exit_code_0_is_ancestor(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            self.assertTrue(G.is_ancestor(repo, base, "HEAD"))

    def test_exit_code_1_not_ancestor(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            # HEAD is newer than base, so the other direction (HEAD being an ancestor of
            # base) does not hold — definitely not an ancestor, not an error
            self.assertFalse(G.is_ancestor(repo, "HEAD", base))

    def test_exit_code_ge_2_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            with self.assertRaises(G.SelfCheckError):
                G.is_ancestor(repo, "no-such-ref-xyz", "HEAD")


class TestFetchOrigin(unittest.TestCase):
    def test_fetch_succeeds_against_real_origin(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            G.fetch_origin(repo)  # passing means not raising

    def test_fetch_failure_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            G.git(repo, "remote", "set-url", "origin", "/no/such/path")
            with self.assertRaises(G.SelfCheckError):
                G.fetch_origin(repo)


class TestFindBase(unittest.TestCase):
    def test_normal_p_then_i_returns_p_sha(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            p_sha = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            base, warnings = G.find_base(repo, PREDICT_REL)
            self.assertEqual(base, p_sha)
            self.assertEqual(warnings, [])

    def test_empty_candidates_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            with self.assertRaises(G.SelfCheckError):
                G.find_base(repo, PREDICT_REL)

    def test_multiple_candidates_takes_earliest_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            first_sha = commit_predict_file(repo)
            # Deleted and then added back: the second add produces a second
            # --diff-filter=A candidate
            _run(repo, "rm", PREDICT_REL)
            _run(repo, "commit", "-m", "delete the prediction file by mistake")
            commit_predict_file(repo, content="predict v2\n")
            base, warnings = G.find_base(repo, PREDICT_REL)
            self.assertEqual(base, first_sha)
            self.assertEqual(len(warnings), 1)
            self.assertIn("2", warnings[0])


class TestSelfChecks(unittest.TestCase):
    def test_check1_uncommitted_changes_under_code_root_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "unused"
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            (repo / CODE_ROOT_REL / "dirty.py").write_text("x = 1\n", encoding="utf-8")
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, base, CODE_ROOT_REL)

    def test_check2_base_not_ancestor_of_head_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            # Simulate base no longer being in the current history after a rebase: forge
            # an unrelated sha
            fake_base = _run(repo, "rev-parse", "HEAD").strip()
            # Move HEAD back one commit so that fake_base (the current HEAD) is no longer
            # an ancestor of the new HEAD
            _run(repo, "reset", "--hard", "HEAD^")
            commit_py_change(repo, f"{CODE_ROOT_REL}/other.py", "def b():\n    return 2\n")
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, fake_base, CODE_ROOT_REL)

    def test_check3_base_on_origin_master_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            # Reused-directory scenario: the prediction file was already committed on
            # master (left over from the previous cycle)
            (repo / PREDICT_REL).parent.mkdir(parents=True, exist_ok=True)
            (repo / PREDICT_REL).write_text("prediction from an earlier cycle\n", encoding="utf-8")
            _run(repo, "checkout", "master")
            _run(repo, "add", PREDICT_REL)
            _run(repo, "commit", "-m", "kickoff commit of the previous cycle")
            base_on_master = _run(repo, "rev-parse", "HEAD").strip()
            _run(repo, "push", "origin", "master")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "master", "--no-edit")
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, base_on_master, CODE_ROOT_REL)

    def test_check5_running_on_master_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "master")
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, base, CODE_ROOT_REL)

    def test_check5_on_mainline_with_tag_named_like_it_still_raises(self):
        """A tag named like the mainline makes `rev-parse --abbrev-ref HEAD` print
        `heads/master`; self-check 5 must still fire, so it compares the full symbolic ref."""
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "master")
            _run(repo, "tag", "master", "HEAD")  # a tag that shadows the short branch name
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            with self.assertRaises(G.SelfCheckError) as cm:
                G.run_self_checks(repo, base, CODE_ROOT_REL)
            self.assertIn("self-check 5", str(cm.exception))
            self.assertIn("'master'", str(cm.exception))  # the short name is what is shown

    def test_check5_on_feature_with_tag_named_like_it_passes(self):
        """The mirror image: a tag named like the feature branch must not turn a legal
        feature branch into a self-check 5 failure."""
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "tag", "feature", "HEAD")
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            G.run_self_checks(repo, base, CODE_ROOT_REL)  # passing means not raising

    def test_check5_detached_head_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            head_sha = _run(repo, "rev-parse", "HEAD").strip()
            _run(repo, "checkout", head_sha)  # detached HEAD: not on any branch
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, base, CODE_ROOT_REL)

    def test_check4_merge_with_non_first_parent_not_on_master_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            # Branch a side branch off feature; the side branch never went through
            # origin/master
            _run(repo, "checkout", "-b", "side")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 9\n")
            _run(repo, "checkout", "feature")
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            _run(repo, "merge", "side", "--no-edit")
            with self.assertRaises(G.SelfCheckError):
                G.run_self_checks(repo, base, CODE_ROOT_REL)

    def test_all_five_pass_on_well_formed_feature_branch(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            G.run_self_checks(repo, base, CODE_ROOT_REL)  # passing means not raising


class TestMergeBase(unittest.TestCase):
    def test_no_common_history_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "--orphan", "orphan")
            _run(repo, "commit", "--allow-empty", "-m", "orphan root")
            with self.assertRaises(G.SelfCheckError):
                G.merge_base(repo, "orphan", "master")

    def test_common_history_returns_sha(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            mb = G.merge_base(repo, "feature", "master")
            self.assertEqual(len(mb), 40)


class TestChangedPyFiles(unittest.TestCase):
    def test_rename_gives_both_old_and_new_paths(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            a = commit_py_change(repo, f"{CODE_ROOT_REL}/old.py", "def f():\n    return 1\n")
            _run(repo, "mv", f"{CODE_ROOT_REL}/old.py", f"{CODE_ROOT_REL}/new.py")
            _run(repo, "commit", "-m", "rename")
            b = _run(repo, "rev-parse", "HEAD").strip()
            files = G.changed_py_files(repo, a, b, CODE_ROOT_REL)
            self.assertIn(f"{CODE_ROOT_REL}/old.py", files)
            self.assertIn(f"{CODE_ROOT_REL}/new.py", files)

    def test_only_py_files_under_code_root_included(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            a = _run(repo, "rev-parse", "HEAD").strip()
            (repo / CODE_ROOT_REL / "mod.py").write_text("x = 1\n", encoding="utf-8")
            (repo / CODE_ROOT_REL / "notes.txt").write_text("n\n", encoding="utf-8")
            (repo / "outside.py").write_text("y = 2\n", encoding="utf-8")
            _run(repo, "add", ".")
            _run(repo, "commit", "-m", "mixed changes")
            b = _run(repo, "rev-parse", "HEAD").strip()
            files = G.changed_py_files(repo, a, b, CODE_ROOT_REL)
            self.assertEqual(files, [f"{CODE_ROOT_REL}/mod.py"])


class TestFileAt(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            sha = _run(repo, "rev-parse", "HEAD").strip()
            self.assertIsNone(G.file_at(repo, sha, f"{CODE_ROOT_REL}/nope.py"))

    def test_existing_file_returns_content(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            sha = commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            content = G.file_at(repo, sha, f"{CODE_ROOT_REL}/mod.py")
            self.assertEqual(content, "def a():\n    return 1\n")


class TestParents(unittest.TestCase):
    def test_non_merge_commit_has_one_parent(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            sha = commit_predict_file(repo)
            ps = G.parents(repo, sha)
            self.assertEqual(len(ps), 1)

    def test_merge_commit_has_multiple_parents(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            _run(repo, "checkout", "-b", "side")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 9\n")
            _run(repo, "checkout", "feature")
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            _run(repo, "merge", "side", "--no-edit")
            merge_sha = _run(repo, "rev-parse", "HEAD").strip()
            ps = G.parents(repo, merge_sha)
            self.assertEqual(len(ps), 2)


class TestValidateBase(unittest.TestCase):
    def test_clean_history_no_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertEqual(warnings, [])

    def test_base_commit_itself_changes_py_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            full_predict = repo / PREDICT_REL
            full_predict.parent.mkdir(parents=True, exist_ok=True)
            full_predict.write_text("predict\n", encoding="utf-8")
            (repo / CODE_ROOT_REL / "sneaky.py").write_text("x = 1\n", encoding="utf-8")
            _run(repo, "add", ".")
            _run(repo, "commit", "-m", "kickoff commit smuggling in a code change")
            base = _run(repo, "rev-parse", "HEAD").strip()
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertTrue(any("itself changed" in w for w in warnings), warnings)

    def test_prior_commit_changed_py_before_base_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            # Acting first and asking later: before the prediction file was committed the
            # feature branch already carries a commit that changes a .py
            commit_py_change(repo, f"{CODE_ROOT_REL}/early.py", "def e():\n    return 0\n",
                              "code committed early by mistake")
            base = commit_predict_file(repo)
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertTrue(any("a commit that changed .py" in w for w in warnings), warnings)

    def test_merge_before_base_judged_by_two_branch_criteria(self):
        """Whether a merge commit "changed a .py" is not a placeholder warning that
        merely records the merge without judging it: the two-parent rule is really run.
        Two merges are planted before base here — a clean one (side1.py comes whole from
        the side1 branch and was never hand-edited) and an evil one (side2.py was
        hand-edited from 1 to 999, which the first branch of the rule must hit) — and
        each is asserted through its own sha rather than by only asking whether there is
        any warning at all: "is there a warning" cannot separate "the rule ran and the
        result was empty" from "the rule never ran", and only asserting on both shas
        proves the rule reached different conclusions for the two cases.
        """
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))

            # The clean one: side1.py is merged in as is and must not be judged invalid
            _run(repo, "checkout", "-b", "side1")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side1.py", "def s():\n    return 9\n")
            _run(repo, "checkout", "feature")
            (repo / "NOTES1.md").write_text("placeholder commit 1 on the feature side\n", encoding="utf-8")
            _run(repo, "add", "NOTES1.md")
            _run(repo, "commit", "-m", "placeholder commit 1 on the feature side")
            _run(repo, "merge", "side1", "--no-edit")
            clean_merge = _run(repo, "rev-parse", "HEAD").strip()

            # The evil one: after the merge side2.py is hand-edited from 1 to 999, which
            # neither parent matches
            _run(repo, "checkout", "-b", "side2")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side2.py", "def e():\n    return 1\n")
            _run(repo, "checkout", "feature")
            (repo / "NOTES2.md").write_text("placeholder commit 2 on the feature side\n", encoding="utf-8")
            _run(repo, "add", "NOTES2.md")
            _run(repo, "commit", "-m", "placeholder commit 2 on the feature side")
            _run(repo, "merge", "side2", "--no-edit")
            (repo / CODE_ROOT_REL / "side2.py").write_text("def e():\n    return 999\n", encoding="utf-8")
            _run(repo, "add", f"{CODE_ROOT_REL}/side2.py")
            _run(repo, "commit", "--amend", "--no-edit")
            evil_merge = _run(repo, "rev-parse", "HEAD").strip()

            base = commit_predict_file(repo)
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)

            # Direction 1: the evil merge is judged invalid — both the key substring and
            # its own sha must show up
            self.assertTrue(
                any("merge commit that changed .py" in w and evil_merge[:9] in w for w in warnings),
                warnings,
            )
            # Direction 2: the clean merge is not dragged in — its sha appears in no warning
            self.assertFalse(any(clean_merge[:9] in w for w in warnings), warnings)

    def test_stacked_branch_topology_is_caught_by_check3(self):
        """The "no stacked branches" rule has no detection function of its own — this
        test proves it is caught indirectly by validation 3:

        when a feature branch is cut from another feature branch that carries .py changes
        not yet merged into master, the lower bound = merge-base(base, origin/master)
        lands on the real fork point on master, so enumerating lower_bound..base^ is bound
        to reach those .py commits on the branch that was stacked upon.
        """
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            # "feature" is branch A: commit a .py change on it that is not merged into master
            commit_py_change(repo, f"{CODE_ROOT_REL}/on_branch_a.py", "def a():\n    return 1\n",
                              "code change on branch A (not merged into master)")
            # Cut the stacked branch B off A and commit the prediction file on B as the base
            _run(repo, "checkout", "-b", "stacked-b")
            base = commit_predict_file(repo)
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertTrue(any("a commit that changed .py" in w for w in warnings), warnings)


class TestCommitsAndMerges(unittest.TestCase):
    def test_commits_no_merges_excludes_merge_commit(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            _run(repo, "checkout", "-b", "side")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 9\n")
            _run(repo, "checkout", "feature")
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def a():\n    return 1\n")
            _run(repo, "merge", "side", "--no-edit")
            merge_sha = _run(repo, "rev-parse", "HEAD").strip()
            no_merges = G.commits_no_merges(repo, base)
            self.assertNotIn(merge_sha, no_merges)
            merges = G.merge_commits(repo, base)
            self.assertEqual(merges, [merge_sha])


class TestMainline(unittest.TestCase):
    def _pair(self, tmp: Path, head: str, branch: str | None = None) -> Path:
        """bare origin whose HEAD -> refs/heads/<head>; work repo with one commit pushed to <branch or head>."""
        origin = tmp / "origin.git"
        repo = tmp / "repo"
        subprocess.run(["git", "init", "--bare", "-b", head, str(origin)], check=True, capture_output=True)
        b = branch or head
        subprocess.run(["git", "init", "-b", b, str(repo)], check=True, capture_output=True)
        _run(repo, "config", "user.name", "T")
        _run(repo, "config", "user.email", "t@example.com")
        _run(repo, "remote", "add", "origin", str(origin))
        (repo / "f").write_text("x\n", encoding="utf-8")
        _run(repo, "add", ".")
        _run(repo, "commit", "-m", "init")
        _run(repo, "push", "origin", b)
        return repo

    def test_main(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            self.assertEqual(G.mainline(repo), G.Mainline("main", "refs/remotes/origin/main"))

    def test_master(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "master")
            self.assertEqual(G.mainline(repo).name, "master")

    def test_nested_name(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "release/1.0")
            self.assertEqual(G.mainline(repo).full_ref, "refs/remotes/origin/release/1.0")

    def test_unborn_remote_head_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            subprocess.run(["git", "--git-dir", str(Path(d) / "origin.git"), "symbolic-ref", "HEAD", "refs/heads/unborn"], check=True)
            with self.assertRaises(G.SelfCheckError) as cm:
                G.mainline(repo)
            self.assertIn("default branch", str(cm.exception))

    def test_remote_head_to_tag_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            _run(repo, "tag", "v1")
            _run(repo, "push", "origin", "v1")
            subprocess.run(["git", "--git-dir", str(Path(d) / "origin.git"), "symbolic-ref", "HEAD", "refs/tags/v1"], check=True)
            with self.assertRaises(G.SelfCheckError):
                G.mainline(repo)

    def test_unreachable_remote_raises(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            _run(repo, "remote", "set-url", "origin", "/no/such/path")
            with self.assertRaises(G.SelfCheckError):
                G.mainline(repo)

    def test_nested_dir_named_origin_is_not_a_remote(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            _run(repo, "remote", "remove", "origin")
            subprocess.run(["git", "clone", "-q", str(Path(d) / "origin.git"), str(repo / "origin")], check=True)
            with self.assertRaises(G.SelfCheckError) as cm:
                G.mainline(repo)
            self.assertIn("no remote named 'origin'", str(cm.exception))

    def test_fetch_updates_stale_ref_under_narrow_refspec(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            _run(repo, "config", "remote.origin.fetch", "+refs/heads/feat:refs/remotes/origin/feat")
            other = Path(d) / "other"
            subprocess.run(["git", "clone", "-q", str(Path(d) / "origin.git"), str(other)], check=True)
            _run(other, "config", "user.name", "T"); _run(other, "config", "user.email", "t@example.com")
            (other / "g").write_text("y\n", encoding="utf-8")
            _run(other, "add", "."); _run(other, "commit", "-m", "adv"); _run(other, "push", "origin", "main")
            m = G.mainline(repo)
            G.fetch_origin(repo, m)
            local = _run(repo, "rev-parse", m.full_ref).strip()
            remote = _run(repo, "ls-remote", "origin", "refs/heads/main").split()[0]
            self.assertEqual(local, remote)

    def test_full_ref_immune_to_tag_named_origin_main(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self._pair(Path(d), "main")
            _run(repo, "checkout", "-b", "feat")
            (repo / "h").write_text("z\n", encoding="utf-8")
            _run(repo, "add", "."); _run(repo, "commit", "-m", "feat")
            _run(repo, "tag", "origin/main", "HEAD")
            m = G.mainline(repo)
            self.assertEqual(_run(repo, "rev-parse", m.full_ref).strip(), _run(repo, "rev-parse", "main").strip())


if __name__ == "__main__":
    unittest.main()
