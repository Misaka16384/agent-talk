#!/usr/bin/env python3
"""One-step installer for agent_talk.

    python install.py              # install for every agent found (Claude Code and/or agy)
    python install.py --only claude
    python install.py --uninstall

Each side gets one skill folder holding SKILL.md and its own copy of agent_talk.py,
so the clone can be deleted after installing. Re-running upgrades in place.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent_talk  # noqa: E402

MARKER = ".agent_talk"


def sides(args):
    home = os.path.expanduser("~")
    claude_dir = args.claude_dir or os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude"), "skills")
    agy_dir = args.agy_dir or os.path.join(home, ".gemini", "config", "skills")
    found = {
        "claude": bool(shutil.which("claude")) or os.path.isdir(os.path.dirname(claude_dir)),
        "agy": bool(shutil.which("agy")) or os.path.isdir(os.path.dirname(agy_dir)),
    }
    table = [("claude", "Claude Code", claude_dir, "discuss-with-gemini"),
             ("agy", "Antigravity CLI (agy)", agy_dir, "discuss-with-claude")]
    for key, label, skills_dir, skill in table:
        if args.only and args.only != key:
            continue
        yield key, label, skills_dir, skill, found[key]


def ours(path):
    return os.path.isfile(os.path.join(path, MARKER))


def install_one(label, skills_dir, skill, force):
    dest = os.path.join(skills_dir, skill)
    if os.path.exists(dest):
        if not (ours(dest) or force):
            print("  [skip] %s exists and was not installed by agent_talk; rerun with --force to replace it" % dest)
            return False
        shutil.rmtree(dest)
    os.makedirs(dest)
    script = os.path.join(dest, "agent_talk.py")
    shutil.copy2(os.path.join(HERE, "agent_talk.py"), script)
    with open(os.path.join(HERE, "skills", skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    outbox = os.path.join(agent_talk.HOME, "outbox")
    os.makedirs(outbox, exist_ok=True)
    text = (text.replace("{{PYTHON}}", sys.executable.replace("\\", "/"))
                .replace("{{SCRIPT}}", script.replace("\\", "/"))
                .replace("{{OUTBOX}}", outbox.replace("\\", "/")))
    with open(os.path.join(dest, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(os.path.join(dest, MARKER), "w", encoding="utf-8") as f:
        f.write(agent_talk.__version__ + "\n")
    print("  [ok] %s: skill `%s` -> %s" % (label, skill, dest))
    return True


def main():
    ap = argparse.ArgumentParser(description="Install agent_talk skills for Claude Code and agy.")
    ap.add_argument("--only", choices=["claude", "agy"], help="install for one side only")
    ap.add_argument("--uninstall", action="store_true", help="remove the installed skills")
    ap.add_argument("--force", action="store_true", help="replace a same-named skill folder not made by agent_talk")
    ap.add_argument("--claude-dir", help="Claude Code skills folder (default ~/.claude/skills)")
    ap.add_argument("--agy-dir", help="agy skills folder (default ~/.gemini/config/skills)")
    args = ap.parse_args()

    if sys.version_info < (3, 7):
        sys.exit("agent_talk needs Python 3.7 or newer.")

    if args.uninstall:
        for key, label, skills_dir, skill, _ in sides(args):
            dest = os.path.join(skills_dir, skill)
            if ours(dest):
                shutil.rmtree(dest)
                print("  [ok] removed %s" % dest)
            elif os.path.exists(dest):
                print("  [skip] %s was not installed by agent_talk" % dest)
        print("Discussion logs and scratch folders are kept in %s; delete it by hand if you like." % agent_talk.HOME)
        return

    print("Installing agent_talk %s" % agent_talk.__version__)
    installed = 0
    for key, label, skills_dir, skill, found in sides(args):
        if not found and not args.only:
            print("  [skip] %s not found" % label)
            continue
        installed += install_one(label, skills_dir, skill, args.force)
    if not installed:
        sys.exit("Nothing installed.")
    print()
    ok = agent_talk.doctor()
    print()
    print("Done. Start a NEW session in Claude Code or agy, then say for example:")
    print('  "discuss this with gemini"  /  "和 claude 讨论一下"')
    if not ok:
        print("Fix the [x] items above first.")


if __name__ == "__main__":
    main()
