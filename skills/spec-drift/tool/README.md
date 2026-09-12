# spec-drift tool

Verification tool for spec-drift governance. What it governs is drift of the kind "the code changed, the business-rule ledger did not follow". **A global tool, belonging to no single project.** Why a project adopts this and where the two gates sit in its workflow is described in SKILL.md; this file is usage only (and hard-codes no link to any project).

The cross-project process description (what this is, how the two gates are plugged in, the four kinds of disposition) lives in the `SKILL.md` of the `spec-drift` skill, one directory level above this file.

## Usage

```bash
python3 "<skill-dir>/tool" <command> [arguments]
```

`<skill-dir>` is the directory holding the skill's `SKILL.md`, one level above this file: a plain copy resolves it to the `spec-drift` directory under `~/.claude/skills/`, a plugin install to the `spec-drift` directory under the installed plugin's `skills/`.

No new dependencies, standard library only. The ledger, the lock, the code root being verified and the names `--by` accepts are all read from `.spec-drift.json` at the repository root of the **adopting project** (all five fields are required; a missing one is an error that names which one is missing; there are also two optional fields, `hot_zone` and `labels`):

```json
{
  "code_root": "backend",
  "ledger": "design/ledger.md",
  "lock": "design/drift-lock.json",
  "owner": "<your name>",
  "assistant": "<your assistant's name>"
}
```

Every value above is an **example** — replace them with your own project's real paths and names; this file goes at **your project's repository root**, not inside this tool's directory. `repo.find_repo_root` searches upwards from the cwd for this config, and the level where it is found is the repository root (the search does not cross a git repository boundary: it stops at `.git`). `sync`/`relink` require `--by <owner>`; `confirm` accepts `<owner>` or `<assistant>`. An anchor is always written `file.py::name` (a class method is `file.py::Class::method`, the module-level pseudo-symbol is `file.py::<module>`).

### `code_root` accepts several values

`code_root` can be a string (one code root, the shape of the vast majority of projects) or a **non-empty list of strings** (several code roots, whose union is what every command scans):

```json
{ "code_root": ["backend", "worker"] }
```

Written as a plain string rather than a list, the behaviour is exactly what it is with a single code root. Written as a list, two structural constraints apply, and violating either is an error raised while the config is being loaded (you do not find out halfway through some command):

- No two items may be equal, nor may one be an ancestor directory of the other (`["backend", "backend/sub"]` is illegal) — otherwise the same physical file falls under two directory prefixes and cannot be assigned an unambiguous owner.
- No two `code_root`s may hold **`.py` files that really exist** sharing one relative path (both holding `pkg/mod.py`, say) — otherwise the symbol name `relpath::name` has no unambiguous owner. Anchors, the full scan of `impact` and the actual change set of `changed` all depend on this uniqueness. Two kinds of file are left out of this comparison: anything under a `tests` directory at any depth (the hot zone of `uncovered` and the anchor scan of `inventory` exclude those too) and `__init__.py` (any two Python package roots necessarily share it). The price of the exemption is confined to those files: an anchor into a shared `__init__.py` fails loudly on resolution rather than silently picking a root; `impact` shows a reference site in a shared file root-qualified (`svc_a/tests/conftest.py:12`) so the two are told apart; and `changed` names symbols by relpath, so a symbol changed in a shared `tests/…` or `__init__.py` file under both roots appears once in the actual set, not twice.

These two checks only run when `code_root` is a list: with a single value there is zero cost and zero behaviour change.

**Be honest with yourself before reaching for a list.** A multi-value `code_root` only fits layouts whose relative paths do not overlap by construction — two services with different top-level package names, say. Two roots that both hold `app/models.py` or `pkg/settings.py` will be refused, and the fix is to restructure or to pick one parent directory as a single `code_root` (nested `tests` directories are excluded at any depth, so one root over several services is a fine choice). Reading `reference/adopting-an-existing-project.md` § Choosing `code_root` first saves the round trip.

### `hot_zone` (optional): adding your own range to the hot zone

The hot zone of `uncovered` is derived **only** from the files the ledger anchors live in (see below). To bring directories or files that no ledger anchor points at into the "is any rule unmanaged here" check as well, configure the optional `hot_zone` field: a list of strings, each a **path relative to some `code_root`** (a file or a directory; a directory is taken recursively, every `.py` beneath it):

```json
{ "hot_zone": ["services/new_module", "utils/helper.py"] }
```

- Field absent: `uncovered` behaves exactly as it does without the field at all (derived purely from anchors). This is the default.
- Field present: hot zone = the anchor-derived files **∪** the files and directories listed here, with anything under a `tests` directory (at any depth) excluded from both sources; the output of `uncovered` labels each hot-zone file with where it came from (`anchor-derived` / `configured` / both).
- An item found under **no** `code_root`: a warning is printed and the item skipped; the command is not aborted.
- An item found under **several** `code_root`s (only possible with a multi-value `code_root`): its owner cannot be determined, so this fails loudly — it does not silently pick one.

### `labels` (optional): the four ledger section labels

The four section labels of a ledger entry (the format is in `reference/ledger-format.md`, next to `SKILL.md`) default to these English literals:

```json
{
  "labels": {
    "assertion": "**Current rule**",
    "boundary":  "**Boundary**",
    "anchors":   "**Anchors**",
    "confirmed": "**Last confirmed**"
  }
}
```

- The block is optional, but the four keys are **all or none**: half a block is refused and the missing keys are named, so a half-translated ledger cannot be half-parsed.
- Each value is the **whole line, literally**, the `**` included: matching is "the input line, with trailing whitespace stripped, equals this literal exactly".
- Validation runs when the config is loaded, so a bad label fails before a single entry is parsed. The checks, in the order the code applies them, are that each value:
  1. is a string;
  2. is not empty;
  3. equals its own stripped form — no surrounding whitespace (`"**Rule** "` would pass a mere emptiness check and then never match a single line, because the match is against the whole line);
  4. is a single line;
  5. does not look like a markdown heading — neither a level-1/level-2 heading (those terminate an entry) nor a `### <ID> <title>` entry heading;
  6. does not look like an anchor line (`` - `mod.py::f` ``): the moment an entry anchors that same symbol, its anchor line would be taken for a label and reported as a duplicate label;
  7. does not start with three backticks (a code fence), which would flip the parser's fence state and swallow every later section boundary;
  8. and finally, that the four values are distinct.
- Changing the labels never invalidates the lock. `assertion_sha` hashes only the assertion body and the boundary body — the labels take no part in it. So translating the labels in a ledger, or switching the config to a different set, needs no re-`sync` and leaves `check` behaviour unchanged.

## The eleven commands

| Command | Legal state | Behaviour | Exit code |
|---|---|---|---|
| `check` | any | judges every entry's state and compares fingerprints, see "Exit-code semantics of `check`" below | see below |
| `uncovered` | — | reports the symbols in the hot-zone files (derived from the ledger anchors, optionally unioned with the `hot_zone` field of `.spec-drift.json`; any `tests` or `node_modules` directory excluded) that no entry anchors; a `hot_zone` item that adds no file once those are excluded is reported with a `⚠` line | usually 0; 2 when a `hot_zone` item exists under several `code_root`s (its owner cannot be determined — a configuration error, see below) |
| `impact <symbol\|entry ID>` | — | reports "who references this symbol" plus "the sibling anchors under the same entry"; given an entry ID it reports once per anchor of that entry; ends with **the entries involved** — every entry that anchors the symbol (or any of the entry's anchors), each with the anchor it goes through, which is the list a Gate 1 premise list starts from | always 0 |
| `inventory [--symbol <file.py::name>\|--file <path relative to code_root>]` | — | enumerates the eight categories of AST element inside a symbol and prints a markdown table skeleton with the "verdict" and "reason" columns left blank, for building a ledger over existing code; with no argument it takes stock of every anchor currently in the ledger (any `tests` directory excluded) | always 0 |
| `sync <ID> --by <owner> --note <reason>` | S1 | generates `assertion_sha` and every anchor fingerprint, writes them to the lock, syncs the "last confirmed" date in the markdown | 0; 1 when the state or `--by` does not match |
| `confirm <ID> --by <owner\|assistant> --note <reason>` | S4 | refreshes the fingerprints and the confirmation metadata in the lock, syncs the date in the markdown | 0; 1 when it does not match |
| `relink <ID> --by <owner> --note <reason>` | S3 | rebuilds the lock record from the anchors currently in the markdown (recomputing every fingerprint), syncs the date in the markdown | 0; 1 when it does not match |
| `relink <ID> --delete --by <owner> --note <reason>` | S2 | deletes that lock entry; does **not** sync the date in the markdown | 0; 1 when it does not match |
| `changed --predict <path to the prediction file, relative to the repository root>` | — | computes the set of symbols this cycle actually changed; `base` is discovered automatically | 1 on a self-check or parse failure, otherwise 0 |
| `catalog [--book <text>] [--format md\|json]` | — | renders the ledger and the lock as a catalog grouped by book: each entry's status, signer, signing time, note, rule and anchors | 0; 2 when --book matches no book |
| `history <ID>` | — | every wording and signature one entry has had, from the git history of the ledger and the lock, plus the working tree | 0; 1 when the ID was never found or git fails |
| `verdicts <file>… [--book <name>]…` | — | grades filled-in `inventory` tables against the verdict disciplines: a row with no verdict or with none of the four; a ① that names no existing entry, or quotes ledger wording (in straight or curly double quotes, or CJK corner brackets; backticks are read as code) that is not in the ledger verbatim; a ② that names neither an existing entry ID nor a book given with `--book`; a ③ reasoned from "the ledger does not say so"; a ②, ③ or ④ with no reason. Whether a genuine quote covers every decision the line makes stays a judgement | 0 when every row passes; 1 when any fails; 2 when a file cannot be read |

**Exit code 2**: the tool could not even start — `.spec-drift.json` missing (no such file walking up to the git boundary), not valid JSON, not an object, missing a required field or holding a wrong-typed one; a multi-value `code_root` that overlaps or is ambiguous; a ledger that does not parse (a missing label, a malformed anchor line). These are configuration errors, so every command reports them as one `❌ …` line on **stderr** and never as a Python traceback; the message names the offending file or field. Read `2` as "fix the config, then run again", as distinct from `1`, which is a real finding (drift, a failed self-check, a refused state transition). One documented exception: a ledger file that is **missing or parses to zero entries** is reported by `check` itself, on stdout with exit **1** (its "Exit-code semantics" below), because for `check` that is a finding, not a start-up failure; every other command that reads the ledger (`uncovered`, `impact`, argument-less `inventory`, `catalog`, the three write commands) treats a missing ledger as a start-up failure and exits 2; `inventory --file`/`--symbol` and `changed` do not read it at all. `history` is the other exception: it reads the ledger of every revision, so a revision whose ledger does not parse — the working tree included — is reported as a note in its output and skipped, and the exit code is 0 as long as some version is left; a configuration error still exits 2.

### Exit-code semantics of `check`

`check` is the single outlet for drift alarms, and one run produces five reports:

1. every entry's state is judged; anything other than S4 is an alarm.
2. ledger anchors that do not resolve (the symbol was renamed, deleted or moved away and is no longer in the code).
3. lock anchors that vanished (reported apart from ② — this usually means the rule was refactored out, and mixing the two would drown it).
4. for S4 entries, `assertion_sha` or an anchor fingerprint disagrees with the lock record (the assertion wording changed / the code drifted).
5. warning: a symbol the ledger anchors has more than one definition of that name in the code (one `def` in each branch of an `if/else`, say).

**Any of ①–④ non-empty means a non-zero exit; ⑤ is a warning only and does not affect the exit code.** To judge "did anything drift this round", read the exit code — there is no need to count the rows in each category.

### Two notes on `impact`

- The reference sites come from **matching the symbol name as text** (the search domain is every `.py` under `code_root`, `tests/` included, `node_modules/` excluded), not from a call graph, so **false positives are inevitable** (a local variable of the same name, the name inside a string, a mention in a comment) — the output prints a line saying so, the false positives have to be filtered by hand, and every item filtered out is written into the prediction file to leave a trace. References can be missed in the same way (an alias after `import ... as`, an indirect reference through `getattr`), and a missed reference shows up as a blind spot in the gate-2 reconciliation.
- Passing an entry ID (the `R-XXX-000` shape) is equivalent to querying each of that entry's anchors in turn, and their "sibling anchors" include one another; passing a single symbol reports its sibling anchors from **whatever entry** holds it.

### The eight categories and three argument shapes of `inventory`

`inventory` is the scaffolding for **building a ledger over existing code**: every row in the ledger is one falsifiable business assertion, and that is a judgement no tool can generate; but a tool can exhaustively enumerate "where inside this symbol a rule could be carried", leaving the human or model to fill in the two blank columns, "verdict" and "reason", item by item.

The eight categories of element (the criteria are fixed, nothing may be added or removed): ① conditional branches (`If`/`IfExp`/`match`) ② `Return` statements plus, inside their expression, every `BoolOp` operand and every `Compare` comparison ③ `raise` ④ cross-module calls (the root name of the call appears in this module's import list) ⑤ object field writes (counted per assignment target, an `Attribute`/`Subscript` target counting as one each, so the chained assignment `a.x = b.y = 1` counts as 2) ⑥ member assignments in a class body ⑦ assignments to a `Name` target (tuple unpacking included) ⑧ `ExceptHandler`. ⑦ and ⑧ were taken in from what a one-off stock-taking script taught: criteria carried by a local variable, and which class of exception is caught, had both been real anchor blind spots.

A class anchor covers the **class body level** only and does not descend into method bodies — method bodies are enumerated separately as `Class::method`, so that class and method together do not count the same code twice; when taking stock of a class symbol the output additionally lists its method names, as a prompt to take stock of those separately.

The three argument shapes are mutually exclusive: with no argument it takes stock of every production anchor currently in the ledger (any `tests` directory excluded), which is what you use to check completeness after building the ledger; `--symbol` takes stock of one symbol only; `--file` takes stock of every top-level symbol plus class methods in that file, which is what you use when building a ledger from **empty** (there are no anchors to derive anything from yet). The output always ends with "how to fill in the verdict" (four verdicts: asserted by some entry / belongs to another book, no entry / no business meaning / gap, no entry asserts this yet — ① only when the entry covers every decision the item makes, and ②–④ each state a reason, ④'s reason being a one-sentence draft assertion for the owner to rule on) and "known limits" — the latter states honestly what this enumeration structurally cannot see (same-module calls, comparisons inside call arguments, absent semantics of the "deliberately does not do X" kind) rather than boasting about completeness.

### The self-checks and validations of `changed`

`changed` is the single source of "which symbols this round of work actually changed". `--predict` is required and takes the path of the prediction file relative to the repository root (where that file lives is up to each project's own document conventions; this tool hard-codes no directory name); `base` is identified mechanically from the earliest commit in git history that added that file and never has to be typed.

Before the self-checks run, `changed` prints the two facts the whole reconciliation stands on, so they are never invisible — and they are printed even when a self-check then fails:

```
base: <sha> (the commit that added <prediction file>)
mainline: origin/<name> @ <sha>
```

**Five self-checks (any one unmet is an error and exits):**

1. no uncommitted changes under `code_root` (staged, unstaged and untracked are all disallowed).
2. `base` must be an ancestor of `HEAD`.
3. `base` must not be an ancestor of `origin/<mainline>` (this catches a reused directory making the wrong base look right).
4. every non-first parent of every merge commit on the first-parent chain must be an ancestor of `origin/<mainline>`.
5. this cycle must run on a feature branch, not on the mainline branch itself.

**Three validations (an unmet one only warns and marks this cycle's prediction invalid; the command is not aborted):**

1. the candidates (the commits that added the prediction file) are non-empty — an empty set counts as a failed self-check and exits with an error, not as a warning here.
2. there is exactly one candidate — more than one (the file was deleted and added back) warns, takes the earliest, and asks for human confirmation.
3. neither `base` itself nor the range from `merge-base(base, origin/<mainline>)` to `base^` may already contain a commit that changed a `.py` under `code_root` (merge commits included, judged by the same two-branch criterion the merge case uses).

`changed` only scans the `.py` files under `code_root`; changes to the frontend, to documents, to configuration or to SQL do not enter the actual set. An `ast.parse` or decoding failure in either revision fails closed (naming the commit and the file, exiting non-zero); a file that does not exist in one of the revisions does not count as a parse failure.

### Mainline discovery

`changed` does not hard-code a mainline branch name. Once per run it asks the remote, with `git ls-remote --symref origin HEAD`, and takes the branch named by the `ref: refs/heads/<name>` line as the mainline. Self-checks 3 and 4 and validation 3 then use the full ref `refs/remotes/origin/<name>`, never the short form: a tag or a local branch named literally `origin/main` shadows the short form and git only prints a warning, while the full ref cannot be shadowed. Self-check 5 compares the current branch against the mainline's name.

The local `origin/HEAD` is never read. It is a cache: it goes stale (a fetch only creates it, it never updates it), it can dangle, and it is re-created by a fetch, which makes it useless both as a source of truth and as a test signal.

Three states of the remote HEAD are rejected loudly rather than worked around, each with the same message asking for the default branch to be set on the remote (GitHub/GitLab: repository settings; a bare repo: `git symbolic-ref HEAD refs/heads/<branch>`):

- the remote HEAD is unborn (`ls-remote` prints nothing);
- the remote HEAD is detached (only a `<sha>\tHEAD` line);
- the remote HEAD points at a tag (`ref: refs/tags/…`).

The fetch uses an explicit refspec, `git fetch origin +refs/heads/<name>:refs/remotes/origin/<name>`, so that the remote-tracking ref is created and updated whatever `remote.origin.fetch` says: under a narrow refspec (a `--single-branch` clone, or one edited by hand) a plain `git fetch origin` exits 0 without moving `origin/<mainline>` at all. After the fetch the ref is verified to exist.

Requirements: a remote named `origin` must be configured — this is checked first with `git remote get-url origin`, because without that guard a sub-directory named `origin` that happens to be a git repository is silently used as the remote by both `ls-remote` and `fetch`; the remote HEAD must point at a branch; and the client needs git ≥ 2.8 with a server that advertises the symref (older clients and servers are untested). Renaming the default branch on the remote normally needs nothing done locally; the one exception is a new name that collides with an old tracking ref as a directory/file conflict (`main` → `main/next`), where the fetch fails loudly and carries git's own `git remote prune origin` hint.

### `catalog` and `history`

Both are read-only views: they never write the ledger or the lock, and neither is a gate — drift alarms keep their one outlet, `check`.

`catalog` renders the ledger as a catalog of approved definitions, one table per book. A book is the nearest `#` or `##` heading above an entry (headings inside code fences do not count); entries above any such heading are grouped under `(no book)`. Books appear in ledger order, and entries in ledger order within their book. Every entry gets one status, the first rule that matches:

| Status | Meaning |
|---|---|
| `unsigned` | S1: in the ledger, not yet in the lock |
| `anchors changed` | S3: the anchor sets of the ledger and the lock differ |
| `anchor missing` | S4, and at least one ledger anchor no longer resolves to a symbol |
| `drifted` | S4, and the rule or boundary text, or some anchor's code, changed since the signature |
| `consistent` | S4, and the text and every fingerprint still match the signature |

"Signed by", "Signed at" and "Note" come from the lock record (`confirmed_by`, `confirmed_at`, `note`) and are empty for an unsigned entry; in a cell, multi-line text is joined with a space and `|` is escaped. Entries present only in the lock (S2, removed from the ledger) are not rows: they are named on one line after the tables, `Lock-only entries (S2, removed from the ledger): …`, left out when there are none. `--book <text>` keeps only the books whose title contains `<text>` (a case-sensitive substring); the summary line then counts only what is shown, and the S2 line is still printed. When no book matches, it prints one `❌` line to stderr naming the books there are and exits 2. `--format json` prints the same rows as a JSON object with the keys `ledger`, `entries` and `lock_only`; the rule and boundary keep their newlines, and the signature fields of an unsigned entry are `null`. The exit code is 0 whenever the catalog was printed, drifted or unsigned entries included; a missing ledger exits 2 like any other start-up failure.

`history <ID>` reads every commit that touched the ledger or the lock (`git log --full-history --date-order --reverse` over the two current paths), then the working tree, and prints a new version each time the entry's rule text, boundary text or anchor set differs from the previous version printed, or its lock record's `assertion_sha`, `confirmed_by`, `confirmed_at` or `note` does (the title and the "last confirmed" date alone do not make a version, and neither does a change to the lock's anchor fingerprints alone). `--full-history` matters when branches are merged: git's default walk follows only one side of a merge that kept that side's files, so a wording written and signed on the other branch would never be listed. With parallel branches their versions interleave by commit date, parents always before children. Each version names what changed — `entry added`, `entry removed`, `text changed`, `anchors changed`, `signature changed` — and the signature state at that version:

- `signed by <by> at <at>: <note>` — the lock record's `assertion_sha` is that of this version's text;
- `signature is for an earlier text (edited after signing)` — the lock has a record, but for other wording;
- `unsigned` — the lock has no record for the entry.

Rule, boundary and anchors are printed for the first version and whenever they change; a signature-only change prints only its signature line, and a removal only its heading. Edits not yet committed appear as a last version dated `working tree` and labelled `uncommitted`. A revision whose ledger does not parse is skipped, with a one-line note under the header (`ledger did not parse at <sha>: …`); a lock that is absent or not valid JSON at a revision counts as empty. Exit code: 0 when at least one version was printed; 1 when the ID is in no committed revision and not in the working tree, or when git fails (not a git repository, say), reported as one `❌` line.

Known limits of `history`: every revision is parsed with today's labels, so a revision written with other label wording is skipped with that note; and **a renamed ledger or lock path is not followed** — git is asked about the current paths only, so revisions from before a rename are not seen.

## The four states S1–S4 and their legal commands

| State | entry in md | entry in lock | anchor sets | the one legal command in that state |
|---|---|---|---|---|
| S1 | yes | no | — | `sync` |
| S2 | no | yes | — | `relink --delete` |
| S3 | yes | yes | md and lock differ | `relink` |
| S4 | yes | yes | md and lock agree | `confirm` |

The four states are mutually exclusive and exhaustive. A command run in the wrong state is refused, and the message names the current state and the legal command for it, for example:

```
Refused: R-FLOW-001 is currently S4; the legal command in that state is `confirm`
```

When a lock anchor no longer resolves to a symbol in the code (renamed, deleted, moved away), the two sets still agree and the state is still S4, but ③ of `check` reports it separately; the disposition is to edit the anchors in the markdown by hand, which puts the entry into S3, and then run `relink`.

## The `--by` / `--note` rules

The values `<owner>` and `<assistant>` come from the `owner`/`assistant` fields of `.spec-drift.json` at the repository root; they are not names hard-coded into this tool.

- For the three write commands `sync`, `confirm` and `relink` (`--delete` included), both `--by` and `--note` are required, and a missing one is refused.
- `sync` and `relink` require `--by <owner>`.
- Only `confirm` accepts `--by <assistant>` (it accepts `<owner>` too) — confirm corresponds to the "the rule did not change" class, which the assistant may nod through on its own; sync and relink correspond to creating a ledger entry or reconnecting anchors, which the owner has to nod through in person.
- All three write commands take a single `<ID>`; there is **no bulk command**. That is by design, not an omission: bulk confirmation makes people nod blindly under alarm fatigue, and forcing one pair of eyes over one entry at a time is the whole effect this gate is after.
- Before `sync` / `confirm` / `relink` (not `--delete`) runs, every anchor listed in that entry's markdown is checked to resolve to a symbol in the current code, and any one that does not resolve refuses the command — `relink --delete` skips this check (it exists precisely to handle symbols that have already disappeared).

## Acknowledged coverage boundaries

> `parse_symbols` only walks the top-level statements of a module, so **a `def` written inside an `if` / `try` / `with` branch produces no symbol at all** — those fall into the `<module>` pseudo-symbol, drift is still detectable at a coarse grain, and using such a symbol as an anchor is reported by ② of `check` as "does not resolve" with a non-zero exit (fail-loud, not silent). Measured 0 occurrences across the pilot.

> A module-level constant (a mapping table, say) is itself a top-level symbol, and `module_fingerprint` replaces its whole body with a placeholder. **So changing a module-level constant that only a forwarding function references leaves both the anchor fingerprint and the `<module>` pseudo-symbol unchanged** — this "the true source is not in the anchors" blind spot has to be covered by adding an explicit anchor while the ledger is being built. **`check` cannot see it; if the constant sits in the same file as an anchor, `uncovered` still lists it among the uncovered symbols, which is the only human backstop.** Only when the file holding the true source is in no hot zone at all (not sharing a file with any existing anchor) does `uncovered` fail to see it too — that case has to be recognised by hand while the ledger is being built and given an explicit anchor, and the list of cases already identified is maintained in each adopting project's own ledger, not in this tool's documentation.

## Tests

Modules inside the package use absolute imports (which is what lets `python3 <directory>` run it directly), so when running the tests `-t` has to point at **this directory**:

```bash
cd "<skill-dir>/tool"
python3 -m unittest discover -s tests -t .
```
