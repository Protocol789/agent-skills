## Output Format
Always format the security patch results using the following Markdown template. You MUST format the individual host data into a single, cohesive Markdown table. Do not use bullet points for the hosts.

### 🛡️ Security Patch Report
Summary: [X] of [Total] hosts patched successfully. [Y] queued. [Z] pending reboot.

| Status | Host | Patches | Current State / Details |
| :---: | :--- | :---: | :--- |
[For every host in the data, insert a row matching the format below. Do not include markdown headers or bullet points between rows]
| [🟢/🟡/🔴] | [Host Name] | [Count or -] | [Completed / Queued (Waiting for agent) / Pending Reboot] |

> Status Indicator Rules:
> - 🟢 Green: Completed successfully.
> - 🟡 Orange/Yellow: In-progress, queued, or waiting.
> - 🔴 Red: Requires human intervention, failed, or pending reboot.

Follow-up Action:
[If any hosts require a reboot or manual intervention, ask the user for confirmation here.]
