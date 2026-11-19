#!/usr/bin/env python3
"""agent_talk — let Claude Code and Gemini (Antigravity CLI, `agy`) hold a multi-round discussion.

The caller is whichever agent the user is talking to. It runs this script once per
message. The other side is started headless and resumes its own conversation by id,
so it remembers earlier rounds.

    python agent_talk.py --to gemini "first message"            # start a discussion
    python agent_talk.py --to gemini --file msg.md               # message from a file
    python agent_talk.py --to gemini --session <id> "next round" # continue it
    python agent_talk.py --to claude ...                         # the other direction
    python agent_talk.py --to claude --with-memory ...           # Claude with the user's memory
    python agent_talk.py --doctor                                # check the setup

The other side may read the working directory (plus any --read-dir) and the web, may
write only in a private scratch folder, and may not run commands. See README.md for
how far each side enforces this.

Prints the reply, then `[session: ...]`, `[scratch: ...]` and `[log: ...]` lines.
Every exchange is appended to <AGENT_TALK_HOME>/logs/ (default ~/.agent_talk).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

__version__ = "1.2.0"

HOME = os.environ.get("AGENT_TALK_HOME") or os.path.join(os.path.expanduser("~"), ".agent_talk")
LOGS = os.path.join(HOME, "logs")
SCRATCH = os.path.join(HOME, "scratch")
SESSIONS = os.path.join(HOME, "sessions.json")

LABEL = {"claude": "Claude", "agy": "Gemini"}
TARGET = {"claude": "claude", "gemini": "agy", "agy": "agy"}

# Windows caps a command line at 32767 characters, and the message travels as one argument.
MAX_ARG = 30000 if os.name == "nt" else 1000000

PREAMBLE = (
    "[Discussion request. The sender is another AI assistant, {caller}, not the user. "
    "{caller}'s user asked the two of you to discuss the question below; {caller} will report "
    "the outcome back to the user.\n"
    "Rules: you may read files and look things up. You may create or edit files ONLY inside your "
    "scratch folder: {scratch}\n"
    "Do not modify anything else and do not run commands. Answer directly and concretely, "
    "disagree openly and give reasons, and mark what you are unsure of. "
    "Reply in the language the question is written in.]\n\n"
)

MEMORY_NOTE = (
    "[You have your user's own Claude memory and instructions loaded. Use them as background, but keep "
    "anything they mark as confidential or private out of your replies: your replies go to {caller}, "
    "another vendor's AI.]\n\n"
)

# Variables that a host Claude Code session exports. A child `claude` that inherits them
# tries the host's login and fails, so they are dropped -- only when we are inside one.
HOST_VARS_PREFIX = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_")
HOST_VARS = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT")


def fwd(path):
    return os.path.abspath(path).replace("\\", "/")


def inside(path, root):
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def claude_path_rule(path):
    """Claude Code permission-rule path for a directory: ~/... under home, //... otherwise."""
    home = os.path.expanduser("~")
    if inside(path, home):
        rel = os.path.relpath(path, home).replace("\\", "/")
        return "~/" + rel
    p = fwd(path)
    return "//" + p.lstrip("/")


def claude_config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _blocks_write(d, scratch, write_dirs):
    """True if a write-deny on directory d is safe, i.e. it does not cover the scratch or a write dir."""
    return not inside(scratch, d) and not any(inside(w, d) for w in write_dirs)


def claude_argv(session, model, scratch, read_dirs, message, with_memory=False, write_dirs=()):
    allow = ["Write(%s/**)" % claude_path_rule(scratch), "Edit(%s/**)" % claude_path_rule(scratch),
             "WebFetch", "WebSearch"]
    for w in write_dirs:
        allow += ["Write(%s/**)" % claude_path_rule(w), "Edit(%s/**)" % claude_path_rule(w)]
    if with_memory:
        # Load everything a normal session loads (CLAUDE.md files, auto-memory, settings,
        # hooks). dontAsk denies whatever is not explicitly allowed; the deny rules keep the
        # working directories and Claude's own config/memory folder read-only even if the
        # user's settings allow edits there.
        deny = []
        for d in [os.getcwd()] + list(read_dirs) + [claude_config_dir()]:
            if _blocks_write(d, scratch, write_dirs):
                deny += ["Write(%s/**)" % claude_path_rule(d), "Edit(%s/**)" % claude_path_rule(d)]
        permissions = {"allow": allow, "deny": deny}
        mode = ["--permission-mode", "dontAsk", "--permission-prompts", "none"]
    else:
        # --restricted: no command-running tools, user/project settings, CLAUDE.md and
        # auto-memory ignored, file tools confined to the working directories.
        permissions = {"allow": allow}
        mode = ["--restricted"]
    argv = ([shutil.which("claude") or "claude", "-p", "--output-format", "json"] + mode +
            ["--strict-mcp-config", "--tools", "Read,Grep,Glob,WebFetch,WebSearch,Write,Edit",
             "--settings", json.dumps({"permissions": permissions}), "--add-dir", scratch])
    for d in list(read_dirs) + list(write_dirs):
        argv += ["--add-dir", d]
    if session:
        argv += ["--resume", session]
    if model:
        argv += ["--model", model]
    return argv + ["--", message]


def agy_argv(session, model, scratch, read_dirs, message, with_memory=False, write_dirs=()):
    deny = ["command(*)", "mcp(*)", "execute_url(*)"]
    for d in [os.getcwd()] + list(read_dirs):
        # a deny on a parent of the scratch (or of a write dir) would block it too
        if _blocks_write(d, scratch, write_dirs):
            deny.append("write_file(%s)" % fwd(d))
    settings = {"toolPermission": "request-review",
                "permissions": {"allow": ["read_url(*)"], "ask": [], "deny": deny}}
    argv = [shutil.which("agy") or "agy", "--settings", json.dumps(settings),
            "--add-dir", scratch, "--output-format", "json"]
    for d in list(read_dirs) + list(write_dirs):
        argv += ["--add-dir", d]
    if session:
        argv += ["--conversation", session]
    if model:
        argv += ["--model", model]
    return argv + ["-p", message]          # agy's -p takes the prompt as its value: keep it last


def child_env(target):
    env = dict(os.environ)
    env["AGENT_TALK_DEPTH"] = "1"
    if target == "claude" and "CLAUDECODE" in env:
        for k in list(env):
            if k in HOST_VARS or k.startswith(HOST_VARS_PREFIX):
                env.pop(k)
    return env


def load_sessions():
    try:
        with open(SESSIONS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def session_record(sessions, key):
    rec = sessions.get(key)
    if isinstance(rec, str):            # written by 1.0.x: just the scratch path
        rec = {"scratch": rec}
    return rec or {}


def save_session(key, record):
    data = load_sessions()
    data[key] = record
    tmp = SESSIONS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, SESSIONS)


def run_cmd(argv, timeout=30, env=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)


def doctor():
    ok = True
    print("agent_talk %s, Python %s" % (__version__, sys.version.split()[0]))
    if sys.version_info < (3, 7):
        print("  [x] Python 3.7 or newer is required"); ok = False
    for exe, label in (("claude", "Claude Code CLI"), ("agy", "Antigravity CLI")):
        path = shutil.which(exe)
        if not path:
            print("  [ ] %s (`%s`) not found on PATH" % (label, exe)); continue
        code, out, err = run_cmd([path, "--version"])
        print("  [ok] %s: %s" % (label, (out or err).splitlines()[0] if (out or err) else path))
        if exe == "claude":
            code, out, _ = run_cmd([path, "auth", "status"], env=child_env("claude"))
            try:
                logged = json.loads(out).get("loggedIn")
            except ValueError:
                logged = None
            if logged:
                print("  [ok] claude CLI is logged in")
            else:
                ok = False
                print("  [x] claude CLI is not logged in: run `claude auth login` once in a terminal "
                      "(a Claude desktop-app login is not shared with the CLI)")
    print("  data folder: %s" % HOME)
    return ok


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Discuss with the other agent (Claude <-> Gemini/agy).")
    ap.add_argument("--to", choices=sorted(TARGET), help="who to talk to")
    ap.add_argument("--session", help="id printed by the previous round; omit to start a new discussion")
    ap.add_argument("--file", help="read the message from this UTF-8 file")
    ap.add_argument("--model", help="model for the other side (`agy models` lists Gemini ids)")
    ap.add_argument("--read-dir", action="append", default=[],
                    help="extra directory the other side may read (repeatable)")
    ap.add_argument("--write-dir", action="append", default=[],
                    help="extra directory the other side may also write in (repeatable; opt-in). "
                         "A write dir inside the working directory or a --read-dir lifts the write "
                         "block on that parent too, so check `git status` afterwards. Commands stay blocked.")
    ap.add_argument("--with-memory", action="store_true",
                    help="Claude only, first round only: load the user's CLAUDE.md files, auto-memory, "
                         "settings and hooks (default: a clean Claude without them)")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds to wait for one round")
    ap.add_argument("--doctor", action="store_true", help="check the setup and exit")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("message", nargs="?")
    a = ap.parse_args()

    if a.doctor:
        sys.exit(0 if doctor() else 1)
    if not a.to:
        ap.error("--to is required")
    if os.environ.get("AGENT_TALK_DEPTH"):
        sys.exit("agent_talk: you were started by another agent for a discussion, so you cannot "
                 "forward it to a third. Answer directly.")
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            message = f.read()
    elif a.message:
        message = a.message
    else:
        ap.error("give the message as an argument or with --file")

    target = TARGET[a.to]
    callee, caller = LABEL[target], LABEL["agy" if target == "claude" else "claude"]
    read_dirs = [os.path.abspath(d) for d in a.read_dir]
    write_dirs = [os.path.abspath(d) for d in a.write_dir]
    for w in write_dirs:
        os.makedirs(w, exist_ok=True)
    if a.with_memory and target != "claude":
        sys.exit("agent_talk: --with-memory only applies when talking to Claude "
                 "(Gemini always loads its own GEMINI.md).")

    notes = []
    if a.session:
        rec = session_record(load_sessions(), "%s:%s" % (target, a.session))
        scratch = rec.get("scratch") or os.path.join(SCRATCH, "%s-%s" % (target, a.session))
        # Claude keeps the system prompt of a conversation's first request, so the
        # memory choice is fixed at round one and later rounds follow the record.
        with_memory = rec["memory"] if "memory" in rec else a.with_memory
        if a.with_memory and not with_memory:
            notes.append("[note: this discussion started without --with-memory; memory can only be "
                         "chosen in the first round, so it continues without it]")
        sent = message
    else:
        with_memory = a.with_memory
        scratch = os.path.join(SCRATCH, "%s-%s" % (target, time.strftime("%Y%m%d-%H%M%S")))
        sent = PREAMBLE.format(caller=caller, scratch=fwd(scratch))
        if with_memory:
            sent += MEMORY_NOTE.format(caller=caller)
        sent += message
    if write_dirs:
        sent = ("[For this round you may ALSO create or edit files inside: %s. Still do not modify "
                "anything else and do not run commands.]\n\n" % ", ".join(fwd(w) for w in write_dirs)) + sent
    os.makedirs(scratch, exist_ok=True)
    if len(sent) > MAX_ARG:
        sys.exit("agent_talk: the message is %d characters, more than one command line can carry "
                 "(%d). Put the bulk in a file the other side can read and send its path instead."
                 % (len(sent), MAX_ARG))

    build = claude_argv if target == "claude" else agy_argv
    argv = build(a.session, a.model, scratch, read_dirs, sent, with_memory, write_dirs=write_dirs)
    if not os.path.isabs(argv[0]):
        sys.exit("agent_talk: `%s` is not on PATH." % argv[0])
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=child_env(target), timeout=a.timeout)
    except subprocess.TimeoutExpired:
        sys.exit("agent_talk: %s gave no answer within %d s. Retry the same round with the same "
                 "--session (or a larger --timeout); do not start a new discussion." % (callee, a.timeout))
    try:
        out = json.loads(p.stdout)
    except ValueError:
        sys.exit("agent_talk: %s did not return JSON (exit %s).\nstdout: %s\nstderr: %s"
                 % (callee, p.returncode, p.stdout[-1500:], p.stderr[-1500:]))

    if target == "claude":
        sid, reply, failed = out.get("session_id"), out.get("result") or "", out.get("is_error")
    else:
        sid, reply = out.get("conversation_id"), out.get("response") or ""
        failed = out.get("status") != "SUCCESS"
    if failed or not sid:
        hint = ""
        if target == "claude" and "authenticat" in (reply + p.stderr).lower():
            hint = "\nRun `claude auth login` once in a terminal, then retry."
        sys.exit("agent_talk: %s failed: %s%s" % (callee, (reply or p.stderr)[-1500:], hint))

    save_session("%s:%s" % (target, sid), {"scratch": scratch, "memory": with_memory})
    os.makedirs(LOGS, exist_ok=True)
    log = os.path.join(LOGS, "%s-%s.md" % (target, sid))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log, "a", encoding="utf-8") as f:
        f.write("## %s -> %s  (%s)\n\n%s\n\n## %s\n\n%s\n\n"
                % (caller, callee, stamp, message.strip(), callee, reply.strip()))

    print(reply.strip())
    print()
    for note in notes:
        print(note)
    print("[session: %s]" % sid)
    if target == "claude":
        print("[memory: %s]" % ("on -- the user's CLAUDE.md and auto-memory are loaded" if with_memory else "off"))
    print("[scratch: %s]" % scratch)
    print("[log: %s]" % log)
    print("[round complete -- continue with: --to %s --session %s]" % (a.to, sid))


if __name__ == "__main__":
    main()
