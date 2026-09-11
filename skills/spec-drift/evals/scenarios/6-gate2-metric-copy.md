# Scenario 6 · a changed metric and its user-facing copy

What it measures: when a drifted entry defines a number people see (a metric entry), and what
the number means changed, the wrap-up must require every place users read that definition —
export header notes, tooltips, user guides — to be updated in the same branch. The tool cannot
see those files (they are not Python symbols, or not anchored), so only the skill text can make
this happen.

This scenario is **incremental**, unlike 1–5: it tests one clause added in 1.2.0, so RED is the
1.1.0 `SKILL.md` and GREEN is the 1.2.0 `SKILL.md`, both pasted in full. It is a **paper
exercise**: the repository, the diff and the tool output are given on one page, and the subject
runs no command. That isolates the one judgement under test — which files must change before
merging — from the mechanics scenarios 1–5 already cover.

## Setup

The subject gets the skill text and a one-page scenario:

- a repository whose ledger has a signed metric entry `R-MET-016 Export conversion rate (conv_rate)`:
  `conv_rate = export downloads ÷ export requests over all events, rounded to 3; null when there are no requests`, anchored to `stats.py::compute_funnel`;
- a requirement from the owner ("failed downloads should not count as attempts; conversion should be downloads over successful requests");
- the branch diff, which changes only `compute_funnel` to divide by `requests − fails`;
- `check` (one fingerprint drift on `R-MET-016`) and `changed` (one symbol, predicted);
- the repository file list, which includes `backend/config.py` (`EXPORT_COL_META`, the header notes written into every exported xlsx), `web/dashboard.html` (tooltips) and `web/export_help.md` (the export user guide) — none of them touched by the branch.

Task text: run Gate 2; write the three-cell reconciliation, the disposition of every drifted
entry with class, nod and commands, and the complete list of what must be true and which files
must change before the branch may merge.

Pass criterion: the pre-merge list **requires** the three user-facing descriptions of `conv_rate`
to be updated in the same branch. Listing them as optional, as "my own judgement", or as files
that need not change is a fail. All runs must also get the disposition itself right (class A,
the owner's nod, edit the ledger then `confirm --by <owner>`).

## RED (1.1.0 SKILL.md, 3 runs)

3 / 3 FAIL. All three dispositioned the entry correctly as class A with the owner's nod, and all
three saw the three files — and then kept them out of the merge requirements because the skill
scoped Gate 2 to anchored symbols:

> **Flagged, not mandated by the spec-drift mechanism itself (my own judgement, outside what Gate 2 actually requires):** `backend/config.py`'s `EXPORT_COL_META`, `web/dashboard.html`'s tooltip, and `web/export_help.md` …

> **Files that do *not* need to change for this gate, and why I'm not touching them:** `backend/config.py` (`EXPORT_COL_META`), `web/dashboard.html`, `web/export_help.md`. None of them appear in the diff, none of them are anchors on any ledger entry …

> **Explicitly not required by the mechanical gate, flagged separately as my own judgment**: `web/dashboard.html` (metric tooltip), `web/export_help.md` (user guide), and `backend/config.py::EXPORT_COL_META` …

The second quote is the failure the clause exists for: a disciplined reading of the old text
argued itself *out* of fixing the copy.

## GREEN (1.2.0 SKILL.md, 3 runs)

3 / 3 PASS. Each run put the three files into the merge requirements as numbered edits, and each
kept the disposition right (class A, the owner's nod on the exact ledger text, then
`confirm --by <owner>`). One run named the stakes in the clause's own terms:

> None of these three appear in "What this branch did" (only `backend/stats.py` changed), and that is a **gap that blocks merge**, not an optional follow-up.

## What changed in SKILL.md

Two additions, nothing removed:

- Gate 2, after the table of the four dispositions: a drifted entry that defines a published number is class A when its meaning changed, and every place users read that definition is updated in the same branch.
- Gate 1, action 2: a requirement that changes a published number involves that number's metric entry.

The shipped `SKILL.md` is byte-identical to the text the GREEN runs were given.

