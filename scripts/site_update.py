#!/usr/bin/env python3
"""Post a plain-English progress note to the Orrin page on ricmassey.com.

The note lands in RicsWebsite/orrin-updates.js (newest first), which the
"PROGRESS NOTES" region of orrin.html renders. Write for friends and family:
what was tried, what happened, what's next. Mechanisms, not feelings
(CLAUDE.md golden rule 4).

    python scripts/site_update.py --kind "run result" \\
        --title "Run 13: ..." --body "..." --href https://github.com/ric-massey/orrin_v3/...

By default it only edits the local site checkout. --publish pushes JUST this
note: it commits on top of origin/main in a throwaway worktree, runs the site's
own check for the file, and pushes, so anything else sitting unpushed in the
site checkout (the weekly board-sessions commit, someone's half-done room) is
not published along with it. A push to the site's main IS a publish.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, Optional

KINDS = ("run result", "build", "design", "note")
MARKER = "window.ORRIN_UPDATES = ["
FILE = "orrin-updates.js"
HREF_PREFIX = "https://github.com/ric-massey/orrin_v3/"


def site_dir() -> Path:
    return Path(os.environ.get("ORRIN_SITE_DIR") or Path.home() / "RicsWebsite")


def make_entry(kind: str, title: str, body: str, href: Optional[str] = None,
               when: Optional[str] = None) -> Dict[str, str]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    title, body = title.strip(), " ".join(body.split())
    if not title or not body:
        raise ValueError("title and body are required")
    if any(c in title + body for c in "<>"):
        raise ValueError("no markup: the page renders text only")
    if href and not href.startswith(HREF_PREFIX):
        raise ValueError(f"href must point into the Orrin repo ({HREF_PREFIX}...)")
    entry = {"date": when or date.today().isoformat(), "kind": kind, "title": title, "body": body}
    if href:
        entry["href"] = href
    return entry


def insert_entry(src: str, entry: Dict[str, str]) -> str:
    """Return `src` with `entry` as the first element of window.ORRIN_UPDATES."""
    i = src.find(MARKER)
    if i < 0:
        raise ValueError(f"{FILE} has no '{MARKER}' line")
    at = i + len(MARKER)
    lines = ["  {"] + [f"    {k}: {json.dumps(v, ensure_ascii=False)}," for k, v in entry.items()] + ["  },"]
    return src[:at] + "\n" + "\n".join(lines) + src[at:]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def publish(site: Path, entry: Dict[str, str]) -> str:
    """Commit just this note on top of origin/main and push it. Returns the commit sha."""
    _git(site, "fetch", "-q", "origin")
    tmp = Path(tempfile.mkdtemp(prefix="orrin-site-"))
    wt = tmp / "site"
    try:
        _git(site, "worktree", "add", "-q", "--detach", str(wt), "origin/main")
        f = wt / FILE
        f.write_text(insert_entry(f.read_text(encoding="utf-8"), entry), encoding="utf-8")
        check = wt / ".github" / "test" / "orrin-updates.mjs"
        if check.exists() and shutil.which("node"):
            subprocess.run(["node", str(check)], cwd=wt, check=True)
        _git(wt, "add", FILE)
        _git(wt, "commit", "-q", "-m", f"ORRIN: {entry['title']}")
        sha = _git(wt, "rev-parse", "--short", "HEAD").strip()
        _git(wt, "push", "-q", "origin", "HEAD:main")
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=site,
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
    # Bring the local checkout along when that is safe; otherwise leave it for its owner.
    try:
        _git(site, "fetch", "-q", "origin")
        if not _git(site, "status", "--porcelain").strip():
            _git(site, "rebase", "-q", "origin/main")
    except subprocess.CalledProcessError:
        print(f"note published as {sha}; the local site checkout was left as it was "
              f"(rebase it onto origin/main yourself)", file=sys.stderr)
    return sha


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--href")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--publish", action="store_true", help="push just this note to the live site")
    a = ap.parse_args(argv)
    entry = make_entry(a.kind, a.title, a.body, a.href, a.date)
    site = site_dir()
    if not (site / FILE).exists():
        print(f"no {FILE} under {site} (set ORRIN_SITE_DIR)", file=sys.stderr)
        return 2
    if a.publish:
        print(f"published {publish(site, entry)}: {entry['title']}")
    else:
        f = site / FILE
        f.write_text(insert_entry(f.read_text(encoding="utf-8"), entry), encoding="utf-8")
        print(f"added to {f} (not published; re-run with --publish, or commit it yourself)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
