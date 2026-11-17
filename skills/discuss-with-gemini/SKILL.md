---
name: discuss-with-gemini
description: Hold a multi-round discussion with Gemini (Antigravity CLI, `agy`) and report the outcome to the user. Use when the user asks you to discuss something with Gemini, ask Gemini, get Gemini's view, or have Gemini critique or check something — e.g. "discuss this with gemini", "ask gemini", "和 gemini 讨论一下", "问问 gemini", "让 gemini 看看".
---

# Discuss with Gemini

Command (installed by agent_talk):

    "{{PYTHON}}" "{{SCRIPT}}" --to gemini ...

1. **Write the opening message.** Gemini cannot see this conversation, so the message must stand on its own: the question, the background it needs, paths of the relevant files (it can read the current working directory; add `--read-dir <dir>` for anything outside it), your current view, and what you want it to challenge. If the message contains LaTeX, quotes or backslashes, write it to a `.md` file in `{{OUTBOX}}/` first (never in the user's project) and pass `--file <path>` instead of quoting it in the shell.
2. **First round:** `"{{PYTHON}}" "{{SCRIPT}}" --to gemini --file <message.md>`. The output ends with `[session: <id>]`, `[scratch: ...]`, `[log: ...]` and `[round complete ...]`.
3. **Later rounds:** the same command plus `--session <id>`; Gemini remembers the earlier rounds. A round can take several minutes: give the command a 10-minute timeout and wait for it to finish. Never start a second call while one is running, and never open a new discussion to retry — retry the same `--session`. If the user names a model, add `--model <id>` (`agy models` lists ids).
4. **When to stop:** follow the user's number of rounds if given; otherwise at most 4 rounds, earlier once you agree or the disagreement is clear. Engage with Gemini's arguments each round instead of just agreeing.
5. **Report to the user**, in the user's language: the conclusion or consensus; open disagreements with each side's reasons; points Gemini raised that you had missed; your own final judgement; the log path.

Check any factual claim Gemini makes (citations, numbers, who proved what) before relying on it. Gemini may read files and write only in its scratch folder; it cannot run commands.
