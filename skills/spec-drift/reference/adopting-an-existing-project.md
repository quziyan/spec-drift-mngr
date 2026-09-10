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
| 2 | **`uncovered`**: which symbols in the hot zone carry no anchor at all | Judge each one "anchor added / knowingly not anchored / should not be covered"; "knowingly not anchored" must state the price |
| 3 | **`inventory`**: what is missing **inside** the symbols that do carry anchors | Exhaustive enumeration of the eight AST element kinds — **the only systematic way to find a sentence the ledger is missing** |
| 4 | **Two-family review of every batch** | Self-review has a high error rate; see the measured numbers below |
| 5 | Merge the gaps into draft assertions, then the **owner reviews the draft list and decides per item which drafts become entries**, before any `sync` | Creating an entry is a class-D disposition; the assistant may draft, but only the owner's nod turns a draft into an entry |
| 6 | Only now does the project enter the steady state of the two gates | — |

**Be honest about the cost** (measured on an already-launched production system over 2026-09-07/08): four books came to **2777 AST elements and 492 symbol verdicts**, took a dozen rounds of two-track review and a full day; the ledger grew from 75 entries to 97, turning up 22 rules nobody had asserted before.

**Three practical lessons, all learned the hard way this time:**

- **Work book by book, closing each one out**, rather than trying to build the whole ledger at once. Separate books with a `## ` level-2 heading; the tool honours that as a terminator.
- **Send each batch to review the moment it is filled in.** Saving them up so they are reviewed together lets the errors cover for one another: in one measured batch 142 items had been self-judged "① already asserted", and only 80 survived review — **more than sixty "the ledger does not say this" had been judged by their own author as "the ledger covers this"**.
- **Somebody has to own the "knowingly not anchored" list.** This time 179 symbols were known to carry criteria and, after weighing it up, still left unanchored; the price (change them and `check` stays quiet) was written into the verdict table at the time, so nobody can later pretend not to have known.

**The three mistakes that verdicts most often make, written here as a checklist:**

1. When judging "already asserted by entry X", **the ledger wording you quote must be findable verbatim in the ledger file**; if it cannot be found, you made it up.
2. When judging "belongs to another book", **you must name an entry ID that really exists**. Naming only a domain and no ID usually means that entry does not exist at all.
3. When judging "should not be covered", **the reason must not be "the ledger does not say so"** — "the ledger does not say so" is the definition of "an entry waiting to be written", and reasoning from it to "should not be covered" lets that one sentence dismiss every gap there is.

## Initial configuration (the same for both kinds of project)

1. Create `.spec-drift.json` at the repository root (five required fields, `code_root`/`ledger`/`lock`/`owner`/`assistant` — `code_root` may be a string or a list of strings to cover several code roots; the optional `hot_zone` list adds directories and files beyond the ledger anchors to the default hot zone of `uncovered`; the field details are in the tool's `README.md`).
2. Build a first business-rule markdown in the **ledger format** (`ledger-format.md`, next to this file) and point `ledger` at it, even if it holds only one assertion at first; when the file `lock` points at does not exist the tool treats it as an empty lock, so it does not have to be created in advance.
3. Run `python3 "<skill-dir>/tool" check` and confirm that the config is readable, that the ledger parses to at least one entry, and that it is clean (**`check` now treats both "the ledger file does not exist" and "parsed 0 entries" as errors and exits non-zero**, rather than quietly letting them through — 0 entries never means "nothing has drifted", it means "nothing is written yet" or "the format is wrong"). After the first assertion is written the entry is in S1: run `sync --by <owner>` for each entry, and only then can `check` exit 0.
4. **Tell your agents, in your own project instructions, that the ledger exists and what it outranks.** The skill is only loaded when one of the two gates triggers; everything an agent reads between gates is governed by whatever your project's standing instructions say (for Claude Code, the project's `CLAUDE.md`). Without one sentence there, the ledger is read twice per change cycle and stale documents are read the rest of the time — which is exactly the disease this mechanism treats. This sentence is yours to write, not the skill's: whether the ledger outranks the PRD, the design specs, or only older snapshots is a project policy, and a different project may decide it the other way. Keep it to one or two lines and point at the file, do not import the whole ledger into every session (a hundred entries is context you pay for on every turn). The one real host project uses this shape:

   > When you need to know what the current business rule *is*, look first at `<ledger path>`: N falsifiable assertions, each anchored to a code symbol with a machine-maintained fingerprint. When it conflicts with the historical snapshots under `<design dir>` it wins; when the PRD conflicts with it, it also wins (example: the PRD's automatic-penalty rule in §X is retired, see `<entry ID>`). Only for topics the ledger does not cover do you fall back to the raw sources below, and then you must confirm against the code.

   Nothing in that sentence names the skill, the lock file, or the gates — the gates live in the skill, the precedence policy lives with the project.
