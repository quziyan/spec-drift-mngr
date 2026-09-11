---
name: spec-drift
description: "Drift control between the business-rule ledger and the code: a pre-work reconciliation (Gate 1) and a wrap-up ritual (Gate 2). USE WHEN starting work on a new requirement, after finishing reading a requirement and before touching the code, after a design is approved and before writing an implementation plan, before seeding test data, wrapping up a change, after walkthroughs or reviews are done and before merging a development branch, when finishing a development branch. NOT FOR changes that touch no business rule (styling, pure technical refactors, dependency bumps). Applies only to repositories that have a .spec-drift.json at the root."
---

# Spec drift control · two gates

`<skill-dir>` in this file and in `reference/` means the directory that contains this SKILL.md. On Claude Code that directory is `${CLAUDE_SKILL_DIR}`; on other runtimes (Codex, OpenCode) use the path you loaded this file from.

## 0. Kill switch and adoption check (the first thing on every entry into this skill)

```bash
test -f .spec-drift-disabled && echo "SPEC-DRIFT DISABLED"
```

The path is the **repository root**, not the tool directory — disabling this in one project must not knock it out in the others.

**If that file exists, stop this skill immediately, do nothing, and do not explain the mechanism to the user.** Just carry on with the work in hand as normal.

Disable: `touch .spec-drift-disabled`  ·  Restore: `rm .spec-drift-disabled`

Then, second:

```bash
test -f .spec-drift.json || echo "SPEC-DRIFT NOT ADOPTED"
```

No `.spec-drift.json` at the repository root means **this repository has not adopted spec-drift**: stop here and do nothing, exactly as above. To adopt it, read `reference/adopting-an-existing-project.md`.

---

## 1. What this is, and why it exists

Most repositories accumulate a pile of unmaintained documents describing the business rules as they stood at some moment in the past. Assistants (and people) keep reading an old document, mistake it for the rule in force today, and work from a rule that has been superseded — which takes a human watching the whole way to correct.

A project that adopts this mechanism has **one ledger of the business rules that are true right now** (a set of falsifiable assertions, each anchored to a specific code symbol). The spec-drift tool (`<skill-dir>/tool/`) pins the ledger to the code with symbol fingerprints; the paths — the ledger, the lock file, the code root being verified — all come from `.spec-drift.json` at the repository root, and the body of this skill hard-codes no project's paths.

The ledger markdown is the sole authority for the anchors and the assertions; the lock file is its machine projection (symbol fingerprints and confirmation records) and is never edited by hand — only `sync` / `confirm` / `relink` write it.

**This mechanism does not guarantee the ledger is always right. It guarantees that once the ledger and the code come apart, the alarm goes off at the wrap-up of the next change.**

Command usage is in `<skill-dir>/tool/README.md`; the design motivation and reasoning particular to a project are in that project's own design documents.

---

## 2. Where it plugs in

Taking the superpowers workflow as the example:

| Point | What to do |
|---|---|
| after the `brainstorming` design is approved, before `writing-plans` | **run Gate 1** |
| during `writing-plans` / `subagent-driven-development` / `executing-plans` | **stay out of it** (the gates are per change cycle, not per task) |
| **before** the verification tests of `finishing-a-development-branch` | **run Gate 2** |

**Gate 1 goes between "the requirement has been read" and "hands on the code"**: earlier and there is no requirement to analyse; later and the code is already written, which makes the prediction hindsight.

**Gate 2 goes before merging**: the ledger, the lock and the reconciliation result must be merged **in the same batch** as this round's code changes — split into two batches, the ledger is wrong for the interval in between. Gate 2 runs after any walkthrough or review steps the project already has (verification on a real machine, cross review, and so on), and before merging.

---

## 3. Gate 1 · reconciliation before starting work

For every new requirement, **compulsorily inserted between finishing reading the requirement and touching the code**. Seeding test data goes through this gate too.

**Hard precondition before producing the prediction commit P**: under the directory that `code_root` in `.spec-drift.json` points at, **staged, unstaged and untracked must all three be empty**. If they are not, refuse to write the file. (Otherwise "write the implementation in the working tree first, then commit the prediction file separately" makes the whole gate a formality — measured, every one of the history self-checks passes.)

> ⚠️ This precondition is currently **enforced only by this skill's own discipline**; the tool itself intercepts nothing at Gate 1. Before writing P, run this yourself:
> ```bash
> git status --porcelain -- <code_root>
> ```
> Any output at all, and the file must not be written.

### The five actions

1. Run `python3 "<skill-dir>/tool" check`. An unclean ledger means the previous round's wrap-up was never finished — **finish it before starting work**.
2. Identify from the requirement which ledger entries are involved (a requirement that changes a published number involves that number's metric entry); **run `uncovered` while you are at it**.
3. Entry by entry, **open the anchor symbols and read the current source**. **Do not consult memory, only the code just read.**
4. Run `impact` and produce the **prediction set**. Write the prediction file where the project keeps its change documents, commit it alone (predictions only, no implementation), and pass its path to `changed --predict` later. That commit is the base-ref.
5. Hand the premise list to `<owner>`.

### The prediction set has three classes, always by symbol (`file.py::name`)

| Class | Meaning | Basis |
|---|---|---|
| P1 direct change | symbols the requirement explicitly changes **or adds**, not limited to ledger anchors | the requirement text |
| P2 indirect reach | callers, and sibling anchors under the same entry | `impact` output, **every false positive filtered out must be noted** |
| P3 uncertain | might be touched, only reading tells | marked by the assistant after reading |

**P2 must have `impact` output as its basis; listing it by feel is not allowed.** Going by feel is precisely the disease this mechanism treats, and letting it come back in the prediction step wastes the whole exercise.

**Premise list format**: entry / the ledger assertion (verbatim) / the code fact (just read) / evidence (`file.py::symbol`) / changed this round or not.

### Two hard constraints

- **Constraint one: every line must carry `file::symbol` evidence, and what has not been read must not go on the list.** The rule is short: **if you cannot state the evidence, you cannot make the claim.**
- **Constraint two: whatever the ledger does not cover must be said out loud.** If the requirement touches a place that shows up in the `uncovered` output and no entry corresponds to it, write "the ledger does not cover this; here is the code fact as just read, plus the evidence" — **no fudging it, no pretending the ledger is complete.**

**What `<owner>` does**: read the list, and answer yes / no / correction line by line. **They do not have to go and check the code themselves. The prediction set does not need `<owner>`'s review.**

---

## 4. Gate 2 · the wrap-up ritual

Position: **after** the project's existing walkthrough/review steps, **before** merging into the mainline.

1. Run `check` to get the drifted entries, the entries in a state other than S4, and the reports of vanished and unresolvable anchors.
2. Run `changed` for the actual set; **the prediction set is always read with `git show <base>:<path to the prediction file>` — never from the working tree, never from HEAD**. Do the three-cell reconciliation and append the result to the end of the prediction file.
3. Compare the ledger text against the new code entry by entry and judge whether the rule really changed; **at the same time judge whether a rule the ledger does not yet assert has appeared inside the already-anchored symbols** (→ class D). Before adding or editing any ledger entry, read `reference/ledger-format.md`.
4. **Take the symbols in the actual set that no entry anchors (hits and blind spots alike) and judge one by one whether it carries a new rule** (→ class D). The part inside hot-zone files can be cross-checked with `uncovered`. Here too: before adding or editing any ledger entry, read `reference/ledger-format.md`.
5. Dispose of everything by the four classes.
6. The ledger, the lock and the reconciliation appended to the prediction file are merged into the mainline **in the same batch** as this round's code changes; the wrap-up counts as finished only when `check` comes back at zero.

### The three-cell reconciliation

| | in the actual set | not in the actual set |
|---|---|---|
| **predicted** | hit | miss |
| **not predicted** | blind spot | nothing |

**A miss** has four attributions, one line recorded for each, and **the first must not be the default**: the requirement shrank (normal) / it was never implemented (a defect) / a P3 uncertain item was ruled out (normal) / **the prediction was too wide** (normal).

> The fourth was added from the measured 2026-09-06 dry run: **all** 5 misses that round belonged to it, and not one of the three original classes fitted. Two sub-forms — **the prediction assumed a function body had to change when editing a data table was enough** (adding an outward-facing state, say, needs only the mapping table changed, and not a word of the forwarding function); and **a false positive of `impact`'s text matching was taken for P2** (those tests referenced the symbol but assert nothing about the behaviour that changed). Forcing them into "the requirement shrank" would hide something that matters: **too wide a prediction says the prediction method can be sharper, whereas a shrinking requirement says the requirement changed** — what the two feed into the next round is completely different.

**Blind spots**: each one must get a line of attribution, and the attribution feeds the next round. Four kinds can be attributed as a batch (one line covering each): newly added test functions; `::<module>` pseudo-symbols; an outer class swept in because one of its inner methods changed; symbols swept in by the merge judgement. If a blind spot cannot be explained, check `reference/known-limits.md` first.

> **Blind spots are this mechanism's only self-calibration signal.** Which is why "the prediction set is always read from the base version" is a hard constraint: if one more commit at wrap-up time appends the symbols actually touched into the prediction section, the history self-checks all go green and the blind spots go to zero — that is not the prediction having been accurate, that is dressing "I did not predict this" up as "I predicted this".

### The four classes of disposition

| Class | Case | Whose nod | Tool |
|---|---|---|---|
| **A the rule changed** | the existing rule itself changed | **`<owner>`** | edit the md, then `confirm --by <owner>` |
| **B the rule did not change** | refactoring, added logging, wording, comments, moves | **`<assistant>` on its own** | `confirm --by <assistant>` |
| **C the symbol is gone** | an anchor was renamed, deleted or moved away | **`<owner>`** | fix the md anchors by hand, then `relink --by <owner>` |
| **D a new rule** | a business rule the ledger does not yet assert has appeared in the code | **`<owner>`** | the `<assistant>` may draft the entry text; the `<owner>`'s nod is what gates the `sync --by <owner>` that follows |

**A drifted entry that defines a published number** (a metric entry: a dashboard layer, an export column, a KPI; see `reference/ledger-format.md` § Metric entries) needs one more thing. If what the number means changed, it is class A whoever made the change, and **every place users read that definition — export header notes, tooltips, legends, user guides — is updated in the same branch**; name those files in the wrap-up. A ledger that states one formula while the screen explains another is exactly the drift this mechanism exists to stop.

**Class B being the `<assistant>`'s own call is the key to the whole load-shedding design.** A, C and D must have `<owner>`'s nod, but they only come up when "the rule really changed / the symbol is gone / a new rule appeared"; everyday refactoring is always class B and never bothers `<owner>`.

**"A nod" has to be explicit approval of this batch of entries itself.** "Continue", "keep going", "use your judgement" and other advancement instructions **do not count** — those tell you not to stop, not that they have read it. Taking a generic advancement instruction and running `sync` / `relink --by <owner>` on it is signing in their name: the `confirmed_by` left in the lock will claim they confirmed it, when they never looked. When you cannot tell, ask; do not guess. (Measured on 2026-09-06: one "continue" was taken as a green light, all 34 entries of a ledger build were counter-signed, and the whole batch was reverted afterwards.)

`<owner>` (the person whose nod A, C and D require) and `<assistant>` (the only role that can sign class B) both come from `.spec-drift.json` at the repository root; they are not names hard-coded into this skill.

---

## 5. Three nevers

| Never | Why |
|---|---|
| **Never hard-block CI** | this is a process gate, not a build gate; the point of `check` exiting non-zero is that a human sees it |
| **Never confirm in bulk** | no command has a bulk entry point — type them one at a time. What that prevents is blind confirmation under alarm fatigue |
| **Never go by feel in the prediction step** | P2 must have `impact` output as its basis |

---

## Red Flags

| Thought | Reality |
|---|---|
| "Continue" means approve | It means keep going; the owner has not read the entries |
| "Continue" is not approval, so I will sign it myself as the assistant | Class B is refactoring, wording and moves — nothing else. A rule that really changed stays class A whoever signs it; re-labelling the case to fit the signature you are allowed to produce leaves the same lie in the lock |
| I'll add the symbols I actually touched to the prediction file so the blind-spot count is honest | That turns "I did not predict this" into "I predicted this"; the base version is the only one that counts |
| I remember what this function does | Memory is exactly what this mechanism treats as the disease — read the anchor now |
| The ledger is probably complete here | Say "not covered" and give the code fact with evidence |
