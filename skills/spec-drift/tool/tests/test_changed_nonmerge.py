"""Tests for the non-merge branch of cmd_changed.

They run against real git subprocesses, with no mocking, and reuse the temporary
repository scaffolding from test_gitutil. Each scenario narrows the enumeration window
of `changed` down to exactly one step, by taking the shas of two adjacent commits as
base and HEAD, so that the assertions are precise and not polluted by unrelated
intermediate commits.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_changed as CH
import repo as R
from tests.test_gitutil import (
    CODE_ROOT_REL,
    PREDICT_REL,
    _run,
    commit_predict_file,
    commit_py_change,
    make_repo,
)


def _mod(repo: Path, content: str, message: str = "impl") -> str:
    return commit_py_change(repo, f"{CODE_ROOT_REL}/mod.py", content, message)


class TestChangeFunctionBody(unittest.TestCase):
    def test_body_change_hits_the_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "def f():\n    return 1\n")
            _mod(repo, "def f():\n    return 2\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertEqual(actual, {"mod.py::f"})


class TestAddFunction(unittest.TestCase):
    def test_new_function_and_module_both_hit(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "def f():\n    return 1\n")
            _mod(repo, "def f():\n    return 1\n\n\ndef g():\n    return 2\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertEqual(actual, {"mod.py::g", "mod.py::<module>"})


class TestDeleteFunction(unittest.TestCase):
    def test_deleted_function_hits(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "def f():\n    return 1\n\n\ndef g():\n    return 2\n")
            _mod(repo, "def f():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertIn("mod.py::g", actual)


class TestSwapTwoFunctions(unittest.TestCase):
    def test_swap_reports_both_symbols_via_positional_diff(self):
        """The acceptance point of the positional comparison: swapping two adjacent functions would be reported as one symbol by a longest-increasing-subsequence reading, and both are required here."""
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "def f():\n    return 1\n\n\ndef g():\n    return 2\n")
            _mod(repo, "def g():\n    return 2\n\n\ndef f():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertEqual(actual, {"mod.py::f", "mod.py::g"})


class TestImportMovesAcrossFunctions(unittest.TestCase):
    def test_import_reposition_hits_module_only(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(
                repo,
                "import os\n\n\ndef f():\n    return 1\n\n\ndef g():\n    return 2\n",
            )
            _mod(
                repo,
                "\n\ndef f():\n    return 1\n\n\nimport os\n\n\ndef g():\n    return 2\n",
            )
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertEqual(actual, {"mod.py::<module>"})


class TestRenameWithNoRenames(unittest.TestCase):
    def test_rename_hits_both_old_and_new_path_symbols(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            c1 = commit_predict_file(repo)
            commit_py_change(repo, f"{CODE_ROOT_REL}/old.py", "def f():\n    return 1\n")
            _run(repo, "mv", f"{CODE_ROOT_REL}/old.py", f"{CODE_ROOT_REL}/new.py")
            (repo / CODE_ROOT_REL / "new.py").write_text("def f():\n    return 2\n", encoding="utf-8")
            _run(repo, "add", CODE_ROOT_REL)
            _run(repo, "commit", "-m", "rename + edit")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertIn("old.py::f", actual)
            self.assertIn("new.py::f", actual)


class TestBrandNewFile(unittest.TestCase):
    def test_new_file_does_not_trigger_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            c1 = commit_predict_file(repo)
            _mod(repo, "def h():\n    return 1\n", "add brand new file")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)  # passing means not raising
            self.assertIn("mod.py::h", actual)


class TestSyntaxErrorFailsClosed(unittest.TestCase):
    def test_mid_chain_syntax_error_raises_and_names_commit_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            base = commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n", "valid")
            _mod(repo, "def f(:\n    return 1\n", "broken syntax")
            _mod(repo, "def f():\n    return 2\n", "fixed later")
            # Naming the file is the acceptance point: wherever the parse failure happens
            # (reading the broken revision as the after side or as the before side), the
            # error message must let you pin down which file failed to parse.
            with self.assertRaises(CH.ParseFailed) as cm:
                CH.nonmerge_symbols(repo, base, CODE_ROOT_REL)
            self.assertIn("mod.py", str(cm.exception))


class TestCommentOnlyChange(unittest.TestCase):
    def test_comment_wording_change_hits_the_symbol(self):
        """An accepted cost: changing only the wording of a comment also enters the set."""
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "X = 1\n\n# old comment\ndef f():\n    return 1\n")
            _mod(repo, "X = 1\n\n# new comment\ndef f():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertEqual(actual, {"mod.py::f"})


class TestBlankLineInsertedBetweenCommentAndDef(unittest.TestCase):
    def test_blank_line_breaks_absorption_and_hits_the_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            c1 = _mod(repo, "X = 1\n\n# comment\ndef f():\n    return 1\n")
            _mod(repo, "X = 1\n\n# comment\n\ndef f():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo, c1, CODE_ROOT_REL)
            self.assertIn("mod.py::f", actual)


def _ctx(repo: Path) -> R.Ctx:
    """cmd_changed.run only ever uses repo_root / code_root, so the remaining fields can be dummies."""
    return R.Ctx(
        repo, repo / CODE_ROOT_REL, repo / "unused-ledger.md", repo / "unused-lock.json",
        "Alice", "Bot",
    )


def _run_changed(repo: Path, predict_relpath: str = PREDICT_REL) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = CH.run(_ctx(repo), predict_relpath)
    return code, buf.getvalue()


class TestRunHappyPath(unittest.TestCase):
    def test_prints_actual_symbols_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n")
            code, out = _run_changed(repo)
            self.assertEqual(code, 0, out)
            self.assertIn("mod.py::f", out)
            self.assertIn("mod.py::<module>", out)


class TestRunOnMainMainline(unittest.TestCase):
    def test_run_on_main_mainline(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), mainline="main")
            commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n")
            code, out = _run_changed(repo)
            self.assertEqual(code, 0, out)
            self.assertIn("Actual changed symbol set", out)


class TestRunSelfCheckFailure(unittest.TestCase):
    def test_running_on_master_is_nonzero_and_prints_error(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            _run(repo, "checkout", "master")
            commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n")
            code, out = _run_changed(repo)
            self.assertNotEqual(code, 0)
            self.assertIn("❌", out)


class TestRunMergeWarning(unittest.TestCase):
    """The earlier placeholder notice, which said merge commits were not yet recognized
    by this command and would be handled later, is gone: the result of the two-parent
    rule for merges is genuinely folded into the actual changed symbol set. With no
    merge in range there is still no routine noise.
    """

    def test_merge_in_range_symbols_merged_and_old_prompt_gone(self):
        """Both directions have to be asserted: only checking that the notice is gone
        cannot prove the rule really runs, and only checking that the symbol shows up
        cannot prove the old placeholder notice was really deleted — both must pass. Here
        onmaster.py is hand-edited away from the merge result to a value neither parent
        matches (the evil-merge shape), so the first branch of the rule really hits,
        which is what proves that "folded into the actual set" is not decorative.
        """
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            # Self-check 4 requires the non-first parent of a merge to be an ancestor of
            # origin/master, so the branch being merged in can only be a commit already
            # pushed to origin/master, not a stray side branch.
            _run(repo, "checkout", "master")
            commit_py_change(repo, f"{CODE_ROOT_REL}/onmaster.py", "def m():\n    return 0\n",
                              "one more commit on master")
            _run(repo, "push", "origin", "master")
            _run(repo, "checkout", "feature")
            commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n")
            _run(repo, "merge", "master", "--no-edit")
            # Hand-edit onmaster.py (neither parent carries the value 999): the
            # evil-merge shape, used to verify that the two-parent rule for merges really
            # runs rather than merely "no longer saying anything".
            (repo / CODE_ROOT_REL / "onmaster.py").write_text(
                "def m():\n    return 999\n", encoding="utf-8",
            )
            _run(repo, "add", f"{CODE_ROOT_REL}/onmaster.py")
            _run(repo, "commit", "--amend", "--no-edit")
            code, out = _run_changed(repo)
            self.assertEqual(code, 0, out)
            # Direction 1: the earlier placeholder notice is gone
            self.assertNotIn("not yet recognized", out)
            self.assertNotIn("handled later", out)
            # Direction 2: the symbol introduced by the merge really entered the actual
            # changed symbol set
            self.assertIn("onmaster.py::m", out)

    def test_no_merge_in_range_prints_no_warning(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            commit_predict_file(repo)
            _mod(repo, "def f():\n    return 1\n")
            code, out = _run_changed(repo)
            self.assertEqual(code, 0, out)
            self.assertNotIn("merge commit", out)


if __name__ == "__main__":
    unittest.main()
