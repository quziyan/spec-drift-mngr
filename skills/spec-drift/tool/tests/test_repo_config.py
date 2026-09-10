"""Locating and validating the repository root .spec-drift.json. Added when the tool was generalized to any repository."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import repo
import symbols as S

FULL_CONFIG = {
    "code_root": "backend",
    "ledger": "docs/ledger.md",
    "lock": "docs/drift-lock.json",
    "owner": "Alice",
    "assistant": "Bot",
}


class TestFindRepoRoot(unittest.TestCase):
    def test_finds_root_by_walking_up(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            self.assertEqual(repo.find_repo_root(deep), root)

    def test_missing_config_raises_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as d:
            deep = Path(d) / "a" / "b"
            deep.mkdir(parents=True)
            with self.assertRaises(RuntimeError) as cm:
                repo.find_repo_root(deep)
            self.assertIn(S.CONFIG_FILENAME, str(cm.exception))

    def test_does_not_cross_git_boundary_into_parent_repo(self):
        """A reproduction case from review: in a nested-repository layout the walk must not silently bind to the parent repository's config.

        outer/ is a git repository and has a .spec-drift.json; outer/inner/ is **another
        independent git repository** nested inside its tree (with its own .git) but with
        no .spec-drift.json of its own. Running find_repo_root from outer/inner/deep must
        stop and raise at inner's .git boundary rather than reaching through to outer's
        config.
        """
        with tempfile.TemporaryDirectory() as d:
            outer = Path(d) / "outer"
            (outer / ".git").mkdir(parents=True)
            (outer / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")

            inner = outer / "inner"
            (inner / ".git").mkdir(parents=True)
            deep = inner / "deep"
            deep.mkdir(parents=True)

            with self.assertRaises(RuntimeError) as cm:
                repo.find_repo_root(deep)
            self.assertIn(S.CONFIG_FILENAME, str(cm.exception))
            self.assertIn("git", str(cm.exception))

    def test_config_in_same_dir_as_git_still_found(self):
        """When .git and .spec-drift.json sit at the same level, the boundary check must not block the repository's own config."""
        with tempfile.TemporaryDirectory() as d:
            root = (Path(d) / "repo").resolve()
            (root / ".git").mkdir(parents=True)
            (root / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")
            deep = root / "a" / "b"
            deep.mkdir(parents=True)
            self.assertEqual(repo.find_repo_root(deep), root)


class TestLoadConfig(unittest.TestCase):
    def test_all_fields_present_loads(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")
            self.assertEqual(S.load_config(root), FULL_CONFIG)

    def test_missing_field_names_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            partial = dict(FULL_CONFIG)
            del partial["owner"]
            del partial["lock"]
            (root / ".spec-drift.json").write_text(json.dumps(partial), encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                S.load_config(root)
            self.assertIn("owner", str(cm.exception))
            self.assertIn("lock", str(cm.exception))

    def test_no_default_for_missing_field(self):
        """Silently falling back to a default is the disease this tool treats: a missing field must raise, never be quietly filled in."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".spec-drift.json").write_text(json.dumps({"code_root": "backend"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                S.load_config(root)


class TestBuildCtx(unittest.TestCase):
    def test_ctx_carries_owner_and_assistant(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")
            ctx = repo.build_ctx(root)
            self.assertEqual(ctx.owner, "Alice")
            self.assertEqual(ctx.assistant, "Bot")
            self.assertEqual(ctx.code_root, root / "backend")
            self.assertEqual(ctx.ledger_path, root / "docs" / "ledger.md")
            self.assertEqual(ctx.lock_path, root / "docs" / "drift-lock.json")

    def test_single_string_code_root_yields_one_tuple_via_code_roots(self):
        """String shape: ctx.code_root stays a Path (the behaviour from before
        multi-root support was added), while ctx.code_roots, the uniform view, is
        always a one-element tuple."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".spec-drift.json").write_text(json.dumps(FULL_CONFIG), encoding="utf-8")
            ctx = repo.build_ctx(root)
            self.assertIsInstance(ctx.code_root, Path)
            self.assertEqual(ctx.code_roots, (root / "backend",))


class TestMultiCodeRoot(unittest.TestCase):
    """code_root also accepts a list of strings."""

    def _write_config(self, root: Path, code_root) -> None:
        cfg = dict(FULL_CONFIG)
        cfg["code_root"] = code_root
        (root / ".spec-drift.json").write_text(json.dumps(cfg), encoding="utf-8")

    def test_list_code_root_yields_path_tuple(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a").mkdir()
            (root / "svc_b").mkdir()
            self._write_config(root, ["svc_a", "svc_b"])
            ctx = repo.build_ctx(root)
            self.assertEqual(ctx.code_root, (root / "svc_a", root / "svc_b"))
            self.assertEqual(ctx.code_roots, (root / "svc_a", root / "svc_b"))

    def test_single_element_list_also_works(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a").mkdir()
            self._write_config(root, ["svc_a"])
            ctx = repo.build_ctx(root)
            self.assertEqual(ctx.code_roots, (root / "svc_a",))

    def test_empty_list_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_config(root, [])
            with self.assertRaises(ValueError):
                repo.build_ctx(root)

    def test_non_string_element_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_config(root, ["svc_a", 1])
            with self.assertRaises(ValueError):
                repo.build_ctx(root)

    def test_bad_type_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_config(root, {"a": 1})
            with self.assertRaises(ValueError):
                repo.build_ctx(root)

    def test_duplicate_entries_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a").mkdir()
            self._write_config(root, ["svc_a", "svc_a"])
            with self.assertRaises(ValueError):
                repo.build_ctx(root)

    def test_nested_roots_rejected(self):
        """One code_root being an ancestor directory of another would put the same
        physical file under two pathspec prefixes at once; it must be rejected loudly,
        never resolved by silently picking one."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a" / "sub").mkdir(parents=True)
            self._write_config(root, ["svc_a", "svc_a/sub"])
            with self.assertRaises(ValueError) as cm:
                repo.build_ctx(root)
            self.assertIn("must not nest", str(cm.exception))

    def test_identical_roots_via_different_spelling_rejected(self):
        """Two config entries spelled differently that resolve() to the same directory (e.g. './svc_a' and 'svc_a')."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a").mkdir()
            self._write_config(root, ["svc_a", "./svc_a"])
            with self.assertRaises(ValueError):
                repo.build_ctx(root)

    def test_overlapping_relative_py_path_rejected(self):
        """Two code_roots each hold a real .py file at the same relative path, so the
        symbol name `relpath::name` has no unique owner; this must be rejected loudly."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a" / "pkg").mkdir(parents=True)
            (root / "svc_b" / "pkg").mkdir(parents=True)
            (root / "svc_a" / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
            (root / "svc_b" / "pkg" / "mod.py").write_text("y = 2\n", encoding="utf-8")
            self._write_config(root, ["svc_a", "svc_b"])
            with self.assertRaises(ValueError) as cm:
                repo.build_ctx(root)
            self.assertIn("pkg/mod.py", str(cm.exception))

    def test_non_overlapping_files_across_roots_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a" / "pkg").mkdir(parents=True)
            (root / "svc_b" / "pkg").mkdir(parents=True)
            (root / "svc_a" / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "svc_b" / "pkg" / "b.py").write_text("y = 2\n", encoding="utf-8")
            self._write_config(root, ["svc_a", "svc_b"])
            ctx = repo.build_ctx(root)  # not raising is the pass condition
            self.assertEqual(len(ctx.code_roots), 2)


class TestResolveRelpathAmbiguity(unittest.TestCase):
    """The second line of defence in repo._resolve_relpath: even when a Ctx with
    overlapping files is hand-assembled, bypassing the validation in build_ctx, reading
    must still raise loudly rather than silently picking the first root in the list."""

    def test_ambiguous_relpath_raises_on_read(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc_a").mkdir()
            (root / "svc_b").mkdir()
            (root / "svc_a" / "mod.py").write_text("x = 1\n", encoding="utf-8")
            (root / "svc_b" / "mod.py").write_text("y = 2\n", encoding="utf-8")
            ctx = repo.Ctx(
                root, (root / "svc_a", root / "svc_b"),
                root / "unused-ledger.md", root / "unused-lock.json",
                "Alice", "Bot",
            )
            with self.assertRaises(ValueError) as cm:
                repo.read_source(ctx, "mod.py")
            self.assertIn("mod.py", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
