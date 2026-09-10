#!/usr/bin/env bash
#
# check-plugin.sh — repository consistency checks for the spec-drift-mngr plugin.
# Run from anywhere: bash tests/check-plugin.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

FAILED=0

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=1; }

check() {  # check <label> <command...>
  local label="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    pass "$label"
  else
    fail "$label"
    [[ -n "$out" ]] && printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

echo "spec-drift-mngr checks (in $REPO_ROOT)"
echo ""

# --- manifests -------------------------------------------------------------

check "plugin.json parses" \
  python3 -c 'import json;json.load(open(".claude-plugin/plugin.json"))'
check "marketplace.json parses" \
  python3 -c 'import json;json.load(open(".claude-plugin/marketplace.json"))'

check "the two version fields agree" python3 -c '
import json, sys
a = json.load(open(".claude-plugin/plugin.json"))["version"]
b = json.load(open(".claude-plugin/marketplace.json"))["plugins"][0]["version"]
if a != b:
    sys.exit(f"plugin.json {a} != marketplace.json {b}")
print(a)
'

# --- the skill -------------------------------------------------------------

check "SKILL.md frontmatter opens, closes within 15 lines, and declares name + a real description" python3 -c '
import sys
lines = open("skills/spec-drift/SKILL.md", encoding="utf-8").read().splitlines()

if not lines or lines[0] != "---":
    sys.exit("SKILL.md does not open with a bare --- line")

close_idx = None
for i in range(1, min(len(lines), 15)):
    if lines[i] == "---":
        close_idx = i
        break
if close_idx is None:
    sys.exit("frontmatter is not closed with a bare --- line within the first 15 lines")

fm = lines[1:close_idx]

if not any(l.strip() == "name: spec-drift" for l in fm):
    sys.exit("frontmatter lacks a bare: name: spec-drift")

desc_line = next((l for l in fm if l.startswith("description:")), None)
if desc_line is None:
    sys.exit("frontmatter lacks a description: line")
value = desc_line[len("description:"):].strip()
if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", chr(39)):
    value = value[1:-1]
if len(value) < 40:
    sys.exit(f"description is only {len(value)} chars (need >= 40): {value!r}")
'

check "SKILL.md actually uses \${CLAUDE_SKILL_DIR} on a command line, not just in prose" python3 -c '
import sys
lines = open("skills/spec-drift/SKILL.md", encoding="utf-8").read().splitlines()
if not any("${CLAUDE_SKILL_DIR}" in l and "python3" in l for l in lines):
    sys.exit("no line in SKILL.md has both ${CLAUDE_SKILL_DIR} and python3 -- "
             "the substitution may be mentioned only in prose or a comment, "
             "with a stale path actually driving the command")
'

# --- content hygiene, over every tracked file ------------------------------
# The patterns below are written so that this script is not itself a match
# (bracket-split literals, backslash-escaped regex metacharacters).

check "no installation path is hard-coded outside README.md" python3 -c '
import re, subprocess, sys
pat = re.compile(r"~/[.]claude/skills/spec[-]drift")
bad = []
for f in subprocess.run(["git","ls-files"],capture_output=True,text=True,check=True).stdout.split():
    if f == "README.md":
        continue
    try:
        t = open(f, encoding="utf-8").read()
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        continue
    if pat.search(t):
        bad.append(f)
if bad:
    sys.exit("hard-coded install path in: " + ", ".join(bad))
'

check "no Chinese characters outside the two ledger fixtures" python3 -c '
import re, subprocess, sys
allowed = {"skills/spec-drift/tool/tests/test_labels.py",
           "skills/spec-drift/tool/tests/test_ledger.py"}
pat = re.compile("[\\u3000-\\u303f\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\uff00-\\uffef]")
bad = []
for f in subprocess.run(["git","ls-files"],capture_output=True,text=True,check=True).stdout.split():
    if f in allowed:
        continue
    try:
        t = open(f, encoding="utf-8").read()
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        continue
    m = pat.search(t)
    if m:
        bad.append(f"{f} ({m.group()!r} at offset {m.start()})")
if bad:
    sys.exit("Chinese characters in: " + "; ".join(bad))
'

check "no private words, local paths, internal IPs, or leaked project details" python3 -c '
import re, subprocess, sys

# Chinese private words: allowed only in the two label fixtures, and only for
# these two words -- any other pattern below still fails there.
zh_exempt = {"skills/spec-drift/tool/tests/test_labels.py",
             "skills/spec-drift/tool/tests/test_ledger.py"}
zh_words = re.compile("\\u7533\\u8bc9|\\u95e8\\u5e97")  # appeal-system word | store word

# A bare mention of the generic project-instructions filename is allowed only
# in the one doc that talks about wiring the ledger into it.
claude_md_exempt = {"skills/spec-drift/reference/adopting-an-existing-project.md"}
claude_md = re.compile("CLAUDE\\.md")

# Everything else below: no exemptions, anywhere.
other_words = re.compile(
    "Qu[Z]hi"
    "|Co[C]o"
    "|\\u8bbe\\u8ba1\\u65b9\\u6848"   # design-proposal word
    "|/User[s]/"
    "|haidila[o]"
    "|192\\.168\\."
    "|10\\.[0-9]+\\.[0-9]+\\."
    "|172\\.(1[6-9]|2[0-9]|3[01])\\."
)

bad = []
for f in subprocess.run(["git","ls-files"],capture_output=True,text=True,check=True).stdout.split():
    try:
        t = open(f, encoding="utf-8").read()
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        continue
    m = zh_words.search(t)
    if m and f not in zh_exempt:
        bad.append(f"{f} ({m.group()!r})")
    m = claude_md.search(t)
    if m and f not in claude_md_exempt:
        bad.append(f"{f} ({m.group()!r})")
    m = other_words.search(t)
    if m:
        bad.append(f"{f} ({m.group()!r})")
if bad:
    sys.exit("private content in: " + "; ".join(bad))
'

# --- the tool's own tests --------------------------------------------------

echo ""
echo "  running the tool unit tests..."
TEST_LOG="$(mktemp -t spec-drift-tests)"
HIST_LOG="$(mktemp -t spec-drift-history)"
trap 'rm -f "$TEST_LOG" "$HIST_LOG"' EXIT

if (cd skills/spec-drift/tool && python3 -m unittest discover -s tests -t .) >"$TEST_LOG" 2>&1; then
  RAN="$(grep -E "^Ran [0-9]+ test" "$TEST_LOG" | tail -1)"
  if ! grep -qE "^OK$" "$TEST_LOG"; then
    fail "tool unit tests: did not end in a bare OK"
    tail -20 "$TEST_LOG" | sed 's/^/        /'
  elif grep -q "skipped" "$TEST_LOG"; then
    fail "tool unit tests: some tests were skipped"
    grep -n "skipped" "$TEST_LOG" | sed 's/^/        /'
  else
    pass "tool unit tests — $RAN, OK, none skipped"
  fi
else
  fail "tool unit tests failed"
  tail -20 "$TEST_LOG" | sed 's/^/        /'
fi

# --- git history (separate section) -----------------------------------------
#
# This scans the *entire* history, not just the tracked tree, for the same
# family of private content (plus a couple of history-only tells: a leaked
# session-log label, the appeal-system word). Unlike every check above, this
# one is currently EXPECTED to fail -- the history still carries the original
# authorship and some commit bodies from before this repo was extracted for
# publication, and rewriting that history is a separate piece of work. It is
# kept here and reported on its own, so that fixing the working tree above
# does not read as "the repository is clean" when the history is not.

echo ""
echo "  git history (separate from the checks above — expected to FAIL until"
echo "  the history is rewritten for publication):"

git log --all --format='tformat:%H%x01%an <%ae>%x01%B%x02' > "$HIST_LOG"

if python3 - "$HIST_LOG" <<'PYEOF'
import re, sys

path = sys.argv[1]
data = open(path, encoding="utf-8", errors="replace").read()
records = [r for r in data.split("\x02") if r.strip()]

pat = re.compile(
    "haidila[o]"
    "|Qu[Z]hi"
    "|Co[C]o"
    "|Claude[-]Session"
    "|\u7533\u8bc9"   # appeal-system word
)

bad = []
for r in records:
    parts = r.split("\x01", 2)
    if len(parts) != 3:
        continue
    commit, author, body = parts
    commit = commit.strip()
    if pat.search(author) or pat.search(body):
        bad.append((commit[:9], author.strip()))

if bad:
    print("  FAIL  private content in git history:")
    for commit, author in bad:
        print(f"          {commit}  {author}")
    sys.exit(1)
print("  ok    no private content in git history")
PYEOF
then
  :
else
  FAILED=1
  echo "        (expected for now -- see report; the history rewrite is tracked separately)"
fi

# --- verdict ---------------------------------------------------------------

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  VERSION="$(python3 -c 'import json;print(json.load(open(".claude-plugin/plugin.json"))["version"])')"
  TESTS="$(grep -Eo "^Ran [0-9]+" "$TEST_LOG" | tail -1 | cut -d" " -f2)"
  echo "PASS — spec-drift-mngr $VERSION: manifests in sync, skill frontmatter good, no hard-coded paths or private content, $TESTS tool tests OK."
  exit 0
fi
echo "FAIL — one or more checks above did not pass."
exit 1
