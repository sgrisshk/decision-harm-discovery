import re
import subprocess
from pathlib import Path

REPO = Path("<repo>/worktrees/agent-ab783e08609be4ffa")
NUM_PATTERN = r"(?<![0-9])5(?:00[1-9]|0[1-2][0-9]|030)(?![0-9])"

# Wide "seed" proximity (either order, generous 40-char gap) -- catches "SEEDS = list(range(5001,"
# style and "`5001-5030`, reserved for..." style alike.
seed_wide = re.compile(
    rf"(?i)seed[a-z_\-]*.{{0,40}}({NUM_PATTERN})|({NUM_PATTERN}).{{0,40}}seed", re.DOTALL
)
# Explicit range-notation substrings this project's own docs/scripts actually use for seed ranges
# (see docs/benchmark/task-107-freeze-manifest.md: "4001-4030", "SEEDS = list(range(4101, 4131))").
range_literal = re.compile(
    rf"({NUM_PATTERN})\s*[-,]\s*({NUM_PATTERN})|range\(\s*({NUM_PATTERN})"
)


def scan_text(text: str, label_prefix: str, out: list) -> None:
    for i, line in enumerate(text.splitlines(), start=1):
        if seed_wide.search(line) or range_literal.search(line):
            out.append((label_prefix, i, line.strip()[:200]))


proc = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
tracked = [REPO / line for line in proc.stdout.splitlines() if line]
wt_hits: list = []
for p in tracked:
    rel = str(p.relative_to(REPO))
    if not p.is_file():
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, PermissionError, OSError):
        continue
    scan_text(text, rel, wt_hits)

print(f"=== Tracked files: wide seed-proximity OR range-literal hits: {len(wt_hits)} ===")
for h in wt_hits:
    print(" ", h)

proc2 = subprocess.run(
    ["git", "log", "--all", "-p", "--", "."],
    cwd=REPO, capture_output=True, text=True, errors="replace",
)
cur_file = ""
history_hits: list = []
for line in proc2.stdout.splitlines():
    if line.startswith("+++ b/") or line.startswith("--- a/"):
        cur_file = line[6:]
        continue
    if not line or line[0] not in "+-" or line.startswith("+++") or line.startswith("---"):
        continue
    if seed_wide.search(line) or range_literal.search(line):
        history_hits.append((cur_file, line.strip()[:200]))

print(f"\n=== git history content lines: wide seed-proximity OR range-literal hits: {len(history_hits)} ===")
for h in history_hits[:400]:
    print(" ", h)
