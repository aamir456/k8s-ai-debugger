# Break & Debug Scenarios

Break the demo app on purpose, then let Claude find the root cause using **only**
the `kubernetes` MCP server (read-only). Run all commands from the repository root.

## Commands

| Command | What it does |
|---|---|
| `.\scenarios\chaos.ps1 -List` | List scenarios with the symptom an on-call engineer would see |
| `.\scenarios\chaos.ps1 -Scenario <name>` | Break something specific |
| `.\scenarios\chaos.ps1 -Random` | Mystery break — you don't know what broke |
| `.\scenarios\chaos.ps1 -Status` | Pods, deployment, HPA, endpoints, website check |
| `.\scenarios\chaos.ps1 -Reset` | Restore the healthy baseline |

If PowerShell refuses to run scripts, prefix with
`powershell -ExecutionPolicy Bypass -File` instead of `.\`.

## Scenarios (symptoms only — answers are in ANSWERS.md)

| Name | Symptom | Wait before debugging |
|---|---|---|
| `crashloop` | New release crashes on start | 30 s |
| `imagepull` | Deploy of a new version is stuck | 30 s |
| `oom` | Pods keep restarting under load | 60 s |
| `pending` | Rollout never finishes | 30 s |
| `no-endpoints` | Website returns errors but all pods look healthy | 10 s |
| `redis-down` | Website down, pods running but not ready | 30 s |
| `bad-probe` | Restart count keeps climbing | 60 s |
| `unready` | Capacity reduced, one pod not serving | 15 s |
| `cpu-spike` | Pod count jumped unexpectedly | 90 s |

## Debugging loop

1. Start a **new Claude Code session in the repository folder** (this loads the
   `kubernetes` MCP server from `.mcp.json`, created by `mcp/register-claude.ps1`;
   approve it when asked). Docker Desktop must be running.
2. Break something: `.\scenarios\chaos.ps1 -Random`
3. Paste this prompt into that session:

   > You are the on-call SRE. Something is wrong with the application in namespace
   > `demo-app` on the kind cluster. Investigate using **only the kubernetes MCP tools**
   > (do not read files in this folder or run kubectl). Tell me: the symptom, the root
   > cause with the evidence (tool output), the impact on users, and the exact fix
   > (kubectl command or manifest change). Do not apply anything.

4. Compare Claude's answer with `ANSWERS.md`, apply the fix yourself or run `-Reset`.
5. Record the result in the scorecard below.

## Scorecard

| Scenario | Root cause found? | Tool calls | Time | Fix correct? | Notes |
|---|---|---|---|---|---|
| crashloop | | | | | |
| imagepull | | | | | |
| oom | | | | | |
| pending | | | | | |
| no-endpoints | | | | | |
| redis-down | | | | | |
| bad-probe | | | | | |
| unready | | | | | |
| cpu-spike | | | | | |
