# Ledger markdown format

Ledger parsing is **exact format matching**, not "it looks about right" — the parser matches the shapes below literally, and one character off is either skipped or refused (see "What a format error does"). Copy the minimal example below and the tool parses exactly one entry out of it:

````markdown
# Example ledger

### R-001 Example rule title

**Current rule**
One sentence saying plainly what this business rule currently is; it may span several lines.

**Boundary**
What this assertion does not govern, so that it does not overlap other entries.

**Anchors**
- `path/to/file.py::symbol_name`

**Last confirmed**
2026-09-06
````

## Hard requirements

- The heading line must be `### <ID> <title>`: `###`, one space, the ID, one space, the title text. The ID must start with an uppercase letter, continue with uppercase letters and digits, and contain at least one hyphen followed by a further run of uppercase letters or digits (`R-001`, `R-FLOW-001`, `ABC-DEF`). An ID with no hyphen (`R001`), or one starting with a digit (`9-ABC`), is not legal.
- The four labels **each occupy a line of their own**, and each must equal one of the four literals character for character (no extra text, no rewording, no numbering): `**Current rule**`, `**Boundary**`, `**Anchors**`, `**Last confirmed**`.
- An anchor line must match `` - `file.py::symbol_name` `` character for character: a hyphen, one space, then a backtick-wrapped path (relative to `code_root`) + `::` + the symbol name (a class method is written `file.py::Class::method`; the module-level pseudo-symbol is `file.py::<module>`, but `<module>` is not supported as an anchor). An entry needs at least one anchor line.
- The "last confirmed" label must be followed by exactly one line of date text.
- An ID must not repeat within one ledger; none of the four labels may repeat within one entry.
- **Between two entries nothing is allowed except level-1 and level-2 headings (`# ` / `## `).** An entry's body runs from its `###` heading to the next `###` or the next `# `/`## ` — so a ledger that has grown long is split into sections with a level-2 heading such as `## Book two …`, which the tool honours as the terminator. **But a horizontal rule `---`, or an explanatory paragraph, placed between two entries is swallowed into the previous entry's "last confirmed" block** and reported as "must contain exactly one date line"; that is a mistake in the format, not a broken tool. Text explaining a section goes below the `## ` heading and above the first `###`.

## What a format error does

Exactly one format error is silent: a heading that does not match `### <ID> <title>`. That block is not counted as an entry at all and nothing is printed about it. Silent, though, only where the block has nothing above it to fall into: a malformed heading in the middle of a ledger leaves the lines that follow it inside the *previous* entry, where they raise loudly — as a repeated label if that block carries labels of its own, or as a "last confirmed" block of more than one line if it does not. So the failure stays quiet only where nothing precedes the block inside its own section — before the first entry of the file, or immediately after a `## ` section heading — or where its text happens to parse as the previous entry's last-confirmed block. `check` still alarms in the quiet case, indirectly — it exits non-zero when the ledger parses to 0 entries, and when the ledger parses to fewer entries than you wrote, the count is what shows it.

Every other format error on the list above fails loudly. A missing label, a repeated label, a malformed anchor line, an empty anchors section, a "last confirmed" block that is not exactly one line, a duplicate entry ID — each raises `LedgerError`, which nothing catches, so the command aborts naming the entry and exits non-zero.

The four labels are configurable: the optional `labels` block of `.spec-drift.json` replaces them with any other wording or language, all four or none. The rules a label value must satisfy are in `tool/README.md`.

## Metric entries: a catalog of approved definitions

When an entry defines a number that people see (a dashboard layer, an export column, a KPI), write it as a **metric entry**. The format is the same; what changes is how the four blocks are used:

- **One entry per published number.** The first sentence of the current rule reads `<name> = <formula>; source <column or field>`, and the rest states units, rounding and what a missing value shows as.
- **The boundary names what the tool cannot see**: the date or version the definition took effect, and every place the number lives outside Python code — database column definitions, SQL kept outside Python, frontend code, and the user-facing descriptions of the number (export header notes, tooltips, legends).
- **Anchor the function that computes the number and every function that derives the displayed value from it**, and prefer the narrowest symbols: several metric entries anchored to one shared function all drift together when it changes, and each needs its own confirmation.
- **Keep metric entries in a book of their own** (`## Book N: metric definitions`). Rule entries elsewhere then say "definition in R-MET-006" and assert only edge behaviour; otherwise one formula lives in two entries and is updated in only one of them.

Signing a metric entry (`sync` / `confirm --by <owner>`) is the owner's approval of that definition. `catalog` lists the book with each entry's status, signer, date and note; `history <ID>` lists every wording the entry has had and who signed which.

