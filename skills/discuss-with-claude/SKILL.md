---
name: discuss-with-claude
description: Hold a multi-round discussion with Claude (Claude Code CLI) and report the outcome to the user. Use when the user asks you to discuss something with Claude, ask Claude, get Claude's view, or have Claude critique or check something — e.g. "discuss this with claude", "ask claude", "和 claude 讨论一下", "问问 claude", "让 claude 看看".
---

# Discuss with Claude

Command (installed by agent_talk):

    "{{PYTHON}}" "{{SCRIPT}}" --to claude ...

1. **Write the opening message.** Claude cannot see this conversation, so the message must stand on its own: the question, the background it needs, paths of the relevant files (it can read the current working directory; add `--read-dir <dir>` for anything outside it), your current view, and what you want it to challenge. If the message contains LaTeX, quotes or backslashes, write it to a `.md` file in `{{OUTBOX}}/` first (never in the user's project) and pass `--file <path>` instead of quoting it on the command line.
2. **First round:** `"{{PYTHON}}" "{{SCRIPT}}" --to claude --file <message.md>`. The output ends with `[session: <id>]`, `[scratch: ...]`, `[log: ...]` and `[round complete ...]`.
3. **Later rounds:** the same command plus `--session <id>`; Claude remembers the earlier rounds. A round can take several minutes: give the command at least a 10-minute timeout, run it in the foreground and wait for it to finish. Never start a second call while one is running, and never open a new discussion to retry — retry the same `--session`. If the user names a model, add `--model <name>` (e.g. `opus`, `sonnet`). Only if the user asks to let the other side write files, add `--write-dir <dir>` on every round that needs it.
4. **Memory switch (`--with-memory`, first round only).** By default Claude starts clean: it does not load the user's CLAUDE.md files, its auto-memory, or the user's Claude settings, so it knows only what your message tells it. Add `--with-memory` to the **first** round when the user's Claude history matters — for example both of you are working on the same paper or project, or the user says Claude should use its memory. Then:
   - Claude loads the user's CLAUDE.md files and the auto-memory of the current working directory's project (past decisions, preferences, project status). Run the command from that project's folder.
   - Its writes are still limited to its scratch folder; it cannot change the project, its memory or its settings, and it still cannot run commands.
   - The user's own Claude settings and hooks apply to that run.
   - Claude is told to keep anything the user marked confidential out of its replies, but the memory can still shape what it says to you.
   - The choice is fixed for the whole discussion: adding or dropping the flag in later rounds changes nothing. The output shows `[memory: on]` or `[memory: off]`.
5. **When to stop:** follow the user's number of rounds if given; otherwise at most 4 rounds, earlier once you agree or the disagreement is clear. Engage with Claude's arguments each round instead of just agreeing.
6. **Report to the user**, in the user's language: the conclusion or consensus; open disagreements with each side's reasons; points Claude raised that you had missed; your own final judgement; the log path.

Check any factual claim Claude makes (citations, numbers, who proved what) before relying on it. Claude may read files and write only in its scratch folder; it cannot run commands. If the command reports an authentication error, ask the user to run `claude auth login` once in a terminal.
