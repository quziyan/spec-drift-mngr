# Changelog

All notable changes to this plugin. The version is the one in `.claude-plugin/plugin.json`.

## 1.1.0 — 2026-09-10

Fixes from adopting the skill on an existing Python service that had never used it (a second, smaller code base than the pilot). The core loop — configure, build the ledger, `sync`, `check`, `impact`, predict, change, `changed`, `confirm` — worked end to end; these are the edges it hit.

### Fixed

- **Multi-value `code_root` was unusable on ordinary Python projects.** The relative-path uniqueness check counted `tests/conftest.py` and `__init__.py` as collisions, so two package roots could never be configured together. Files under any `tests` directory and `__init__.py` are now left out of that comparison; a genuinely shared production module is still refused. (`repo.py`)
- **`tests` directories are excluded at any depth**, not only directly under `code_root`. A `code_root` holding several services (`svc/tests/…`) previously let every nested test symbol into `uncovered` and `inventory` while the banner still claimed `tests/` was excluded. One definition now, `repo.is_test_path`, shared by the hot zone, the configured `hot_zone` field, the inventory anchor scan and the multi-root check. (`cmd_uncovered.py`, `cmd_inventory.py`, `repo.py`)
- **Configuration errors are one line, exit code 2.** A missing, non-JSON, non-object or wrong-typed `.spec-drift.json`, an ambiguous `code_root`, a ledger file that does not exist (except under `check`, which keeps its documented exit 1) or a ledger that does not parse used to surface as a Python traceback. The CLI now prints one `❌ <message>` line on stderr and exits 2 (distinct from 1, a real finding); `load_config` validates the shape of every required field. (`cli.py`, `symbols.py`)
- **`impact` no longer drops files that share a relative path across code roots** (now possible for the exempt `tests/…` and `__init__.py` files); such reference sites are shown root-qualified. (`cmd_impact.py`)
- **`changed` prints `base:` and `mainline:`** before its self-checks — the two facts the reconciliation stands on were the only invisible links in the chain. (`cmd_changed.py`)

### Docs

- `reference/adopting-an-existing-project.md`: a "Choosing `code_root`" checklist; step 3 now shows the required `--note`; the verdict vocabulary is unified into two levels (symbol-level for `uncovered`, item-level for `inventory`) and the `uncovered` footer uses the same words; the cost paragraph adds the inventory noise ratio and the "N entries = N owner nods" cold-start cost.
- `reference/known-limits.md`: first-inventory noise is by construction; a symbol's fingerprint includes the comment block above it.
- `tool/README.md`: exit code 2; the honest sentence on when a multi-value `code_root` fits; the `changed` diagnostic lines.

### Tests

241 (was 225): multi-root exclusions and their downstream in `impact`, nested `tests` exclusion in three places, the CLI error surface (config shapes, malformed ledger, one-line guarantee), the `changed` diagnostic lines and their order.

## 1.0.1 — 2026-09-10

Initial public release as a Claude Code plugin (also installable into Codex and OpenCode through `~/.agents/skills`).
