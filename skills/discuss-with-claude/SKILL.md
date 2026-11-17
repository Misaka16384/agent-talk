---
name: discuss-with-claude
description: Hold a multi-round discussion with Claude (Claude Code CLI) and report the outcome to the user. Use when the user asks you to discuss something with Claude, ask Claude, get Claude's view, or have Claude critique or check something — e.g. "discuss this with claude", "ask claude", "和 claude 讨论一下", "问问 claude", "让 claude 看看".
---

# Discuss with Claude

Command (installed by agent_talk):

    "{{PYTHON}}" "{{SCRIPT}}" --to claude ...

1. **Write the opening message.** Claude cannot see this conversation, so the message must stand on its own: the question, the background it needs, paths of the relevant files (it can read the current working directory; add `--read-dir <dir>` for anything outside it), your current view, and what you want it to challenge. If the message contains LaTeX, quotes or backslashes, write it to a `.md` file in `{{OUTBOX}}/` first (never in the user's project) and pass `--file <path>` instead of quoting it on the command line.
2. **First round:** `"{{PYTHON}}" "{{SCRIPT}}" --to claude --file <message.md>`. The output ends with `[session: <id>]`, `[scratch: ...]`, `[log: ...]` and `[round complete ...]`.
3. **Later rounds:** the same command plus `--session <id>`; Claude remembers the earlier rounds. A round can take several minutes: give the command at least a 10-minute timeout, run it in the foreground and wait for it to finish. Never start a second call while one is running, and never open a new discussion to retry — retry the same `--session`. If the user names a model, add `--model <name>` (e.g. `opus`, `sonnet`).
4. **When to stop:** follow the user's number of rounds if given; otherwise at most 4 rounds, earlier once you agree or the disagreement is clear. Engage with Claude's arguments each round instead of just agreeing.
5. **Report to the user**, in the user's language: the conclusion or consensus; open disagreements with each side's reasons; points Claude raised that you had missed; your own final judgement; the log path.

Check any factual claim Claude makes (citations, numbers, who proved what) before relying on it. Claude may read files and write only in its scratch folder; it cannot run commands. If the command reports an authentication error, ask the user to run `claude auth login` once in a terminal.
