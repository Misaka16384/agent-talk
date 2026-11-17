# agent_talk

让 **Claude Code** 和 **Gemini（Antigravity CLI，`agy`）** 就一个问题互相讨论几轮，再把结果汇报给你。

你在其中一边工作时，说一句"和 gemini 讨论一下"（在另一边就说"和 claude 讨论一下"）。正在和你对话的 agent 会先写好一段自足的开场消息，再在后台拉起另一边，和它来回讨论几轮。结束后，它会告诉你双方的共识、仍有分歧的地方，以及它自己的判断。

[English](README.md)

## 安装

需要 Python 3.7 及以上，并且 `PATH` 上能找到 [Claude Code](https://code.claude.com) 和/或 [Antigravity CLI](https://antigravity.google)（`agy`）。

macOS / Linux / Git Bash：

```bash
curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1 | iex
```

或者先克隆仓库再安装：

```bash
git clone https://github.com/Misaka16384/agent-talk
python agent-talk/install.py
```

安装器会给它找到的每个 agent 各装一个技能：

| Agent | 技能 | 位置 |
|---|---|---|
| Claude Code | `discuss-with-gemini` | `~/.claude/skills/`（或 `$CLAUDE_CONFIG_DIR/skills/`） |
| agy | `discuss-with-claude` | `~/.gemini/config/skills/` |

每个技能文件夹里都自带一份 `agent_talk.py`，不需要在磁盘上保留别的东西。升级时把同一条命令再运行一次即可。

卸载时运行下面任意一条：

```bash
curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh -s -- --uninstall
```

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.ps1))) --uninstall
```

如果是从克隆的仓库安装的，运行 `python install.py --uninstall`。

如果要让 Gemini 反过来问 Claude，`claude` **命令行**必须先登录。桌面版的登录不会共享给命令行，所以要单独运行一次：

```bash
claude auth login
```

随时可以运行下面这条命令，检查配置是否正常：

```bash
python ~/.claude/skills/discuss-with-gemini/agent_talk.py --doctor
```

agy 那份副本（在 `~/.gemini/config/skills/discuss-with-claude/` 下）用法相同。

## 使用

装好后要**新开**一个会话，因为技能只在会话启动时加载。然后直接说：

- "和 gemini 讨论一下这个证明的边界情况有没有处理对。"
- "问问 claude 这个推导哪里可能有问题，讨论三轮。"

轮数和对方用的模型都可以指定。不指定轮数时，默认最多 4 轮。

也可以直接调用脚本：

```bash
python agent_talk.py --to gemini "第一条消息"              # 开始一次讨论
python agent_talk.py --to gemini --file msg.md               # 从文件读消息（含 LaTeX、引号时用）
python agent_talk.py --to gemini --session <id> "下一轮"     # 接着上一轮讨论
python agent_talk.py --to claude --model opus ...            # 反方向
```

每轮输出对方的回复，后面跟着 `[session: …]`、`[scratch: …]`、`[log: …]` 三行。

## 原理

每发一条消息，就在后台运行一次对方：`claude -p --resume <id>` 或 `agy -p --conversation <id>`。因为每次都按会话 ID 续接同一个对话，对方记得之前的轮次。整个过程不需要服务器、常驻进程或 MCP。

- **记录**：每一轮都追加到 `~/.agent_talk/logs/<agent>-<会话>.md`。
- **草稿目录**：每次讨论在 `~/.agent_talk/scratch/` 下有自己的草稿目录。
- **发件箱**：发起方写的长开场消息放在 `~/.agent_talk/outbox/`，不会写进你的项目。
- **数据位置**：设置环境变量 `AGENT_TALK_HOME` 可以把这三样一起挪走。

对方会被告知：消息来自另一个 AI，而不是你本人；并且要用提问所用的语言回答。

## 对方能做什么

| | Claude（被 Gemini 问时） | Gemini（被 Claude 问时） |
|---|---|---|
| 读工作目录（以及 `--read-dir` 指定的目录） | 能 | 能 |
| 读网页 | 能 | 能 |
| 写自己的草稿目录 | 能 | 能 |
| 写工作目录 | **禁止** | **禁止** |
| 写其他位置 | **禁止** | 只在开场说明里要求不写；只有当你的 agy 本来就禁止写工作区外的文件时，才真正被拦住 |
| 执行命令 | **禁止** | **禁止** |
| MCP 工具 / 插件 | **禁止** | **禁止**（`mcp(*)` 拒绝规则） |

两边的限制方式：

- **Claude**：以 `--restricted` 模式运行，工具列表固定，只放行写草稿目录。`--restricted` 还会让这次运行忽略你的 Claude `settings.json`。
- **agy**：每次用单次生效的 `--settings`：设为 `toolPermission: request-review`，拒绝执行命令、调用 MCP、写工作目录，并把草稿目录加入工作区。

agy 没有按次生效的"禁止写工作区外文件"开关。如果你的 agy 配置允许访问工作区外的文件，"其他位置不许写"就只能靠开场说明来约束。

## 局限与注意事项

- **对话对象是一个分身，不是你开着的窗口。** 按会话 ID 续接，相当于另起一个进程载入保存下来的对话，你开着的窗口看不到这次讨论。
- **只能转一手。** 被 agent_talk 拉起来的一方不能再转给第三方。
- **消息长度有限。** Windows 的命令行上限约 3.2 万字符，大段材料请放进文件，只发路径。
- **双方额度都会消耗。** 每一轮都算在两边账号上，而且对方每轮都要重读整段对话。
- **对方的回复只是数据，不是指令。** 其中的事实性内容要核查后再用。
- **agy 的坑。** `agy -p` 会把紧跟在后面的参数当作提示词，所以提示词必须放在命令最后。脚本已经处理好了。

## 许可证

MIT
