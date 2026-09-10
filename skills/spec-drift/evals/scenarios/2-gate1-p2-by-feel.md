# Scenario 2 · the prediction set, and P2 by feel

What it measures: "never go by feel in the prediction step" — every P2 item is a symbol
(`file.py::name`) and carries `impact` output as its basis.

## Setup

```bash
bash $SKILL_DIR/examples/build-minimal-repo.sh $EVAL_DIR/2-p2-by-feel-<phase>-<n>
```

Clean build, no `--with-predict`, no mutation. `check` exits 0, the worktree is clean.

Task text given to the subject, verbatim:

> Requirement: refund fee becomes 5%. Produce the prediction set (P1/P2/P3).

Mechanical checks:

| # | Command | Passes when |
|---|---|---|
| C1 | `grep -c 'impact' <prediction file>` | ≥ 1 — `impact` output is cited in the file at all |
| C2 | read the P2 section | every P2 item is written as `file.py::symbol` |
| C3 | read the P2 section | every P2 item names `impact` output as its basis; nothing is listed by feel |

The prediction file's path and name are the subject's choice; the checks find it from
`git log --name-only main..HEAD` plus `git status --porcelain`.

## RED

Round 1 (`2-p2-by-feel-red-1`) is **discarded** for the same contamination as scenario 1 —
the subject wrote its premise list under the installed skill's headings.

Round 2 (`2-p2-by-feel-red-2`) is the recorded baseline. The subject ran `check`, `uncovered`,
`inventory` and `impact`, grepped `src/` for `fee`, and committed
`prediction-refund-fee-5pct.json` with a three-class set. Its P2 class, in full, is two items:

> `"id": "R-REF-001", "kind": "ledger entry text (boundary line)" … "reason": "Its Boundary
> line reads \"Nothing about partial refunds or the refund fee.\" -- the only other ledger
> prose besides R-REF-002 that mentions \"fee\". Need to confirm this disclaimer still holds
> after the rate changes …"`

> `"id": "aliased / indirect access to refund.FEE_RATE", "kind": "residual reference-search
> gap" … "reason": "… The tool's own caveat: text match cannot see `import refund as x;
> x.FEE_RATE`-style aliasing or getattr-based access. grep … also found nothing outside
> refund.py, so risk is assessed low, but not mechanically provable -- flagged rather than
> silently dropped."`

Mechanical checks:

```
$ git log --oneline main..HEAD
5ec9fa6 predict: refund fee 3% -> 5% impact set (P1/P2/P3)
[candidate files: prediction-refund-fee-5pct.json]

$ grep -c impact prediction-refund-fee-5pct.json
2

$ git status --porcelain -- src
(empty)
```

| # | Result |
|---|---|
| C1 | PASS — `impact` is cited twice in the file |
| C2 | **FAIL** — neither P2 item is a symbol: one is a ledger entry's prose line, the other is a named absence ("aliased / indirect access") |
| C3 | **FAIL** — the second item's stated basis is that `impact` found *nothing*; it is a worry, not a reference site |

**RED verdict: FAIL.** The single real P2 candidate that `impact` does report —
`refund.py::RefundRequest::amount_after_fee`, the one reference site of `FEE_RATE` — was
filed under P1 instead, and P2 was filled with two items the tool never produced.

## GREEN

Attempt 1 (`2-p2-by-feel-green-1`). The subject verified the precondition, read the anchors,
ran `impact R-REF-002`, and pasted its output into the file as the P2 heading's stated basis:

> ### P2 — indirect reach (basis: `impact` output)
>
> | Symbol | Basis |
> |---|---|
> | `refund.py::RefundRequest::amount_after_fee` | `impact FEE_RATE` reference site + R-REF-002 sibling anchor of `FEE_RATE`; reads the constant at `refund.py:18` |
>
> No false positives to filter — `impact` returned exactly the one reference site above, and
> it is a real reference … not a same-named local variable or a comment/string mention.

```
$ git log --oneline main..HEAD
9c935f3 Gate 1: prediction set for refund fee -> 5%
[candidate files: changes/2026-09-09-refund-fee-5pct.md]

$ grep -c impact changes/2026-09-09-refund-fee-5pct.md
4

$ git status --porcelain -- src
(empty)
```

| # | Result |
|---|---|
| C1 | PASS — 4 |
| C2 | PASS — the single P2 item is a symbol |
| C3 | PASS — `impact` output is the stated basis, with the false-positive filtering noted |

**GREEN verdict: PASS on the first attempt.** P3 was left empty rather than padded, which is
the other half of the same discipline.

Stability pass (`2-p2-by-feel-green-2`, fresh subject). Same shape: the `impact R-REF-002`
transcript pasted verbatim under a heading that reads "(basis for P2)", P2 = the single
symbol `refund.py::RefundRequest::amount_after_fee`, P3 explicitly "none — nothing else
references `FEE_RATE`/`amount_after_fee`, so this class is left empty rather than padded by
feel". `grep -c impact` = 3, `src` clean. **PASS.**

## Plugged

Nothing plugged: GREEN passed on the first attempt.

The RED baseline's failure was not a rationalization to name but a habit — filling P2 with
worries rather than with reference sites. The existing "Never go by feel in the prediction
step" row, plus §3's "P2 must have `impact` output as its basis", already carry it, and both
GREEN subjects quoted them back. No Red Flags row was added.
