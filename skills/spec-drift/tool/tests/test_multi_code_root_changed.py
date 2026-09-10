"""What a multi-value code_root means for `changed`: a union of git pathspecs, plus splitting the relpath by the root each file belongs to.

Reuses the bare-repository scaffolding from test_gitutil, but with two code_root
directories (svc_a / svc_b).
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_changed as CH
import repo as R
from tests.test_gitutil import _run, commit_predict_file, commit_py_change, make_repo

ROOT_A = "svc_a"
ROOT_B = "svc_b"
PREDICT_REL = "docs/plans/demo/impact-prediction-20260101.md"


def _mod(repo_path: Path, root: str, content: str, message: str = "impl") -> str:
    return commit_py_change(repo_path, f"{root}/mod.py", content, message)


class TestNonMergeAcrossTwoRoots(unittest.TestCase):
    def test_changes_in_either_root_are_detected_without_root_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            repo_path = make_repo(Path(d))
            commit_predict_file(repo_path, PREDICT_REL)
            c1 = _mod(repo_path, ROOT_A, "def f():\n    return 1\n")
            _mod(repo_path, ROOT_B, "def g():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo_path, c1, [ROOT_A, ROOT_B])
            self.assertIn("mod.py::g", actual)

    def test_body_change_in_second_root_hits_that_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            repo_path = make_repo(Path(d))
            commit_predict_file(repo_path, PREDICT_REL)
            c1 = _mod(repo_path, ROOT_B, "def f():\n    return 1\n")
            _mod(repo_path, ROOT_B, "def f():\n    return 2\n")
            actual = CH.nonmerge_symbols(repo_path, c1, [ROOT_A, ROOT_B])
            self.assertEqual(actual, {"mod.py::f"})

    def test_same_relpath_in_both_roots_stays_disambiguated_per_commit(self):
        """Relative to their own root, svc_a/mod.py and svc_b/mod.py are both called
        mod.py — each is detected as changed independently, and they neither overwrite
        each other nor go missing just because the relpath string is the same."""
        with tempfile.TemporaryDirectory() as d:
            repo_path = make_repo(Path(d))
            commit_predict_file(repo_path, PREDICT_REL)
            c1 = _mod(repo_path, ROOT_A, "def f():\n    return 1\n")
            _run(repo_path, "checkout", "feature")
            _mod(repo_path, ROOT_B, "def h():\n    return 1\n")
            actual = CH.nonmerge_symbols(repo_path, c1, [ROOT_A, ROOT_B])
            self.assertIn("mod.py::h", actual)


def _ctx(repo_path: Path) -> R.Ctx:
    return R.Ctx(
        repo_path, (repo_path / ROOT_A, repo_path / ROOT_B),
        repo_path / "unused-ledger.md", repo_path / "unused-lock.json",
        "Alice", "Bot",
    )


def _run_changed(repo_path: Path, predict_relpath: str = PREDICT_REL) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = CH.run(_ctx(repo_path), predict_relpath)
    return code, buf.getvalue()


class TestRunEndToEndWithTwoRoots(unittest.TestCase):
    def test_prints_symbols_from_both_roots(self):
        with tempfile.TemporaryDirectory() as d:
            repo_path = make_repo(Path(d))
            commit_predict_file(repo_path, PREDICT_REL)
            _mod(repo_path, ROOT_A, "def f():\n    return 1\n")
            _mod(repo_path, ROOT_B, "def g():\n    return 1\n")
            code, out = _run_changed(repo_path)
            self.assertEqual(code, 0, out)
            self.assertIn("mod.py::f", out)
            self.assertIn("mod.py::g", out)

    def test_uncommitted_change_in_second_root_fails_self_check_1(self):
        with tempfile.TemporaryDirectory() as d:
            repo_path = make_repo(Path(d))
            commit_predict_file(repo_path, PREDICT_REL)
            (repo_path / ROOT_B).mkdir(parents=True, exist_ok=True)
            (repo_path / ROOT_B / "dirty.py").write_text("x = 1\n", encoding="utf-8")
            code, out = _run_changed(repo_path)
            self.assertNotEqual(code, 0)
            self.assertIn("❌", out)


if __name__ == "__main__":
    unittest.main()
