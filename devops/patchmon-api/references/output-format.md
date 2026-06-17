## Output Format

Always format the security patch results using the following template.
Wrap pipe tables inside a **fenced code block** (` ``` `) — bare Markdown tables do not render on Discord and other platforms. Code-fenced pipe tables render cleanly everywhere (Discord, Telegram, CLI) as monospaced, aligned text.

If only 1–2 hosts have results, you may use a compact summary sentence instead of a full table, but when 3+ hosts are involved **always use the code-fenced table**.

### 🛡️ Security Patch Report
Summary: [X] of [Total] hosts patched successfully. [Y] queued. [Z] pending reboot.

```
| Status | Host         | Patches | Current State / Details       |
| :---:  | :---         | :---:   | :---                          |
| 🟢     | [Host Name]  | [Count] | Completed                     |
| 🟡     | [Host Name]  | [Count] | Queued (Waiting for agent)    |
| 🔴     | [Host Name]  | [Count] | Pending Reboot / Failed       |
```

> Status Indicator Rules:
> - 🟢 Green: Completed successfully.
> - 🟡 Orange/Yellow: In-progress, queued, or waiting.
> - 🔴 Red: Requires human intervention, failed, or pending reboot.

**Padding tip:** Keep each column's content short and pad with spaces so the pipe separators stay aligned in monospaced rendering — it makes the table much more readable on Discord.

Follow-up Action:
[If any hosts require a reboot or manual intervention, ask the user for confirmation here.]
