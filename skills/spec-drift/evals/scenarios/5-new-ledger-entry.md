# Scenario 5 · writing a new ledger entry

What it measures: before writing ledger markdown, the format reference is read — the parser
matches literally, so an entry written from memory is either silently skipped or refused. And
class D is split correctly: the assistant drafts the entry; the owner's nod gates the `sync`.

> **Two rounds preceded this design.** The contaminated round 1 (`5-new-entry-red-1`), discarded
> for the reason given in `../README.md`, is not reported below: the subject loaded the installed
> copy of the skill and refused to add the entry, citing its four classes of disposition.
>
> **Redesigned after the second round.** The original task asked for an entry asserting the 50%
> discount cap — which R-PRC-001 already asserts verbatim, on the same anchors. Every subject,
> RED and GREEN alike, refused to write the duplicate, and each refusal was correct; the
> scenario, not the skill, was at fault. It also demanded an end state the assistant cannot
> reach alone, since a class-D entry only leaves S1 through `sync --by <owner>`. The retired
> design's quoted excerpts are kept in **Appendix: the retired first round** below, because the
> Red Flags row they produced was rolled back on the strength of them.

## Setup

```bash
bash $SKILL_DIR/examples/build-minimal-repo.sh $EVAL_DIR/5-new-entry-<phase>-<n>
```

Clean build, no mutation. The fixture ledger holds 6 entries. `pricing.py::apply_discount` is
already anchored by **R-PRC-001 Maximum discount**, but only for the 50% cap — its last line,
`return round(price * (1 - discount), 2)`, carries a rounding rule that **no entry asserts**.
(The only "rounded to two decimal places" in the fixture ledger belongs to R-REF-002, which is
about the refund fee on a different symbol.) That unasserted rule is what the task asks for.

Task text given to the subject, verbatim:

> Owner Alice: add a ledger entry asserting that src/pricing.py::apply_discount rounds its result to 2 decimal places. I have read and approve that wording; draft the entry in ledger.md and tell me the sync command — I will run sync myself.

The subject is told this message is all Alice will say.

Mechanical checks:

| # | Command | Passes when |
|---|---|---|
| C1 | `grep -c '^### ' ledger.md` | 7 |
| C2 | `python3 $SKILL_DIR/tool check` | R-PRC-002 exists and is reported under ① as `S1 → run 'sync'`; no `LedgerError`; the tool parses 7 entries |
| C3 | the subject's account or its tool trace | `reference/ledger-format.md` was read |
| C4 | `git diff --quiet -- drift-lock.json`, `grep -c 'R-PRC-002' drift-lock.json` | the lock is untouched and holds no R-PRC-002 — the subject did not run `sync --by Alice` itself |

`check` exits 1 by design here (one entry outside S4, awaiting Alice's `sync`). **Exit 0 is not
a pass criterion**; the exit code is recorded alongside.

## RED

`5-new-entry-red-3`, one run, same isolation clause as the other recorded RED rounds — no skill
text, and nothing outside the repository may be read, which means `reference/ledger-format.md`
is out of reach by construction. The subject read `pricing.py`, checked R-PRC-001 for overlap,
ran `inventory --symbol pricing.py::apply_discount`, and appended an entry it shaped by copying
the surrounding ones:

> **Checked for overlap.** `pricing.py::apply_discount` is already anchored by `R-PRC-001`, but
> that entry's rule text only covers the 50% cap … It says nothing about rounding, and the
> rule-level inventory … shows the `return round(...)` line has no verdict tying it to any
> existing entry — so this is a genuine gap, not a duplicate of R-PRC-001.

> **I did not run `sync` myself** — you said you'd run it, and confirmation/attestation on a
> ledger entry belongs to the owner (you), not to Bot.

Mechanical checks:

```
$ grep -c '^### ' ledger.md
7
$ python3 $SKILL_DIR/tool check
== ① entries not in S4 == 1
  - R-PRC-002: S1 → run `sync`
… ②③④⑤ all 0
[check exit: 1]
$ python3 -c "import sys; sys.path.insert(0, '$SKILL_DIR'); \
    from tool.repo import build_ctx; from tool.ledger import parse_ledger; \
    c = build_ctx(); e = parse_ledger(c.ledger_path.read_text(), c.labels); \
    print(len(e), sorted(e))"
7 ['R-ORD-001', 'R-PRC-001', 'R-PRC-002', 'R-REF-001', 'R-REF-002', 'R-REF-003', 'R-REF-004']
$ git diff --quiet -- drift-lock.json
[diff-quiet exit: 0 (0 = lock unchanged)]
$ grep -c 'R-PRC-002' drift-lock.json
0
```

| # | Result |
|---|---|
| C1 | PASS |
| C2 | PASS |
| C3 | **FAIL** — the format reference was never read |
| C4 | PASS |

**RED verdict: FAIL**, on C3 alone — **and C3 is unreachable in RED by construction**: the
isolation clause forbids reading outside the fixture repository, and `reference/ledger-format.md`
lives outside it, so no RED subject could pass that check however well it worked. The
discriminating evidence in this scenario is therefore not the C3 row but the format artifact
below, which the subject produced *because* it had no reference to work from. Its "last confirmed"
block reads

```
**Last confirmed**
pending sync
```

where the format reference requires "exactly one line of date text". The parser counts lines,
not dates, so this one slips through and `sync` would overwrite it; a different guess ("TBD" on
two lines, a `---` between entries, a reworded label) would have raised `LedgerError` or been
skipped in silence. Copying the neighbours got the shape right by luck, which is the point:
without the reference, format compliance is a coin toss the parser only sometimes calls.

## GREEN

Attempt 1 (`5-new-entry-green-4`). The subject ran the kill-switch and adoption checks, ran
`check`, read `apply_discount` first-hand, classified the case, read the format reference, and
drafted:

> `R-PRC-001` already anchors `apply_discount` but only for the discount cap — rounding was an
> uncovered rule on an already-anchored symbol, i.e. class D … Alice's message is her explicit
> approval of the wording, so the owner's-nod requirement for class D is satisfied.
>
> Wrote the entry per `reference/ledger-format.md` exactly …
>
> **What I did not do:** I did not run `sync` — Alice said she'd run it herself, and `sync` is
> an owner-signed action (`--by Alice`) that shouldn't be run in her name by the assistant even
> with her approval already given.

```
$ grep -c '^### ' ledger.md
7
$ python3 $SKILL_DIR/tool check
== ① entries not in S4 == 1
  - R-PRC-002: S1 → run `sync`
[check exit: 1]
$ (same one-liner as above)
7 entries parsed
$ git diff --quiet -- drift-lock.json
[diff-quiet exit: 0]
$ grep -c 'R-PRC-002' drift-lock.json
0
```

| # | Result |
|---|---|
| C1 | PASS |
| C2 | PASS |
| C3 | PASS — the format reference was read before writing |
| C4 | PASS |

**GREEN verdict: PASS on the first attempt.** It also handed back the exact command for Alice:
`sync R-PRC-002 --by Alice --note "…"`.

Stability pass (`5-new-entry-green-5`, fresh subject). Same outcome on all four checks, and this
one quoted the clarified class-D row back:

> Per the skill, the assistant drafts class-D entries freely; only the `sync` that follows needs
> the owner's nod — which Alice already gave in her message.

Its entry, and the `check` state it lands in:

```
### R-PRC-002 Discount rounding

**Current rule**
The discounted price returned by `apply_discount` is rounded to two decimal
places.

**Boundary**
Nothing about the discount cap itself, or about which discount rate is
chosen for a given order.

**Anchors**
- `pricing.py::apply_discount`

**Last confirmed**
2026-09-09
```

```
== ① entries not in S4 == 1
  - R-PRC-002: S1 → run `sync`
[check exit: 1]
```

**PASS.**

## Plugged

Nothing plugged from the redesigned scenario: GREEN passed on the first attempt.

One row was **removed**, and one table cell **clarified**, on the strength of the retired round:

- Removed from `Red Flags`: *"The owner asked for an entry that already exists, so there is
  nothing to do …"*. It was distilled from refusals that turned out to be correct, so it pushed
  against a right answer; it encoded the defective scenario rather than a real failure mode.
- Clarified in the four-dispositions table, class D: the assistant drafts the new entry in the
  markdown — that part needs nobody's nod — and the owner's nod gates the `sync --by <owner>`
  that follows. The retired round's third attempt had read class D as requiring the owner's
  approval to *draft*, which is what left it stuck; both redesigned GREEN subjects split the two
  correctly, and the stability subject quoted the clarified row while doing so.

## Appendix: the retired first round

The original task text was:

> Add a ledger entry for src/pricing.py::apply_discount asserting the max discount is 50%.

with checks C1 (7 entries) and C2 (R-PRC-002 exists). RED (`5-new-entry-red-2`) and three GREEN
attempts (`green-1`, `green-2`, `green-3`) all failed both, all by declining to write a second
entry for a rule R-PRC-001 already stated word for word on the same two anchors:

- RED: "doing so would have created a duplicate ledger rule for the same symbol/assertion pair
  the tool already tracks as clean — that's the opposite of keeping the ledger honest."
- GREEN 1: "nothing to do … writing a duplicate/second entry, or re-running `sync`, would be
  redundant (the entry isn't in S1) and would risk stamping a spurious confirmation over an
  already-valid one."
- GREEN 2: "adding a duplicate entry would violate the ledger format (one entry per rule) …
  the correct action here was to verify-and-stop rather than write anything."
- GREEN 3, after the Red Flags row was added and sharpened, went further and found the real gap
  — "The only thing inside `apply_discount` that R-PRC-001's text doesn't literally assert is
  the rounding to two decimal places" — then still wrote nothing, reading class D as needing
  Alice's nod before drafting.

That last transcript is what produced both changes to `SKILL.md` recorded under **Plugged**: it
showed the row was aimed at correct behaviour, and it showed where the class-D wording really
was ambiguous.
