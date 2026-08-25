#!/usr/bin/env python3
# MANIFEST
# sample_id: CLN-01
# vulns: []
# fp_traps:
#   - lines: "22-22"
#     pattern: "Path.home() read of user config file - normal local preferences access"
#   - lines: "79-80"
#     pattern: "--in-place write_text to a user-named file - explicit local edit requested by the caller"
"""tidy.py - normalize whitespace, line endings, and blank-line runs in notes.

Local-only utility: it reads the text files named on the command line,
applies cosmetic cleanups, and either prints the result or writes it back
when --in-place is given. It performs no network access.
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "tidynotes" / "config.json"

DEFAULTS = {
    "max_consecutive_blank_lines": 1,
    "trim_trailing_whitespace": True,
    "ensure_trailing_newline": True,
    "tab_width": 4,
}


def load_config(path: Path) -> dict:
    """Merge user preferences from the config file over the defaults."""
    config = dict(DEFAULTS)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return config
    try:
        user_config = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"warning: ignoring malformed config {path}: {exc}", file=sys.stderr)
        return config
    for key in DEFAULTS:
        if key in user_config:
            config[key] = user_config[key]
    return config


def tidy_text(text: str, config: dict) -> str:
    """Apply the configured cosmetic cleanups to a single document."""
    if config["tab_width"] > 0:
        text = text.expandtabs(config["tab_width"])
    lines = text.splitlines()
    if config["trim_trailing_whitespace"]:
        lines = [line.rstrip() for line in lines]
    collapsed = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
        else:
            blank_run += 1
        if blank_run <= config["max_consecutive_blank_lines"]:
            collapsed.append(line)
    result = "\n".join(collapsed)
    if config["ensure_trailing_newline"] and result and not result.endswith("\n"):
        result += "\n"
    return result


def process_file(path: Path, config: dict, in_place: bool) -> bool:
    """Tidy one file; return True when the content changed."""
    original = path.read_text(encoding="utf-8")
    tidied = tidy_text(original, config)
    if tidied == original:
        print(f"unchanged: {path}")
        return False
    if in_place:
        path.write_text(tidied, encoding="utf-8")
        print(f"updated:   {path}")
    else:
        sys.stdout.write(tidied)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize whitespace and line endings in plain-text notes."
    )
    parser.add_argument("files", nargs="+", type=Path, help="note files to tidy")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"preferences file location (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="rewrite each file with the tidied content instead of printing",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    for path in args.files:
        if not path.is_file():
            print(f"error: not a file: {path}", file=sys.stderr)
            return 2
        process_file(path, config, args.in_place)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
