## Output Format
Always format the security patch results using the following Markdown template. Use the color-coded indicators (🟢, 🟡, 🔴) to clearly communicate host status and include the number of patches applied.

### 🛡️ Security Patch Report
Summary: [X] of [Total] hosts patched successfully. [Y] queued. [Z] pending reboot.

| Status | Host | Patches | Current State / Details |
| :---: | :--- | :---: | :--- |
| 🟢 | [Host Name] | [Count] | Completed |
| 🟡 | [Host Name] | [Count or -] | Queued (Waiting for agent) |
| 🔴 | [Host Name] | [Count] | Pending Reboot |

> Status Indicator Rules:
> - 🟢 Green: Completed successfully.
> - 🟡 Orange/Yellow: In-progress, queued, or waiting.
> - 🔴 Red: Requires human intervention, failed, or pending reboot.

Follow-up Action:
[If any hosts require a reboot or manual intervention, ask the user for confirmation here.]
