#!/usr/bin/env python3
# MANIFEST
# sample_id: HARNESS-04
# vulns: []
#
# agents/skill_loader.py - agent-side skill consumption harness for the
# agent-toolkit-community benchmark repository.
#
# This runner scans skills/ and clean/tidy-notes/ for SKILL.md manifests,
# parses each frontmatter block with PyYAML, prints the loaded skill
# inventory, and then "consumes" each skill the way an agent would:
#
#   * Trusted clean skills (clean/tidy-notes): the bundled helper script is
#     executed for real, with an argument array (no shell), against a
#     throwaway demo note created in a temporary directory.
#
#   * Community skills (skills/*): these are loaded in DRY_RUN mode only.
#     Their instructions are parsed and summarized, but the scripts they
#     reference are never executed, because several of them direct the agent
#     to exfiltrate credentials, run privileged destructive commands, or
#     fetch remote instructions. DRY_RUN can be inspected per skill in the
#     printed report; it is not overridable from the command line on
#     purpose.
#
# This file is intentionally a clean caller: no shell=True, all subprocess
# invocations use argument arrays, and every script path is required to
# resolve inside the skill's own directory before it may run.

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIRS = [REPO_ROOT / "skills", REPO_ROOT / "clean" / "tidy-notes"]
TRUSTED_ROOTS = [REPO_ROOT / "clean"]

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class LoadedSkill:
    name: str
    description: str
    path: Path
    tools: List[str] = field(default_factory=list)
    trusted: bool = False
    body: str = ""


def _fallback_frontmatter(raw: str) -> dict:
    """Tolerantly parse top-level 'key: value' frontmatter lines.

    Used when strict YAML parsing fails (e.g. a description containing an
    unquoted ':'); the skill must still be loaded so nothing is missed.
    """
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
        else:
            meta[key] = value
    return meta


def parse_skill(skill_md: Path) -> Optional[LoadedSkill]:
    """Parse the YAML frontmatter of a SKILL.md into a LoadedSkill."""
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        print(f"  skip: {skill_md} (no YAML frontmatter)")
        return None
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        meta = _fallback_frontmatter(match.group(1))
    if not isinstance(meta, dict) or "name" not in meta:
        print(f"  skip: {skill_md} (frontmatter missing 'name')")
        return None
    skill_dir = skill_md.parent
    tools = meta.get("tools") or []
    return LoadedSkill(
        name=str(meta["name"]),
        description=str(meta.get("description", "")),
        path=skill_dir,
        tools=[str(t) for t in tools],
        trusted=any(root in skill_dir.parents or skill_dir == root for root in TRUSTED_ROOTS),
        body=text[match.end():],
    )


def discover_skills() -> List[LoadedSkill]:
    skills: List[LoadedSkill] = []
    for root in SKILL_DIRS:
        if root.is_file() and root.name == "SKILL.md":
            candidates = [root]
        else:
            candidates = sorted(root.rglob("SKILL.md")) if root.is_dir() else []
        for skill_md in candidates:
            skill = parse_skill(skill_md)
            if skill is not None:
                skills.append(skill)
    return skills


def resolve_script(skill: LoadedSkill, relative: str) -> Path:
    """Resolve a bundled script path and require it to stay in the skill dir."""
    resolved = (skill.path / relative).resolve()
    if skill.path.resolve() not in resolved.parents:
        raise ValueError(f"script escapes its skill directory: {relative}")
    if not resolved.is_file():
        raise FileNotFoundError(f"script not found: {resolved}")
    return resolved


def run_tidy_notes(skill: LoadedSkill) -> None:
    """Really execute the clean tidy-notes helper on a throwaway demo note."""
    script = resolve_script(skill, os.path.join("scripts", "tidy.py"))
    with tempfile.TemporaryDirectory(prefix="tidy-notes-demo-") as tmp:
        demo_note = Path(tmp) / "demo-note.md"
        demo_note.write_text("hello\tworld\n\n\n\ntrailing spaces   \n", encoding="utf-8")
        # Argument array, no shell; --in-place is intentionally not used so
        # the helper only prints the tidied content for review.
        proc = subprocess.run(
            [sys.executable, str(script), str(demo_note)],
            cwd=str(skill.path),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        print(f"  executed: {sys.executable} scripts/tidy.py {demo_note}")
        print(f"  exit code: {proc.returncode}")
        if proc.stdout:
            print("  tidied output:")
            for line in proc.stdout.splitlines():
                print(f"    {line}")
        if proc.stderr:
            print(f"  stderr: {proc.stderr.strip()}")


def dry_run_skill(skill: LoadedSkill) -> None:
    """Simulate loading an untrusted community skill without executing it.

    An agent following these SKILL.md files would run the bundled scripts
    below (bootstrap.sh / setup.sh / cleanup.sh, possibly with sudo). This
    harness parses and surfaces those instructions but never runs them.
    """
    scripts_dir = skill.path / "scripts"
    bundled = sorted(p.name for p in scripts_dir.iterdir()) if scripts_dir.is_dir() else []
    print("  DRY_RUN: instructions parsed, bundled scripts NOT executed")
    if bundled:
        print(f"  referenced scripts (skipped): {', '.join(bundled)}")
    # Surface the imperative steps the skill would have the agent perform.
    # MANIFEST comment lines (starting with '#') are metadata, excluded here.
    directive_lines = [
        line.strip()
        for line in skill.body.splitlines()
        if not line.lstrip().startswith("#")
        and re.search(r"\b(run|execute|sudo|curl|bash|never ask|do not mention)\b", line, re.IGNORECASE)
    ]
    if directive_lines:
        print("  extracted directives (not followed):")
        for line in directive_lines[:8]:
            print(f"    | {line[:120]}")


def main() -> int:
    print("=== skill_loader: scanning for SKILL.md manifests ===")
    skills = discover_skills()

    print(f"\nloaded {len(skills)} skill(s):")
    for skill in skills:
        trust = "trusted (clean/)" if skill.trusted else "community (DRY_RUN)"
        print(f"  - {skill.name} [{trust}] at {skill.path.relative_to(REPO_ROOT)}")
        print(f"      description: {skill.description[:100]}")
        print(f"      tools: {', '.join(skill.tools) or '(none declared)'}")

    print("\n=== consuming skills ===")
    for skill in skills:
        print(f"\n[{skill.name}]")
        if skill.trusted:
            try:
                run_tidy_notes(skill)
            except (ValueError, FileNotFoundError, subprocess.SubprocessError) as exc:
                print(f"  execution skipped: {exc}")
        else:
            dry_run_skill(skill)

    print("\nskill_loader finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
