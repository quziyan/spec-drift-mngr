"""Tests for the two-parent rule that cmd_changed applies to merge commits.

They run against real git subprocesses, with no mocking, and reuse the temporary
repository scaffolding from test_gitutil. Every scenario sets up the four-state
structure relative to the merge base: base / the feature parent / the master parent / M.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cmd_changed as CH
import gitutil as G
from tests.test_gitutil import (
    CODE_ROOT_REL,
    _run,
    commit_predict_file,
    commit_py_change,
    make_repo,
)
from tests.test_changed_nonmerge import _run_changed


def _amend_current_file(repo: Path, relpath: str, content: str) -> str:
    """Rewrite a file in place on the commit just made (usually a merge) and amend it,
    simulating a hand edit made while merging (what really produces an evil merge:
    a slip while resolving conflicts, or a deliberate change).
    The original parents are kept; only the tree is replaced.
    """
    full = repo / relpath
    full.write_text(content, encoding="utf-8")
    _run(repo, "add", relpath)
    _run(repo, "commit", "--amend", "--no-edit")
    return _run(repo, "rev-parse", "HEAD").strip()


def _touch(repo: Path, relpath: str, content: str, message: str) -> str:
    """Commit a placeholder change unrelated to any .py under code_root, used only to produce a real fork."""
    full = repo / relpath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _run(repo, "add", relpath)
    _run(repo, "commit", "-m", message)
    return _run(repo, "rev-parse", "HEAD").strip()


class TestEvilMergeFirstBranch(unittest.TestCase):
    """Live-fire case for the first branch, reproducing a real evil merge:
    base does not have the constant / the feature parent has 15 / the master parent does
    not have it / M has 32 -> it must enter the set.
    """

    def test_hand_edited_merge_value_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)  # base: config.py does not exist yet
            commit_py_change(
                repo, f"{CODE_ROOT_REL}/config.py", "MAX_EVIDENCES = 15\n",
                "feature parent: add the constant = 15",
            )
            # The master parent: add one unrelated placeholder commit to produce a real
            # fork — otherwise master is behind feature, `merge master` is a no-op and
            # there is no genuine two-parent merge to work with.
            # master never touches config.py, so that symbol does not exist at all on the
            # master side.
            _run(repo, "checkout", "master")
            _touch(repo, "MASTER_NOTES.md", "placeholder on the master side\n", "placeholder commit on the master side")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "master", "--no-edit")
            # M: hand-edit the value to 32 (what produces an evil merge)
            _amend_current_file(
                repo, f"{CODE_ROOT_REL}/config.py", "MAX_EVIDENCES = 32\n",
            )
            result = CH.merge_symbols(repo, base, CODE_ROOT_REL)
            self.assertIn("config.py::MAX_EVIDENCES", result)


class TestCleanMergeDoesNotFlag(unittest.TestCase):
    """A normal merge does not enter the set: the feature parent changed the function, the master parent did not touch it, and M has the same fingerprint as the feature parent."""

    def test_clean_merge_matching_feature_parent_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def f():\n    return 1\n",
                              "baseline: add f")
            _run(repo, "checkout", "master")
            _run(repo, "merge", "feature", "--no-edit")  # fast-forward: bring the baseline onto master too
            _run(repo, "checkout", "feature")
            # The feature parent: change f
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def f():\n    return 2\n",
                              "feature parent: change f")
            # The master parent: add an unrelated commit to produce a real fork, leaving f at its baseline value
            _run(repo, "checkout", "master")
            _touch(repo, "MASTER_NOTES.md", "placeholder on the master side\n", "placeholder commit on the master side")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "master", "--no-edit")  # M: no conflict, so the feature parent's f=2 is taken naturally
            result = CH.merge_symbols(repo, base, CODE_ROOT_REL)
            self.assertNotIn("mod.py::f", result)


class TestSelfDeletionNotFlagged(unittest.TestCase):
    """The shape where base has g / the feature parent does not (it deleted g itself) /
    the master parent has it / M does not -> it does not enter the set. This is the line
    where an "any parent" rule would produce a false positive and an "all parents" rule
    does not.
    """

    def test_feature_self_delete_survives_clean_merge_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def g():\n    return 9\n",
                              "baseline: add g")
            _run(repo, "checkout", "master")
            _run(repo, "merge", "feature", "--no-edit")  # fast-forward, so master has g too
            _run(repo, "checkout", "feature")
            # The feature parent: delete g itself
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "X = 1\n",
                              "feature parent: delete g")
            # The master parent: an unrelated placeholder commit, g kept as is
            _run(repo, "checkout", "master")
            _touch(repo, "MASTER_NOTES.md", "placeholder on the master side\n", "placeholder commit on the master side")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "master", "--no-edit")  # M: no conflict, so the feature parent's deletion is taken
            result = CH.merge_symbols(repo, base, CODE_ROOT_REL)
            self.assertNotIn("mod.py::g", result)


class TestRealDeletionByMergeIsFlagged(unittest.TestCase):
    """A real deletion enters the set: every parent has g and M (hand-edited) does not."""

    def test_all_parents_have_symbol_merge_removes_it(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", "def g():\n    return 9\n",
                              "baseline: add g")
            _run(repo, "checkout", "master")
            _run(repo, "merge", "feature", "--no-edit")  # fast-forward, so master has g too
            _run(repo, "checkout", "feature")
            _touch(repo, "FEATURE_NOTES.md", "placeholder on the feature side\n", "placeholder commit on the feature side")
            _run(repo, "checkout", "master")
            _touch(repo, "MASTER_NOTES.md", "placeholder on the master side\n", "placeholder commit on the master side")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "master", "--no-edit")  # M: neither side touched mod.py, so g is naturally still there
            _amend_current_file(repo, f"{CODE_ROOT_REL}/mod.py", "X = 1\n")  # hand-delete g
            result = CH.merge_symbols(repo, base, CODE_ROOT_REL)
            self.assertIn("mod.py::g", result)


class TestOctopusMerge(unittest.TestCase):
    """A merge with more than two parents: the rule still holds for N parents.

    The shared baseline shared.py contains h + gg, and three branches each commit
    independently (A changes h, B and C add unrelated marker files to force a genuine
    multi-parent commit), then an octopus merge gives 4 parents. Afterwards h is
    hand-edited to a value none of the four parents has and gg is deleted entirely,
    verifying that both branches of the rule take effect correctly across all N parents.
    """

    def test_first_and_second_branch_hold_across_four_parents(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            commit_py_change(
                repo, f"{CODE_ROOT_REL}/shared.py",
                "def h():\n    return 0\n\n\ndef gg():\n    return 5\n",
                "shared baseline: h + gg",
            )
            # All three branches are cut from here; feature itself also needs an unrelated
            # diverging commit — otherwise git would simply fast-forward feature when the
            # first branch is merged and there would be no way to reach 4 parents.
            _run(repo, "branch", "branchA")
            _run(repo, "branch", "branchB")
            _run(repo, "branch", "branchC")
            _touch(repo, f"{CODE_ROOT_REL}/feature_marker.py", "MARKER_F = 1\n",
                   "feature: add a marker file (to produce a real divergence)")
            _run(repo, "checkout", "branchA")
            commit_py_change(
                repo, f"{CODE_ROOT_REL}/shared.py",
                "def h():\n    return 1\n\n\ndef gg():\n    return 5\n",
                "A: change h",
            )
            _run(repo, "checkout", "branchB")
            _touch(repo, f"{CODE_ROOT_REL}/b_marker.py", "MARKER_B = 1\n", "B: add a marker file")
            _run(repo, "checkout", "branchC")
            _touch(repo, f"{CODE_ROOT_REL}/c_marker.py", "MARKER_C = 1\n", "C: add a marker file")
            _run(repo, "checkout", "feature")
            _run(repo, "merge", "branchA", "branchB", "branchC", "--no-edit")  # octopus
            merge_sha = _run(repo, "rev-parse", "HEAD").strip()
            self.assertEqual(len(G.parents(repo, merge_sha)), 4)

            # Hand edit: h is changed to a value none of the four parents has; gg is deleted entirely
            _amend_current_file(
                repo, f"{CODE_ROOT_REL}/shared.py", "def h():\n    return 99\n",
            )
            result = CH.merge_symbols(repo, base, CODE_ROOT_REL)
            self.assertIn("shared.py::h", result)   # first branch: no parent (N=4) matches 99
            self.assertIn("shared.py::gg", result)  # second branch: all 4 parents have gg, M does not
            # Cleanly merged marker symbols must not be reported by mistake
            self.assertNotIn("b_marker.py::MARKER_B", result)
            self.assertNotIn("c_marker.py::MARKER_C", result)


class TestValidateBaseMergeBranchJudged(unittest.TestCase):
    """The acceptance point for judging merges: a merge commit that "changed a .py"
    exists before base -> validation 3 judges the cycle invalid.

    An evil merge is planted before base the same way as in the live-fire case for the
    first branch: a side branch introduces side.py::s=1, and the merge is hand-edited to
    999 (a value neither parent matches).
    """

    def test_evil_merge_before_base_fails_check3(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "-b", "side")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 1\n",
                              "side branch: add s")
            _run(repo, "checkout", "feature")
            _touch(repo, "NOTES.md", "placeholder commit on feature, to produce a real fork\n", "placeholder commit on feature")
            _run(repo, "merge", "side", "--no-edit")  # M: parents=[feature (no side.py), side (s=1)]
            _amend_current_file(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 999\n")
            base = commit_predict_file(repo)  # base^ is exactly this hand-edited merge
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertTrue(any("merge commit that changed .py" in w for w in warnings), warnings)

    def test_clean_merge_before_base_still_passes_check3(self):
        """The control group: there is a merge before base as well, but it was not
        hand-edited — neither branch of the rule hits, so it must not be judged invalid
        (which avoids over-tightening into "any merge in range makes the cycle invalid").
        """
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "-b", "side")
            commit_py_change(repo, f"{CODE_ROOT_REL}/side.py", "def s():\n    return 1\n",
                              "side branch: add s")
            _run(repo, "checkout", "feature")
            _touch(repo, "NOTES.md", "placeholder commit on feature, to produce a real fork\n", "placeholder commit on feature")
            _run(repo, "merge", "side", "--no-edit")  # a clean merge, not hand-edited
            base = commit_predict_file(repo)
            warnings = G.validate_base(repo, base, CODE_ROOT_REL)
            self.assertFalse(any("that changed .py" in w for w in warnings), warnings)


class TestRunMergesIntoActualSet(unittest.TestCase):
    """The acceptance point for the output: the earlier "not yet recognized" notice is
    gone, and a symbol introduced by a merge really shows up in the actual changed symbol
    set.
    """

    def test_merge_introduced_symbol_appears_and_old_warning_is_gone(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "master")
            commit_py_change(repo, f"{CODE_ROOT_REL}/config.py", "CONST = 15\n",
                              "master: add CONST=15")
            _run(repo, "push", "origin", "master")
            _run(repo, "checkout", "feature")
            commit_predict_file(repo)
            _run(repo, "merge", "master", "--no-edit")  # self-check 4: the non-first parent must be an ancestor of origin/master
            _amend_current_file(repo, f"{CODE_ROOT_REL}/config.py", "CONST = 999\n")
            code, out = _run_changed(repo)
            self.assertEqual(code, 0, out)
            self.assertIn("config.py::CONST", out)
            self.assertNotIn("not yet recognized", out)
            self.assertNotIn("handled later", out)


if __name__ == "__main__":
    unittest.main()
