"""Ledger markdown parsing and assertion_sha.

The markdown is the sole authority for anchors and assertions; the lock is its machine projection.
"""
from __future__ import annotations

import hashlib
import re
from typing import NamedTuple

class Labels(NamedTuple):
    """The four section labels of a ledger entry, as whole-line literals (including the `**`)."""
    assertion: str
    boundary: str
    anchors: str
    confirmed: str


ROLES = ("assertion", "boundary", "anchors", "confirmed")
DEFAULT_LABELS = Labels("**Current rule**", "**Boundary**", "**Anchors**", "**Last confirmed**")

_HEADING = re.compile(r"^###\s+(?P<id>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s+(?P<title>.+?)\s*$")
_ANCHOR = re.compile(r"^-\s+`(?P<anchor>[^`]+)`\s*$")
# A level-1 or level-2 heading terminates the current entry: once the ledger grows to
# dozens of entries it must be possible to split it into sections (`## Book two ...`),
# while an entry body is delimited only by the four labels and carries no end marker of
# its own. Without this termination rule the section heading is swallowed into the
# previous entry's "last confirmed" block and raises "must contain exactly one date
# line" — a rule missing from the parser, not a mistake in the ledger. Level-3 headings
# are excluded: a level-3 heading is the entry itself.
_SECTION = re.compile(r"^#{1,2}\s")


def labels_from_config(cfg: dict) -> Labels:
    """Read the optional `labels` block of the config file.

    Absent -> DEFAULT_LABELS. Present -> all four roles are required (a half-translated
    ledger is refused), each a whole-line literal that cannot be mistaken for other
    ledger syntax. Validation runs at config load time so a bad label fails before any
    entry is parsed. Only an absent key means "use the defaults": an explicit null is a
    mistake, and falling back to the English labels would hide it.
    """
    if "labels" not in cfg:
        return DEFAULT_LABELS
    block = cfg["labels"]
    if not isinstance(block, dict):
        raise ValueError(
            "labels must be an object with keys assertion, boundary, anchors, confirmed "
            "(or be omitted)"
        )
    missing = [r for r in ROLES if r not in block]
    if missing:
        raise ValueError(f"labels block is incomplete, missing: {', '.join(missing)} (all four or none)")
    values = []
    for role in ROLES:
        v = block[role]
        if not isinstance(v, str):
            raise ValueError(f"labels.{role} must be a string")
        if not v.strip():
            raise ValueError(f"labels.{role} must not be empty")
        if v != v.strip():
            raise ValueError(f"labels.{role} must not have surrounding whitespace (it is matched as a whole line)")
        if "\n" in v or "\r" in v:
            raise ValueError(f"labels.{role} must be a single line")
        if _SECTION.match(v) or _HEADING.match(v):
            raise ValueError(f"labels.{role} looks like a markdown heading; headings end an entry")
        if _ANCHOR.match(v):
            raise ValueError(f"labels.{role} looks like an anchor line")
        if v.startswith("```"):
            raise ValueError(f"labels.{role} must not start with a code fence")
        values.append(v)
    if len(set(values)) != 4:
        raise ValueError("the four labels must be distinct")
    return Labels(*values)


class LedgerError(Exception):
    pass


class Entry(NamedTuple):
    entry_id: str
    title: str
    assertion: str
    boundary: str
    anchors: list[str]
    confirmed_date: str
    heading_line: int          # 1-based, used by bump_confirmed_date


def _role_of(line: str, labels: Labels) -> str | None:
    """A label line is a line that, after stripping trailing whitespace, equals one of the four literals exactly."""
    text = line.rstrip()
    for role, literal in zip(ROLES, labels):
        if text == literal:
            return role
    return None


def _sections(block: list[str], labels: Labels) -> dict[str, list[str]]:
    """Split an entry body by role. A label repeated inside one entry is an error (fail-loud).

    Previously a repeated label silently reset `out[current] = []` and only the last
    block was kept, so everything written before it (possibly a directly contradictory
    rule) was lost without a sound while `assertion_sha` stayed byte-for-byte identical.
    """
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in block:
        role = _role_of(line, labels)
        if role is not None:
            if role in out:
                raise LedgerError(f"label {getattr(labels, role)} appears more than once in the same entry")
            current = role
            out[role] = []
        elif current is not None:
            out[current].append(line)
    return out


def _strip_blank_edges(lines: list[str]) -> list[str]:
    body = list(lines)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def _normalize(lines: list[str]) -> str:
    """Same normalization used for the assertion hash: strip trailing whitespace per line, join with newline."""
    return "\n".join(line.rstrip() for line in lines)


def parse_ledger(md: str, labels: Labels = DEFAULT_LABELS) -> dict[str, Entry]:
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heads: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        m = _HEADING.match(line)
        if m:
            heads.append((idx, m.group("id"), m.group("title")))

    # Section terminator lines: `#`/`##` headings. Lines inside a fence **must be
    # skipped** — when an entry body embeds a ```markdown example, the lines of that
    # example starting with # would be mistaken for a section boundary and truncate the
    # boundary text right there, so edits made after the truncation point would leave
    # the fingerprint unchanged (found by a codex review on 2026-09-08, which built a
    # counterexample).
    sections: list[int] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and _SECTION.match(line):
            sections.append(i)

    entries: dict[str, Entry] = {}
    for pos, (idx, entry_id, title) in enumerate(heads):
        end = heads[pos + 1][0] if pos + 1 < len(heads) else len(lines)
        end = min([end] + [i for i in sections if i > idx])
        try:
            secs = _sections(lines[idx + 1:end], labels)
        except LedgerError as e:
            raise LedgerError(f"{entry_id} {e}") from None
        missing = [getattr(labels, r) for r in ROLES if r not in secs]
        if missing:
            raise LedgerError(f"{entry_id} is missing label(s): {', '.join(missing)}")

        anchors: list[str] = []
        for line in secs["anchors"]:
            if not line.strip():
                continue
            m = _ANCHOR.match(line)
            if not m:
                raise LedgerError(f"{entry_id} has a malformed anchor line: {line!r}")
            anchors.append(m.group("anchor"))
        if not anchors:
            raise LedgerError(f"{entry_id} has an empty anchors section")

        confirmed = _strip_blank_edges(secs["confirmed"])
        if len(confirmed) != 1:
            raise LedgerError(f"{entry_id}: 'last confirmed' must contain exactly one date line")

        if entry_id in entries:
            raise LedgerError(f"duplicate entry id: {entry_id}")
        entries[entry_id] = Entry(
            entry_id=entry_id,
            title=title,
            assertion=_normalize(_strip_blank_edges(secs["assertion"])),
            boundary=_normalize(_strip_blank_edges(secs["boundary"])),
            anchors=anchors,
            confirmed_date=confirmed[0].strip(),
            heading_line=idx + 1,
        )
    return entries


def assertion_sha(entry: Entry) -> str:
    """The rule text and the boundary text are each normalized with leading and trailing
    blank lines removed, joined with a single \\n, then hashed with sha256."""
    payload = entry.assertion + "\n" + entry.boundary
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bump_confirmed_date(md: str, entry_id: str, date_str: str, labels: Labels = DEFAULT_LABELS) -> str:
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    entries = parse_ledger(md, labels)
    if entry_id not in entries:
        raise LedgerError(f"the ledger has no entry {entry_id}")
    start = entries[entry_id].heading_line - 1
    ends = [e.heading_line - 1 for e in entries.values() if e.heading_line - 1 > start]
    end = min(ends) if ends else len(lines)

    for i in range(start, end):
        if _role_of(lines[i], labels) == "confirmed":
            for j in range(i + 1, end):
                if lines[j].strip():
                    lines[j] = date_str
                    return "\n".join(lines)
    raise LedgerError(f"{entry_id}: could not find the 'last confirmed' body line")
