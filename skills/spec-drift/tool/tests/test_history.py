"""Tests for history, in real temporary git repositories.

Each step of an entry's life (added, signed, edited, confirmed) is its own commit, made
with the real write commands; the test then reads the versions history reports.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import cmd_history
import cmd_write
from tests.test_check import Fixture
from tests.test_cli import _run_in
from tests.test_gitutil import _run, make_repo

TODAY = "2026-12-25"
OLD_RULE = "f always returns 1."
NEW_RULE = "f always returns one."


def commit(repo: Path, message: str) -> str:
    _run(repo, "add", "--", ".spec-drift.json", "backend", "docs")
    _run(repo, "commit", "-q", "-m", message)
    return _run(repo, "rev-parse", "HEAD").strip()


def write(fx, command: str, by: str, note: str) -> None:
    with redirect_stdout(io.StringIO()):
        assert cmd_write.run(fx.ctx, command, "R-T-001", by, note, False, TODAY) == 0


def edit_rule(fx, old: str, new: str) -> None:
    md = fx.md_path.read_text(encoding="utf-8")
    assert old in md
    fx.md_path.write_text(md.replace(old, new), encoding="utf-8")


def run_history(fx, entry_id: str = "R-T-001") -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_history.run(fx.ctx, entry_id)
    return code, buf.getvalue()


def versions(out: str) -> list[tuple[str, str]]:
    """-> [(heading line without "## ", body text)] in output order."""
    chunks = out.split("\n## ")[1:]
    result = []
    for chunk in chunks:
        heading, _nl, body = chunk.partition("\n")
        result.append((heading, body.strip("\n")))
    return result


def lifecycle(tmp: Path) -> tuple[Fixture, list[str]]:
    """add -> sync -> edit text without signing -> confirm, one commit each."""
    repo = make_repo(tmp)
    fx = Fixture(repo)
    shas = [commit(repo, "add entry")]
    write(fx, "sync", "Alice", "first signature")
    shas.append(commit(repo, "sync"))
    edit_rule(fx, OLD_RULE, NEW_RULE)
    shas.append(commit(repo, "edit text"))
    write(fx, "confirm", "Bot", "wording only")
    shas.append(commit(repo, "confirm"))
    return fx, shas


class TestHistoryLifecycle(unittest.TestCase):
    def test_versions_changes_and_signature_states(self):
        with tempfile.TemporaryDirectory() as d:
            fx, shas = lifecycle(Path(d))
            code, out = run_history(fx)
            self.assertEqual(code, 0, out)
            lines = out.splitlines()
            self.assertEqual(lines[0], "# History: R-T-001 Example rule")
            self.assertEqual(lines[2], "Ledger docs/ledger.md · lock docs/drift-lock.json · 4 versions")

            vs = versions(out)
            self.assertEqual(len(vs), 4, out)
            expected = [
                (1, shas[0], "entry added"),
                (2, shas[1], "signature changed"),
                (3, shas[2], "text changed"),
                (4, shas[3], "signature changed"),
            ]
            for (heading, _body), (k, sha, changes) in zip(vs, expected):
                self.assertRegex(heading, rf"^{k} · \d{{4}}-\d{{2}}-\d{{2}} · {sha[:9]} · {changes}$")

            first, signed, edited, confirmed = (body for _h, body in vs)
            self.assertTrue(first.startswith("Signature: unsigned\n\nRule:\n> " + OLD_RULE + "\n"), first)
            self.assertIn("\n\nBoundary:\n> Nothing else is in scope.\n", first)
            self.assertTrue(first.endswith("\n\nAnchors: `pkg/mod.py::f`"), first)

            self.assertRegex(signed, r"^Signature: signed by Alice at \d{4}-\d{2}-\d{2}T\S+: first signature$")

            self.assertTrue(edited.startswith(
                "Signature: signature is for an earlier text (edited after signing)\n\nRule:\n> " + NEW_RULE
            ), edited)
            self.assertIn("Anchors: `pkg/mod.py::f`", edited)

            self.assertRegex(confirmed, r"^Signature: signed by Bot at \S+: wording only$")
            self.assertNotIn("uncommitted", out)

    def test_working_tree_edit_is_a_final_uncommitted_version(self):
        with tempfile.TemporaryDirectory() as d:
            fx, _shas = lifecycle(Path(d))
            edit_rule(fx, NEW_RULE, "f always returns exactly one.")
            code, out = run_history(fx)
            self.assertEqual(code, 0)
            self.assertIn("· 5 versions", out)
            heading, body = versions(out)[-1]
            self.assertEqual(heading, "5 · working tree · uncommitted · text changed")
            self.assertTrue(body.startswith(
                "Signature: signature is for an earlier text (edited after signing)\n\n"
                "Rule:\n> f always returns exactly one."), body)

    def test_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            fx, _shas = lifecycle(Path(d))
            code, out, err = _run_in(fx.root, ["history", "R-T-001"])
            self.assertEqual(code, 0, err)
            self.assertIn("· 4 versions", out)


class TestHistoryEdges(unittest.TestCase):
    def test_unknown_id_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            fx, _shas = lifecycle(Path(d))
            code, out = run_history(fx, "R-NOPE-001")
            self.assertEqual(code, 1)
            self.assertEqual(out, "❌ R-NOPE-001 was not found in any committed version of "
                                  "docs/ledger.md nor in the working tree\n")

    def test_not_a_git_repository_exits_1_without_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            Fixture(tmp)
            with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(tmp.parent)}):
                code, out, err = _run_in(tmp, ["history", "R-T-001"])
            self.assertEqual(code, 1)
            self.assertTrue(out.startswith("❌ "), out)
            self.assertIn("not a git repository", out)
            self.assertEqual(len(out.splitlines()), 1)
            self.assertNotIn("Traceback", out + err)

    def test_unparseable_revision_is_noted_and_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            fx = Fixture(repo)
            commit(repo, "add entry")
            good = fx.md_path.read_text(encoding="utf-8")
            fx.md_path.write_text(good.replace("**Boundary**\n", ""), encoding="utf-8")
            broken = commit(repo, "break the ledger")
            fx.md_path.write_text(good.replace(OLD_RULE, NEW_RULE), encoding="utf-8")
            commit(repo, "fix and reword")

            code, out = run_history(fx)
            self.assertEqual(code, 0, out)
            lines = out.splitlines()
            self.assertEqual(lines[2], "Ledger docs/ledger.md · lock docs/drift-lock.json · 2 versions")
            self.assertEqual(lines[4], f"ledger did not parse at {broken[:9]}: "
                                       "R-T-001 is missing label(s): **Boundary**")
            self.assertEqual([h.split(" · ")[-1] for h, _b in versions(out)],
                             ["entry added", "text changed"])
            self.assertNotIn(broken[:9] + " ·", out)

    def test_removal_prints_only_the_heading(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            fx = Fixture(repo)
            commit(repo, "add entry")
            write(fx, "sync", "Alice", "n")
            commit(repo, "sync")
            fx.md_path.write_text("# Pilot ledger\n", encoding="utf-8")
            removed = commit(repo, "remove the entry")
            with redirect_stdout(io.StringIO()):
                assert cmd_write.run(fx.ctx, "relink", "R-T-001", "Alice", "gone", True, TODAY) == 0
            commit(repo, "relink --delete")

            code, out = run_history(fx)
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("# History: R-T-001 Example rule\n"), out)
            self.assertIn("· 3 versions", out)
            heading, body = versions(out)[-1]
            self.assertRegex(heading, rf"^3 · \S+ · {removed[:9]} · entry removed$")
            self.assertEqual(body, "")

    def test_invalid_lock_json_counts_as_unsigned(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            fx = Fixture(repo)
            fx.lock_path.write_text("{not json", encoding="utf-8")
            commit(repo, "add entry with a broken lock")
            code, out = run_history(fx)
            self.assertEqual(code, 0)
            self.assertEqual(versions(out)[0][1].splitlines()[0], "Signature: unsigned")


if __name__ == "__main__":
    unittest.main()
