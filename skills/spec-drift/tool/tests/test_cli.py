"""Tests for the CLI entry point's error surface: a configuration or ledger error is one
line on stderr and exit code 2, never a traceback."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import cli
from tests.test_check import Fixture


def _run_in(root: Path, argv: list[str]) -> tuple[int, str, str]:
    old = os.getcwd()
    os.chdir(root)
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()
    finally:
        os.chdir(old)


class TestConfigErrorsAreCleanCliErrors(unittest.TestCase):
    def test_ambiguous_multi_root_is_one_line_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            Fixture(tmp)
            for root in ("svc_a", "svc_b"):
                (tmp / root / "pkg").mkdir(parents=True)
                (tmp / root / "pkg" / "mod.py").write_text("def f():\n    pass\n", encoding="utf-8")
            (tmp / ".spec-drift.json").write_text(
                '{"code_root": ["svc_a", "svc_b"], "ledger": "docs/ledger.md", '
                '"lock": "docs/drift-lock.json", "owner": "Alice", "assistant": "Bot"}',
                encoding="utf-8",
            )
            code, out, err = _run_in(tmp, ["check"])
            self.assertEqual(code, 2)
            self.assertTrue(err.startswith("❌ "), err)
            self.assertIn("pkg/mod.py", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(len(err.splitlines()), 1)

    def test_malformed_ledger_is_exit_2_for_check(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = Fixture(tmp)
            fx.md_path.write_text(fx.md_path.read_text(encoding="utf-8").replace("**Boundary**\n", ""), encoding="utf-8")
            code, _out, err = _run_in(tmp, ["check"])
            self.assertEqual(code, 2)
            self.assertIn("Boundary", err)
            self.assertNotIn("Traceback", err)

    def test_config_wrong_shapes_are_exit_2(self):
        cases = {
            "null": "must be a JSON object",
            "42": "must be a JSON object",
            "{not json": "not valid JSON",
            '{"code_root": "backend", "ledger": null, "lock": "k", "owner": "A", "assistant": "B"}': "'ledger' must be a non-empty string",
            '{"code_root": "backend", "ledger": "l", "lock": "k", "owner": "", "assistant": "B"}': "'owner' must be a non-empty string",
        }
        for text, expected in cases.items():
            with self.subTest(config=text), tempfile.TemporaryDirectory() as d:
                tmp = Path(d)
                Fixture(tmp)
                (tmp / ".spec-drift.json").write_text(text, encoding="utf-8")
                code, _out, err = _run_in(tmp, ["check"])
                self.assertEqual(code, 2, err)
                self.assertIn(expected, err)
                self.assertNotIn("Traceback", err)

    def test_message_with_newline_is_still_one_stderr_line(self):
        """Inject a multi-line message directly: a file name cannot carry a raw newline
        through FileNotFoundError (it is repr-escaped), so that path would not exercise
        the normalisation."""
        original = cli._dispatch
        cli._dispatch = lambda args: (_ for _ in ()).throw(RuntimeError("first line\nsecond line"))
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                code = cli.main(["check"])
        finally:
            cli._dispatch = original
        self.assertEqual(code, 2)
        self.assertEqual(err.getvalue(), "❌ first line second line\n")

    def test_missing_required_field_is_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            Fixture(tmp)
            (tmp / ".spec-drift.json").write_text('{"code_root": "backend"}', encoding="utf-8")
            code, _out, err = _run_in(tmp, ["check"])
            self.assertEqual(code, 2)
            self.assertIn("missing required field", err)

    def test_no_config_in_repo_is_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".git").mkdir()
            code, _out, err = _run_in(tmp, ["check"])
            self.assertEqual(code, 2)
            self.assertIn("repository root not found", err)

    def test_missing_ledger_file_is_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = Fixture(tmp)
            fx.md_path.unlink()
            code, _out, err = _run_in(tmp, ["uncovered"])
            self.assertEqual(code, 2)
            self.assertIn("ledger.md", err)
            self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
