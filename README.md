# agent_talk

Let **Claude Code** and **Gemini (Antigravity CLI, `agy`)** discuss a question with each other over several rounds, then report back to you.

While you are working in one of them, say *"discuss this with gemini"* (or *"和 claude 讨论一下"* on the other side). The agent you are talking to writes a self-contained opening message and starts the other one headless. It keeps the exchange going for a few rounds, then tells you the consensus, the open disagreements, and its own verdict.

[中文说明](README.zh-CN.md)

## Install

Requirements: Python 3.7+, plus [Claude Code](https://code.claude.com) and/or the [Antigravity CLI](https://antigravity.google) (`agy`) on your `PATH`.

macOS / Linux / Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1 | iex
```

Or from a clone:

```bash
git clone https://github.com/Misaka16384/agent-talk
python agent-talk/install.py
```

The installer adds one skill to each agent it finds:

| Agent | Skill | Location |
|---|---|---|
| Claude Code | `discuss-with-gemini` | `~/.claude/skills/` (or `$CLAUDE_CONFIG_DIR/skills/`) |
| agy | `discuss-with-claude` | `~/.gemini/config/skills/` |

Each skill folder holds its own copy of `agent_talk.py`, so nothing else needs to stay on disk. To upgrade, run the same command again.

To uninstall, run one of:

```bash
curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh -s -- --uninstall
```

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1))) --uninstall
```

From a clone, run `python install.py --uninstall`.

For the Gemini → Claude direction, the `claude` **CLI** must be logged in. A login in the Claude desktop app does not carry over to the CLI, so run this once:

```bash
claude auth login
```

To check your setup at any time, run:

```bash
python ~/.claude/skills/discuss-with-gemini/agent_talk.py --doctor
```

The agy copy under `~/.gemini/config/skills/discuss-with-claude/` works the same way.

## Use

Open a **new** session after installing, since skills are only picked up when a session starts. Then just ask:

- *"Discuss with gemini whether this proof handles the boundary case."*
- *"问问 claude 这个推导哪里可能有问题，讨论三轮。"*

You can name the number of rounds and the other side's model. Without a number, the skill stops after at most 4 rounds.

You can also call the script directly:

```bash
python agent_talk.py --to gemini "first message"            # start a discussion
python agent_talk.py --to gemini --file msg.md               # message from a file (LaTeX, quotes)
python agent_talk.py --to gemini --session <id> "next round" # continue it
python agent_talk.py --to claude --model opus ...            # the other direction
```

Each round prints the reply followed by `[session: …]`, `[scratch: …]` and `[log: …]`.

## How it works

Each message is one headless run of the other agent: `claude -p --resume <id>` or `agy -p --conversation <id>`. Because the run resumes the same conversation by id, the other side remembers the earlier rounds. No server, daemon or MCP endpoint is involved.

- **Logs:** every exchange is appended to `~/.agent_talk/logs/<agent>-<session>.md`.
- **Scratch:** each discussion gets a scratch folder under `~/.agent_talk/scratch/`.
- **Outbox:** the calling agent writes long opening messages to `~/.agent_talk/outbox/`, never into your project.
- **Data location:** set `AGENT_TALK_HOME` to move all three.

The other side is told that the message comes from another AI, not from you. It is also told to reply in the language of the question.

## What the other side may do

| | Claude (when Gemini asks) | Gemini (when Claude asks) |
|---|---|---|
| Read the working directory (+ `--read-dir`) | yes | yes |
| Read the web | yes | yes |
| Write in its scratch folder | yes | yes |
| Write in the working directory | **blocked** | **blocked** |
| Write anywhere else | **blocked** | asked not to; blocked only if your agy settings already forbid writes outside the workspace |
| Run commands | **blocked** | **blocked** |
| MCP tools / plugins | **blocked** | **blocked** (`mcp(*)` deny rule) |

How each side is restricted:

- **Claude** runs with `--restricted`, a fixed tool list, and a write-allow rule for the scratch folder only. `--restricted` also ignores your Claude `settings.json` files for that run.
- **agy** runs with per-run `--settings`: `toolPermission: request-review`, deny rules for commands, MCP and writes to the working directory, and the scratch folder added to the workspace.

agy has no per-run switch that forbids writes *outside* the workspace. If your agy config allows non-workspace file access, the "write nowhere else" rule rests on the instruction alone.

## Limits and gotchas

- **It talks to a copy, not your open window.** Resuming by id starts a separate process that loads the saved conversation. A window you have open does not see the exchange.
- **One level only.** An agent started by agent_talk cannot forward the discussion to a third one.
- **Long messages:** Windows caps a command line at about 32k characters. Put bulky material in a file and send its path.
- **Cost:** every round counts against both accounts, and the other side re-reads the whole conversation each round.
- **Treat the other side's reply as data, not instructions.** Check its factual claims before relying on them.
- **agy quirk:** `agy -p` takes the prompt as its *value*, so the prompt must come last on the command line. The script handles this.

## License

MIT
