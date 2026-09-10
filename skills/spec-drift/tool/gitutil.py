"""git wrappers, base-ref discovery, the five self-checks and validation 3.

The foundation of the `changed` command: every git subprocess call is concentrated
here, always in argument-array form, never through shell interpolation.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple


class SelfCheckError(Exception):
    """A self-check or a validation is not met."""


class Mainline(NamedTuple):
    """The remote's default branch: short name and the full remote-tracking ref.

    Self-checks must use `full_ref`: a tag or local branch literally named `origin/<name>`
    shadows the short form (git only prints a warning), the full ref cannot be shadowed.
    """
    name: str
    full_ref: str


def mainline(repo_root: Path) -> Mainline:
    """Ask the remote which branch is the mainline. Never reads the local origin/HEAD:
    it is a cache that goes stale (fetch only creates it, never updates it), can dangle,
    and is re-created by fetch, so it is useless both as a source of truth and as a test signal.
    """
    probe = subprocess.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        # Without this guard a sub-directory literally named `origin` that happens to be a git
        # repository is silently used as the remote by ls-remote and fetch.
        raise SelfCheckError("no remote named 'origin' is configured")
    out = git(repo_root, "ls-remote", "--symref", "origin", "HEAD")
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/") and line.rstrip().endswith("\tHEAD"):
            name = line[len("ref: refs/heads/"):].split("\t", 1)[0]
            return Mainline(name, f"refs/remotes/origin/{name}")
    raise SelfCheckError(
        "remote 'origin' HEAD does not point to a branch, cannot determine the mainline; "
        "set the default branch on the remote (GitHub/GitLab: repository settings; "
        "bare repo: git symbolic-ref HEAD refs/heads/<branch>)"
    )


def pathspecs(code_root_rel) -> list[str]:
    """Normalize the code_root_rel argument: it accepts either a single string (the
    original shape, a single-value code_root) or a list of strings (a multi-value
    code_root), and turns both into a list used as git's several `--` pathspec
    arguments. In the single-value case this is byte-for-byte what passing one
    pathspec did before multi-root support was added.
    """
    return [code_root_rel] if isinstance(code_root_rel, str) else list(code_root_rel)


def describe_pathspecs(code_root_rel) -> str:
    """For human-readable error and warning text only; it does not affect what pathspecs() means."""
    return code_root_rel if isinstance(code_root_rel, str) else ", ".join(code_root_rel)


def git(repo_root: Path, *args: str, check: bool = True) -> str:
    """subprocess.run wrapper: argument-array form, never shell interpolation."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise SelfCheckError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def is_ancestor(repo_root: Path, a: str, b: str) -> bool:
    """Exit code 0 = is an ancestor, 1 = is not an ancestor; anything else (an
    unresolvable ref, say) is a git error and must be raised — it must not be
    quietly swallowed as "not an ancestor", otherwise self-checks 3 and 4 would
    silently pass when the mainline ref cannot be resolved.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", a, b],
        capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise SelfCheckError(
            f"git merge-base --is-ancestor {a} {b} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    return proc.returncode == 0


def merge_base(repo_root: Path, a: str, b: str) -> str:
    """With no common history git itself exits non-zero, so check=True in `git()` raises naturally — no degraded inference."""
    return git(repo_root, "merge-base", a, b).strip()


def current_branch(repo_root: Path) -> str:
    """HEAD's full symbolic ref (`refs/heads/<name>`), or `"HEAD"` on a detached HEAD.

    Deliberately not `rev-parse --abbrev-ref HEAD`: when a tag carries the same name as the
    branch, git disambiguates by printing `heads/<name>`, and self-check 5's comparison
    against the mainline's short name would then miss and let a run on the mainline through.
    `symbolic-ref` returns the full ref whatever tags exist, and exits non-zero when detached.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "symbolic-ref", "-q", "HEAD"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return "HEAD"
    return proc.stdout.strip()


def fetch_origin(repo_root: Path, m: Mainline | None = None) -> None:
    """Fetch the mainline with an explicit refspec so the remote-tracking ref is created and
    updated regardless of remote.origin.fetch (single-branch clones, narrow refspecs).
    A failure (unreachable remote, or a stale tracking ref that conflicts with a renamed
    branch such as main -> main/next) surfaces git's own stderr, which already suggests
    `git remote prune origin` for the latter.
    """
    m = m or mainline(repo_root)
    git(repo_root, "fetch", "origin", f"+refs/heads/{m.name}:{m.full_ref}")
    probe = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--verify", "-q", m.full_ref],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        raise SelfCheckError(f"fetch did not create {m.full_ref}")


def find_base(repo_root: Path, predict_relpath: str) -> tuple[str, list[str]]:
    """Mechanical discovery: the earliest commit that added the prediction file is the base."""
    out = git(repo_root, "log", "--diff-filter=A", "--format=%H", "--reverse",
               "--", predict_relpath)
    candidates = [line for line in out.split("\n") if line.strip()]  # take the whole list first, then count
    if not candidates:
        raise SelfCheckError(
            f"no add commit found for {predict_relpath} "
            "(the prediction file may have been dropped by a rebase -i)"
        )
    warnings = []
    if len(candidates) > 1:
        warnings.append(
            f"⚠ {predict_relpath} was added more than once ({len(candidates)} commits); "
            f"using the earliest, please confirm: {candidates[0][:9]} "
            "(this happens when the file was deleted and then added back)"
        )
    return candidates[0], warnings


def parents(repo_root: Path, commit: str) -> list[str]:
    out = git(repo_root, "rev-list", "--parents", "-n", "1", commit).strip()
    parts = out.split()
    return parts[1:]  # parts[0] is the commit itself


def commits_no_merges(repo_root: Path, base: str) -> list[str]:
    """Enumeration domain of the non-merge branch: the non-merge commits on the first-parent chain."""
    out = git(repo_root, "rev-list", "--first-parent", "--no-merges", f"{base}..HEAD")
    return [line for line in out.split("\n") if line.strip()]


def merge_commits(repo_root: Path, base: str) -> list[str]:
    """Enumeration domain of the merge branch and of self-check 4: the merge commits on the first-parent chain."""
    out = git(repo_root, "rev-list", "--first-parent", "--merges", f"{base}..HEAD")
    return [line for line in out.split("\n") if line.strip()]


def changed_py_files(repo_root: Path, a: str, b: str, code_root_rel) -> list[str]:
    """The .py files under code_root that changed between two revisions. --no-renames
    is mandatory: by default git reports the new path only, so the symbols at the old
    path are never parsed and their deletion never enters the set.

    code_root_rel accepts a single string or a list of strings (a multi-value
    code_root); with several values every pathspec is passed to the same git diff
    call, so what comes back is their union.
    """
    out = git(repo_root, "diff", "--no-renames", "--name-only", a, b, "--", *pathspecs(code_root_rel))
    return [line for line in out.split("\n") if line.strip() and line.endswith(".py")]


def file_at(repo_root: Path, commit: str, path: str) -> str | None:
    """The file does not exist in that revision -> None. That does not count as a parse failure."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8")  # a decoding failure raises UnicodeDecodeError as is


def has_uncommitted_changes(repo_root: Path, code_root_rel) -> bool:
    out = git(repo_root, "status", "--porcelain", "--", *pathspecs(code_root_rel))
    return bool(out.strip())


def run_self_checks(repo_root: Path, base: str, code_root_rel, m: Mainline | None = None) -> None:
    """The five self-checks; any one not met raises SelfCheckError."""
    m = m or mainline(repo_root)

    if has_uncommitted_changes(repo_root, code_root_rel):
        raise SelfCheckError(
            f"self-check 1 failed: uncommitted changes under {describe_pathspecs(code_root_rel)}"
        )

    if not is_ancestor(repo_root, base, "HEAD"):
        raise SelfCheckError(
            f"self-check 2 failed: {base} is not an ancestor of HEAD (was there a rebase?)"
        )

    if is_ancestor(repo_root, base, m.full_ref):
        raise SelfCheckError(
            f"self-check 3 failed: {base} is an ancestor of origin/{m.name} "
            "(a reused directory made the wrong base look right)"
        )

    for merge in merge_commits(repo_root, base):
        for parent in parents(repo_root, merge)[1:]:  # non-first parents
            if not is_ancestor(repo_root, parent, m.full_ref):
                raise SelfCheckError(
                    f"self-check 4 failed: non-first parent {parent[:9]} of merge "
                    f"{merge[:9]} is not an ancestor of origin/{m.name}"
                )

    ref = current_branch(repo_root)
    if ref in (f"refs/heads/{m.name}", "HEAD", ""):
        # "HEAD" (a detached HEAD) and the empty string are both not a feature branch.
        branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        raise SelfCheckError(
            f"self-check 5 failed: this cycle must run on a feature branch, "
            f"current branch is {branch!r}"
        )


def validate_base(repo_root: Path, base: str, code_root_rel, m: Mainline | None = None) -> list[str]:
    """Validation 3; returns a list of warnings (a violation is recorded with its
    reason and does not abort — it only marks this cycle's prediction metrics
    invalid, it does not make `changed` fail and exit). Candidates non-empty /
    more than one candidate (validations 1 and 2) are already done independently by
    find_base; this function only covers validation 3:
    - base itself must not change any .py under code_root.
    - Within the range from the lower bound = merge-base(base, origin/<mainline>) to
      base^ (first-parent) there must be no pre-existing non-merge commit that
      changed a .py; whether a merge commit "changed a .py" is decided by the
      two-parent rule used for merge commits: a merge counts as changing code if
      comparing symbol tables against either parent shows a difference — a
      non-empty merge_symbols_for result means it did.
    """
    m = m or mainline(repo_root)
    warnings: list[str] = []

    if changed_py_files(repo_root, f"{base}^", base, code_root_rel):
        warnings.append(
            f"⚠ validation 3 not met: the base commit {base[:9]} itself changed .py files "
            f"under {describe_pathspecs(code_root_rel)} — this cycle's prediction metrics "
            "count as invalid"
        )

    lower = merge_base(repo_root, base, m.full_ref)
    out = git(repo_root, "rev-list", "--first-parent", f"{lower}..{base}^")
    enumerated = [line for line in out.split("\n") if line.strip()]

    # Deferred import: cmd_changed.py already does `import gitutil` at module level, so
    # importing it inside the function body avoids a mutual top-level dependency — by the
    # time this line runs both modules are fully loaded, so there is no real ordering problem.
    import cmd_changed

    for commit in enumerated:
        if len(parents(repo_root, commit)) > 1:
            if cmd_changed.merge_symbols_for(repo_root, commit, code_root_rel):
                warnings.append(
                    f"⚠ validation 3 not met: before base {base[:9]} there is already a "
                    f"merge commit that changed .py, {commit[:9]} — this cycle's "
                    "prediction metrics count as invalid"
                )
            continue
        if changed_py_files(repo_root, f"{commit}^", commit, code_root_rel):
            warnings.append(
                f"⚠ validation 3 not met: before base {base[:9]} there is already a "
                f"commit that changed .py, {commit[:9]} — this cycle's prediction "
                "metrics count as invalid"
            )

    return warnings
