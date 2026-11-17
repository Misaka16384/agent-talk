#!/usr/bin/env python3
"""agent_talk — let Claude Code and Gemini (Antigravity CLI, `agy`) hold a multi-round discussion.

The caller is whichever agent the user is talking to. It runs this script once per
message. The other side is started headless and resumes its own conversation by id,
so it remembers earlier rounds.

    python agent_talk.py --to gemini "first message"            # start a discussion
    python agent_talk.py --to gemini --file msg.md               # message from a file
    python agent_talk.py --to gemini --session <id> "next round" # continue it
    python agent_talk.py --to claude ...                         # the other direction
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

__version__ = "1.0.0"

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


def claude_argv(session, model, scratch, read_dirs, message):
    allow = ["Write(%s/**)" % claude_path_rule(scratch), "Edit(%s/**)" % claude_path_rule(scratch),
             "WebFetch", "WebSearch"]
    argv = [shutil.which("claude") or "claude", "-p", "--output-format", "json",
            # --restricted: no command-running tools, user/project settings ignored,
            # file tools confined to the working directories.
            "--restricted", "--strict-mcp-config",
            "--tools", "Read,Grep,Glob,WebFetch,WebSearch,Write,Edit",
            "--settings", json.dumps({"permissions": {"allow": allow}}),
            "--add-dir", scratch]
    for d in read_dirs:
        argv += ["--add-dir", d]
    if session:
        argv += ["--resume", session]
    if model:
        argv += ["--model", model]
    return argv + ["--", message]


def agy_argv(session, model, scratch, read_dirs, message):
    deny = ["command(*)", "mcp(*)", "execute_url(*)"]
    for d in [os.getcwd()] + list(read_dirs):
        if not inside(scratch, d):          # a deny on a parent of the scratch would block it too
            deny.append("write_file(%s)" % fwd(d))
    settings = {"toolPermission": "request-review",
                "permissions": {"allow": ["read_url(*)"], "ask": [], "deny": deny}}
    argv = [shutil.which("agy") or "agy", "--settings", json.dumps(settings),
            "--add-dir", scratch, "--output-format", "json"]
    for d in read_dirs:
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


def save_session(key, scratch):
    data = load_sessions()
    data[key] = scratch
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

    sessions = load_sessions()
    if a.session:
        scratch = sessions.get("%s:%s" % (target, a.session)) or os.path.join(SCRATCH, "%s-%s" % (target, a.session))
        sent = message
    else:
        scratch = os.path.join(SCRATCH, "%s-%s" % (target, time.strftime("%Y%m%d-%H%M%S")))
        sent = PREAMBLE.format(caller=caller, scratch=fwd(scratch)) + message
    os.makedirs(scratch, exist_ok=True)
    if len(sent) > MAX_ARG:
        sys.exit("agent_talk: the message is %d characters, more than one command line can carry "
                 "(%d). Put the bulk in a file the other side can read and send its path instead."
                 % (len(sent), MAX_ARG))

    build = claude_argv if target == "claude" else agy_argv
    argv = build(a.session, a.model, scratch, read_dirs, sent)
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

    save_session("%s:%s" % (target, sid), scratch)
    os.makedirs(LOGS, exist_ok=True)
    log = os.path.join(LOGS, "%s-%s.md" % (target, sid))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log, "a", encoding="utf-8") as f:
        f.write("## %s -> %s  (%s)\n\n%s\n\n## %s\n\n%s\n\n"
                % (caller, callee, stamp, message.strip(), callee, reply.strip()))

    print(reply.strip())
    print()
    print("[session: %s]" % sid)
    print("[scratch: %s]" % scratch)
    print("[log: %s]" % log)
    print("[round complete -- continue with: --to %s --session %s]" % (a.to, sid))


if __name__ == "__main__":
    main()
