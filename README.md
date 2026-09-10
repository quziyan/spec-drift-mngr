# spec-drift-mngr

A Claude Code plugin shipping one skill, `spec-drift`, which keeps a project's
business-rule ledger pinned to its code through two process gates: a reconciliation
before work on a requirement starts, and a wrap-up ritual before a development branch
is finished. What the gates are, when they fire, and what each one demands is in
[`skills/spec-drift/SKILL.md`](skills/spec-drift/SKILL.md).

## Install

Pick one of the two. **Never both at once** — two skills of the same name would be
loaded, and which one answers is anybody's guess.

### A. As a plugin (recommended)

This repository is its own marketplace, so add it and then install from it:

```
/plugin marketplace add quziyan/spec-drift-mngr
/plugin install spec-drift-mngr@spec-drift-mngr
```

The skill is then invoked as `spec-drift-mngr:spec-drift`. Model-triggered invocation
works the same as for any skill and needs no prefix.

### B. As a plain skill

Copy the skill directory into your personal skills directory:

```bash
cp -R skills/spec-drift ~/.claude/skills/spec-drift
```

Remove any previous copy first (`rm -rf ~/.claude/skills/spec-drift`, backing it up if
it holds anything you want) — copying over a directory that already exists nests the
new copy inside the old one.

## Enable it in a project

The skill does nothing in a repository that has not adopted it: it needs a
`.spec-drift.json` at the repository root. How to get there, both for a project
starting from zero and for one already well into development, is in
[`skills/spec-drift/reference/adopting-an-existing-project.md`](skills/spec-drift/reference/adopting-an-existing-project.md).

## Run the checks

Repository consistency (manifests, versions, skill frontmatter, path independence)
plus the tool's own unit tests:

```bash
bash tests/check-plugin.sh
```

The tool's tests alone, and what they cover, are described in
[`skills/spec-drift/tool/README.md`](skills/spec-drift/tool/README.md) under "Tests".

## Licence

MIT — see [`LICENSE`](LICENSE). One file, `scripts/bump-version.sh`, is copied from
another MIT-licensed project; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for its notice.
