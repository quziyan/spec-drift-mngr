# Changelog

All notable changes to this plugin. The version is the one in `.claude-plugin/plugin.json`.

## 1.2.0 — 2026-09-11

A ledger can now be read as a catalog of approved definitions — what each entry says, who signed it, when, and whether the code still matches — and one entry's wording can be traced through every version it has had. Both are read-only views over the ledger and the lock that already existed; nothing about the format, the lock or the gates changed for projects that do not use them.

### Added

- **`catalog [--book <text>] [--format md|json]`**: the ledger and the lock rendered as a table per book: status (`consistent` / `drifted` / `anchor missing` / `unsigned` / `anchors changed`), signer, signing time, note, rule and anchors; entries left only in the lock are listed after the tables. Exit 0 whatever the statuses (it is a view, not a gate); 2 when `--book` matches no book. (`cmd_catalog.py`, `ledger.entry_books`)
- **`history <ID>`**: every wording and every signature one entry has had, from the git history of the ledger and the lock, plus the uncommitted working tree; each version says what changed and whether its text was the one signed. It walks the full history (`--full-history`), so a wording written and signed on a branch that a merge later discarded is still listed. Exit 0; 1 when the ID was never found or git fails. (`cmd_history.py`)
- **A fourth `inventory` verdict, `gap: no entry asserts this yet`**, whose reason is a one-sentence draft assertion; the verdict note now says a ① quote must cover every decision the item makes. The first three verdict strings are unchanged. (`cmd_inventory.py`)

### Changed (skill text)

- **Gate 2**: a drifted entry that defines a published number is class A when what the number means changed, and every place users read that definition (export header notes, tooltips, legends, user guides) is updated in the same branch. **Gate 1**: a requirement that changes a published number involves that number's metric entry. Tested as eval scenario 6: with the 1.1.0 text, 3 of 3 runs kept those files out of the merge requirements (one wrote that they "do not need to change"); with the 1.2.0 text, 3 of 3 required them. The skill's trigger description is unchanged.

### Docs

- `reference/ledger-format.md`: **metric entries**, one per published number, kept in a book of their own; signing one is the owner's approval of that definition.
- `reference/adopting-an-existing-project.md`: the fourth verdict; the review covers the first-pass entries and the requirement documents; what belongs in the ledger; ask verdict writers for a contradictions list; measured first-pass quality from two more books.
- `reference/known-limits.md`: anchors are Python symbols only; environment-sourced configuration; tuple-unpacked constants are not symbols.
- `tool/README.md`: ten commands; `catalog` and `history` described.

### Compatibility

No existing test was edited; `ledger.parse_ledger`, `assertion_sha` and the lock format are unchanged, so every existing lock stays valid. The files behind `check`, `uncovered`, `impact`, `changed`, `sync`/`confirm`/`relink` are untouched. On two adopted projects (103 and 49 entries) `check`, `uncovered` and `impact` print byte-identical output under 1.1.0 and 1.2.0, every `assertion_sha` is identical, and `inventory` differs only in its verdict footer.

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
