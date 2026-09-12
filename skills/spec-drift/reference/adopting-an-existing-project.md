# Enabling this in a project

**First work out which kind of project you have — the difference is legacy debt, not configuration.**

| | A project starting from zero | A project already some way into development |
|---|---|---|
| Offline backfill needed? | **No.** The ledger grows alongside the code | **Yes.** Building the ledger means a human reading the code, so it is inevitably incomplete |
| Cost to start | one config file + one assertion | one systematic stock-take (scale below) |
| How the ledger grows | an entry written in passing whenever a change goes through gate 2 | fill in the legacy first, then move to the steady state |

## A project starting from zero

Work through the three steps of "initial configuration" below and it is ready to use. After that every change goes through the two gates, and steps 3 and 4 of gate 2 already ask "did this round turn up a rule the ledger does not assert yet" — if it did, write the entry there and then.

**What matters is the phrase in step 2, "even if it holds only one assertion at first".** The value for a new project is not in writing the ledger out in full on day one, it is in **pinning down the rule of each feature as you write that feature**, so the debt is never taken on. The offline backfill of an existing project is, in essence, repaying exactly that debt.

## A project already some way into development

After the initial configuration you must first do one pass of **building the ledger and filling it in**, and the order matters:

| Step | What to do | Why it cannot be skipped |
|---|---|---|
| 1 | **Build the ledger**: read the requirement documents and the code, write assertions, attach anchors, `sync` | Building the ledger means a human reading code, so it is **inevitably incomplete** — which is what makes steps 2 and 3 mandatory |
| 2 | **`uncovered`**: which symbols in the hot zone carry no anchor at all | Give each symbol one of the three **symbol-level verdicts**: "anchor added" / "knowingly not anchored (state the price)" / "no business meaning" — the same three words the command prints in its footer |
| 3 | **`inventory`**: what is missing **inside** the symbols that do carry anchors | Exhaustive enumeration of the eight AST element kinds — **the only systematic way to find a sentence the ledger is missing**. Each item gets one of the four **item-level verdicts** the command prints: ① "asserted by entry X" / ② "belongs to another book, no entry this round" / ③ "no business meaning (purely technical)" / ④ "gap: no entry asserts this yet" (the reason is a one-sentence draft assertion) |
| 4 | **Two-family review of every batch — the first-pass entries included, with the requirement documents in hand** | Self-review has a high error rate, and the first pass itself is wrong more often than it looks; see the measured numbers below |
| 5 | Merge the gaps into draft assertions, then the **owner reviews the draft list and decides per item which drafts become entries**, before any `sync` | Creating an entry is a class-D disposition; the assistant may draft, but only the owner's nod turns a draft into an entry |
| 6 | Only now does the project enter the steady state of the two gates | — |

**Be honest about the cost** (measured on an already-launched production system over 2026-09-07/08): four books came to **2777 AST elements and 492 symbol verdicts**, took a dozen rounds of two-track review and a full day; the ledger grew from 75 entries to 97, turning up 22 rules nobody had asserted before. Two more numbers to expect, measured on a second, smaller service (2026-09-10): a single 1000-line file produced **569 inventory items, six in ten of them name assignments and library calls**; and because `sync` has no batch form, **building a ledger of N entries means asking the owner for N separate nods** — at a hundred entries that is a real session, plan it as one.

**The first pass is wrong more often than it looks** (two books of a second service, 2026-09-11). A first pass written from one reading of the code had 3 of 14 entries that said the opposite of the code; a first pass written line by line from an unusually precise design document had 7 of 15 that needed correcting, because the document's summaries ("every caller shares this gate", "falls back to the latest value") each had an exception branch in the code. The more confident the document, the easier it is to copy it as if it were the code — which is why step 4 reviews the first-pass entries, not only the gaps.

**What belongs in the ledger**: rules whose silent change would mislead a user or corrupt a stored table. Plumbing (locks, connections, path helpers, dtype mechanics, sort order kept for determinism) never goes in. As a feel for scale, a book of about a thousand lines that gains thirty entries from one inventory has been over-ledgered: in the measured runs, 39 drafted gaps consolidated into 4 to 6 entries once reviewed.

**Ask every verdict writer to end with a list of contradictions**: any line whose code contradicts a ledger sentence or a sentence of the requirement documents, quoting both. It costs nothing, and in the measured runs it found three of the seven real contradictions in one book, none of which were in any reviewer's brief.

**If the project publishes numbers** (a dashboard, exported files), write a metric book as described in `ledger-format.md` § Metric entries. Signed, it doubles as the catalog of the definitions the business has approved; `catalog` renders it.

**Three practical lessons, all learned the hard way this time:**

- **Work book by book, closing each one out**, rather than trying to build the whole ledger at once. Separate books with a `## ` level-2 heading; the tool honours that as a terminator.
- **Send each batch to review the moment it is filled in.** Saving them up so they are reviewed together lets the errors cover for one another: in one measured batch 142 items had been self-judged "① already asserted", and only 80 survived review — **more than sixty "the ledger does not say this" had been judged by their own author as "the ledger covers this"**.
- **Somebody has to own the "knowingly not anchored" list.** This time 179 symbols were known to carry criteria and, after weighing it up, still left unanchored; the price (change them and `check` stays quiet) was written into the verdict table at the time, so nobody can later pretend not to have known.

**The three mistakes that verdicts most often make, written here as a checklist** (`verdicts <file>…` checks the mechanical half of each — a quote not in the ledger, an entry ID that does not exist, a ③ reasoned from silence; whether a quote covers every decision the line makes stays a judgement):

1. When judging "already asserted by entry X", **the ledger wording you quote must be findable verbatim in the ledger file**; if it cannot be found, you made it up. **And it must cover every decision the item makes**: an item that decides two things (a threshold and a fallback) is ① only if the entry asserts both — in the measured reviews, 10–20% of ① verdicts had a genuine quote that covered only half of what the line decides.
2. When judging "belongs to another book", **you must name an entry ID that really exists** — or, when the head of this ledger places that book outside it and the book has no entries here yet, the book's name, declared to `verdicts` with `--book`. Naming only a domain usually means that entry does not exist at all.
3. When judging "no business meaning" (at either level), **the reason must not be "the ledger does not say so"** — "the ledger does not say so" is the definition of "an entry waiting to be written", and reasoning from it to "no business meaning" lets that one sentence dismiss every gap there is.

**When drafting, ask of every assertion: on which code paths is this true?** The error reviews found most often, long after the verdicts were clean, was an assertion true on one path and written as if it held on all of them: a date normalised on one of two write paths, a value injected only after a filter the text never mentions, a configured default that one caller never reads, a count taken from one of two source tables. Name the path, or the condition, in the sentence itself.

**After signing, review the whole ledger once more.** `check` exiting 0 says the signed wording and the anchored code have not moved since signing; it cannot say the wording was right. On one adoption, two full cross-family review rounds after signing found 3 and then 5 wordings that did not match the code — one of them introduced by the last edit before signing — and the two reviewers' findings did not overlap in either round, so one reviewer is not enough. Fix every missing condition a round finds that makes a sentence false on some path; stop the rounds when a round finds nothing of that kind, and leave wording that is merely imprecise to Gate 2.

## Initial configuration (the same for both kinds of project)

1. Create `.spec-drift.json` at the repository root (five required fields, `code_root`/`ledger`/`lock`/`owner`/`assistant` — `code_root` may be a string or a list of strings to cover several code roots; the optional `hot_zone` list adds directories and files beyond the ledger anchors to the default hot zone of `uncovered`; the field details are in the tool's `README.md`). **`code_root` is the one decision here that is expensive to get wrong** — run through the checklist under "Choosing `code_root`" below before writing it.
2. Build a first business-rule markdown in the **ledger format** (`ledger-format.md`, next to this file) and point `ledger` at it, even if it holds only one assertion at first; when the file `lock` points at does not exist the tool treats it as an empty lock, so it does not have to be created in advance.
3. Run `python3 "<skill-dir>/tool" check` and confirm that the config is readable, that the ledger parses to at least one entry, and that it is clean (**`check` now treats both "the ledger file does not exist" and "parsed 0 entries" as errors and exits non-zero**, rather than quietly letting them through — 0 entries never means "nothing has drifted", it means "nothing is written yet" or "the format is wrong"). After the first assertion is written the entry is in S1: run `sync <ID> --by <owner> --note <reason>` for each entry (both flags are required; a missing `--note` is refused), and only then can `check` exit 0.
4. **Tell your agents, in your own project instructions, that the ledger exists and what it outranks.** The skill is only loaded when one of the two gates triggers; everything an agent reads between gates is governed by whatever your project's standing instructions say (for Claude Code, the project's `CLAUDE.md`). Without one sentence there, the ledger is read twice per change cycle and stale documents are read the rest of the time — which is exactly the disease this mechanism treats. This sentence is yours to write, not the skill's: whether the ledger outranks the PRD, the design specs, or only older snapshots is a project policy, and a different project may decide it the other way. Keep it to one or two lines and point at the file, do not import the whole ledger into every session (a hundred entries is context you pay for on every turn). The one real host project uses this shape:

   > When you need to know what the current business rule *is*, look first at `<ledger path>`: N falsifiable assertions, each anchored to a code symbol with a machine-maintained fingerprint. When it conflicts with the historical snapshots under `<design dir>` it wins; when the PRD conflicts with it, it also wins (example: the PRD's automatic-penalty rule in §X is retired, see `<entry ID>`). Only for topics the ledger does not cover do you fall back to the raw sources below, and then you must confirm against the code.

   Nothing in that sentence names the skill, the lock file, or the gates — the gates live in the skill, the precedence policy lives with the project.

## Choosing `code_root`

Every anchor, the hot zone, the reference scan of `impact` and the change set of `changed` are all relative to `code_root`, so it is the one field worth ten minutes of thought. Measured on two real projects, both expensive adoption mistakes came from this single decision. Run through these before writing it:

1. **Prefer one directory over a list.** A single `code_root` that contains several services is fine: `tests` directories are excluded at any depth from the hot zone of `uncovered` and the anchor scan of `inventory`, so `svc_a/tests/…` and `svc_b/tests/…` under one root never inflate the backfill (`impact` still searches them for reference sites, and `changed` still counts a changed test symbol — both on purpose). Reach for a list only when the code you want covered genuinely lives in directories with no common parent short of the repository root.
2. **If you do want a list, check the relative paths do not overlap.** Two roots that both hold `app/models.py`, `pkg/settings.py` or any other same-named module are refused at load time (the symbol name `relpath::name` would have two owners). `__init__.py` and anything under a `tests` directory are exempt from that comparison; everything else is not. A quick way to see the collisions before the tool tells you:

   ```bash
   for r in svc_a svc_b; do (cd "$r" && find . -name '*.py' -not -path '*/tests/*' -not -name __init__.py); done | sort | uniq -d
   ```

   An empty result means no relative-path collision; the tool additionally refuses roots that repeat or nest (including through a symlink), which this scan does not show.
3. **Know where your tests are relative to it.** Only directories named exactly `tests` are excluded; a `test/` directory, or test modules mixed into the package, are counted as production symbols and will show up in `uncovered`.
4. **Anchors are relative to `code_root`, so changing it later means rewriting every anchor** (and `relink --by <owner>` for every entry). Decide once.
5. **What is outside stays outside.** Frontend code, another language, configuration, SQL — none of it is seen by `check` or `changed`. If a rule lives on both sides of that line (a limit enforced in the backend and repeated in the frontend), say so in the entry's boundary line, because the mechanism will only ever watch one side.
