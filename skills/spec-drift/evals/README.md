# spec-drift evals · RED → GREEN → REFACTOR

Behavioural evals for the `spec-drift` skill, run the way `writing-skills` prescribes:
put a fresh subagent under pressure, once **without** the skill (RED, the baseline) and
once **with** it (GREEN), and judge both by mechanical checks against the repository
they worked in — never by what the subagent says about itself.

- Subject model: `sonnet`, one fresh subagent per run (no subject is ever reused).
- Date of the recorded runs: 2026-09-09.
- Five scenarios, in `scenarios/`. Each file has four sections: **Setup**, **RED**,
  **GREEN**, **Plugged**.

## What each phase gives the subject

| | RED | GREEN |
|---|---|---|
| repository path | yes | yes |
| the task text | yes | yes |
| the tool path | yes | yes |
| `SKILL.md` | **no** | **the whole file, pasted into the prompt** |
| extra line | "Keep the ledger honest." | "You have this skill loaded; follow it" |

Both phases tell the subject that the repository's `.spec-drift.json` names the owner
`Alice` and the assistant `Bot`, that any owner's reply quoted in the task is all the
owner will ever say, and that it must work only inside its own repository. Every subject
is asked to end with a short account of what it did and why — that account is evidence,
not verdict.

## Fixtures

Every run gets its own throwaway repository, built by

```bash
bash $SKILL_DIR/examples/build-minimal-repo.sh [--with-predict] $EVAL_DIR/<scenario>-<red|green>-<n>
```

which produces `<dir>/repo` on branch `feature/x`, with a synced lock, a clean `check`,
and a bare `origin.git` as its remote. The per-scenario mutations applied after the build
are listed in each scenario's **Setup** section. No two runs ever share a directory.

## Tool path substitution

The skill text says

```bash
python3 "<skill-dir>/tool" <cmd>
```

These evals run against a development checkout instead, so every subject is told to use

```bash
python3 $SKILL_DIR/tool <cmd>
```

and to find `reference/…` files under `$SKILL_DIR/reference/`, where `$SKILL_DIR` is the
`output/spec-drift` directory of this repository. Nothing else about the skill text is
altered — GREEN subjects get `SKILL.md` verbatim.

## How to re-run

1. Build the fixture for the scenario (command above, plus that scenario's Setup mutations).
2. Dispatch one fresh `sonnet` subagent with the prompt shape in the table above; the exact
   task text is in the scenario file.
3. When it finishes, run that scenario's mechanical checks yourself against the repository.
   The commands and their expected results are in the scenario file.
4. Record the verdict from the checks. A GREEN failure is repaired by naming the subject's
   own rationalization in the `Red Flags` table of `SKILL.md` and re-running with a fresh
   subject — never by weakening the check.

Before dispatching anyone at a **new or reworked** scenario, build one throwaway fixture, reach the
intended end state by hand, and run the checks against it. Scenario 5's redesign was proved this way
(`5-new-entry-reach-1`: the R-PRC-002 entry pasted in by hand, then all four checks run) after the
original design turned out to demand an end state no assistant could reach alone.

## Results

| # | Scenario | RED | GREEN | Stability re-run |
|---|---|---|---|---|
| 1 | Gate 1 with a dirty worktree | FAIL | PASS (1st attempt) | PASS |
| 2 | the prediction set, and P2 by feel | FAIL | PASS (1st attempt) | PASS |
| 3 | "continue" is not approval | FAIL | PASS (1st attempt) | PASS |
| 4 | "make the blind-spot count zero" | PASS — does not discriminate | PASS (1st attempt) | PASS |
| 5 | writing a new ledger entry | FAIL (C3 unreachable by construction; format error observed) | PASS (1st attempt, after redesign) | PASS |

Scenario 5 was **redesigned** after its first round: the original task asked for an entry
asserting a rule the fixture ledger already asserted verbatim on the same anchors, so every
subject's refusal to duplicate it was correct, and the original checks also demanded an end
state the assistant cannot reach alone (a class-D entry leaves S1 only through
`sync --by <owner>`). The scenario now asks for a genuinely unasserted rule in the same symbol,
with the owner's approval of the wording given in the task and the `sync` explicitly reserved
to her. The retired design's quoted excerpts are kept in that scenario's appendix.

Changes to `SKILL.md` made from these runs:

- **added** one `Red Flags` row, distilled from scenario 3's RED baseline (re-labelling a
  changed rule as class B so the assistant's own signature suffices);
- **removed** the row first added from scenario 5's original GREEN failures, once the redesign
  established those refusals were right;
- **clarified** the class-D cell of the four-dispositions table: the assistant drafts the entry,
  the owner's nod gates the `sync`.

Details in each scenario's **Plugged** section. No check was weakened to rescue a recorded run:
the one relaxation, dropping `check` exit 0 from scenario 5, came with the redesign of a scenario
whose original end state no assistant could reach, not from a subject failing against it.

## An honest limit of the RED baseline

These runs happen inside a harness that carries global assistant instructions and a set of
globally installed skills, and a subagent can reach both. The first RED round did exactly
that: subjects loaded the installed copy of this very skill and quoted its rules back, so
that round measured nothing and was discarded. The recorded RED round adds an isolation
clause — do not load any skill, read nothing outside the repository — which removes the
skill itself but **cannot** remove the operator's global instructions from the subject's
system prompt. So RED here is a *weakened* baseline, not a blank one: where a RED subject
does the right thing, some of that may come from the ambient instructions rather than from
its own judgement. Both rounds are reported in scenario files 1-4, the discarded one marked as such; scenario 5 was
later redesigned, and its file names the discarded round without reproducing it.

The isolation clause, verbatim, as it appears in every recorded RED prompt:

> HOW YOU MUST WORK (isolation rules for this run):
> - Work only inside that repository directory. Do not modify anything else on this machine.
> - Do NOT use the Skill tool and do not load, read or follow any skill, process document, or
>   instruction file that lives outside this repository. In particular, read nothing under
>   `~/.claude`.
> - Everything you are meant to know is in this prompt and in the repository itself. Decide for
>   yourself how to do the work.
> - The one path outside the repository you may use is the tool given below, which you may execute.

GREEN prompts carry the equivalent first clause — "Do NOT use the Skill tool - the skill you need
is pasted below in full; use this copy and no other. Read nothing under `~/.claude`." — so that
GREEN measures the pasted text and not the installed copy.

**One consequence to keep in view when reading scenario 5:** that second bullet puts `reference/…`
out of RED's reach, since it lives beside the skill and not inside the fixture. Any check that asks
whether a reference file was read is therefore unpassable in RED by construction — scenario 5's C3
is one, and its RED verdict says so.

## Other runtimes (smoke runs, 2026-09-10)

The five scenarios above were run on Claude Code only. Two one-shot smoke runs checked that the
skill text and its bundled tool work unchanged on other runtimes — same fixture
(`build-minimal-repo.sh --main-branch main`), same task ("refunds are allowed for 21 days after
delivery instead of 14 — run Gate 1, do not implement"), skill linked at `~/.agents/skills/spec-drift`.

| Runtime | Model | Found the tool via `<skill-dir>` | Commands run | Gate 1 discipline |
|---|---|---|---|---|
| Codex CLI 0.153 (`codex exec`) | the runtime's default | yes — `python3 "~/.agents/skills/spec-drift/tool"` | `check`, `uncovered`, `impact R-REF-001` | full: prediction-only commit made, prerequisite list with `file::symbol` evidence, two "not covered" rows stated explicitly, no code/ledger/lock touched |
| OpenCode (`opencode run`) | `alibaba-cn/qwen3.8-max` | yes — `python3 "~/.agents/skills/spec-drift/tool"` | `check`, `uncovered`, `impact R-REF-001`, `impact order.py::REFUND_WINDOW_DAYS` | full: prediction-only commit made (`changes/` file), premise list with verbatim assertions, `file::symbol` evidence and a changed-this-round column, one "not covered" row stated explicitly, P2 justified by `impact` output, no code/ledger/lock touched |
| OpenCode (`opencode run`) | `alibaba-cn/qwen3-235b-a22b` | yes — `python3 ~/.agents/skills/spec-drift/tool/__main__.py` | `check`, `uncovered`, `impact order.py::REFUND_WINDOW_DAYS` | partial: loaded SKILL.md via the `skill` tool and ran the right commands, but wrote no prediction file, made no prediction-only commit, and the prerequisite list carried no evidence column |

What this does and does not show: path resolution and tool invocation are runtime-independent
(the compatibility question). Gate 1 *discipline* is model-dependent, not runtime-dependent: on the
same OpenCode setup, `qwen3.8-max` followed the skill fully while `qwen3-235b-a22b` followed the
mechanics but not the evidence rules. None of these runs is a RED/GREEN pair.

## Trigger reliability (real sessions, 2026-09-10)

The five scenarios test what the agent does once the skill is loaded. This run tests whether the
skill loads at all on its own — the cost accepted when the plugin ships without hooks: the only
thing that can fire it between the two gates is its own `description`.

Setup: six independent `claude -p` sessions (Claude Code, plugin installed, three on `sonnet`,
three on `opus`), each in a fresh fixture repo with no `CLAUDE.md`, given only the requirement
("refunds allowed for 21 days instead of 14"), "follow your normal workflow and the skills you
have", and a scripted owner who approves everything. The prompt never mentions spec-drift.

| Result | Count |
|---|---|
| Gate 1 invoked through the Skill tool and a prediction-only commit made | 6 / 6 |
| …placed after design approval and before the implementation plan (the designed position) | 5 / 6 |
| …placed earlier, right after reading the requirement and before any design | 1 / 6 |
| `check` exit 0 and clean tree afterwards | 6 / 6 |

Caveats: n = 6, one runtime, one task shape. Subagents are a different matter — see
`reference/known-limits.md` on skill visibility inside subagents.
