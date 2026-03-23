---
name: linear
description: CLI tool to interact with Linear tickets, projects and issues.
---

# Linear CLI

`lr` is available on PATH. Requires `LINEAR_API_KEY` env var.

## Commands

```bash
# Issues
lr issue show <issue_id or url>
lr issue list [--team <TEAM_KEY>] [--project <project_name>]
lr issue create --team <TEAM_KEY> --title <title> [--desc <description>] [--project <project_name>] [--parent <issue_id>]
lr issue update <issue_id or url> [--priority <none|urgent|high|medium|low>]

# Projects
lr project list [--team <TEAM_KEY>] [--status <status>] [--limit <n>]
```

## Notes

- Issue IDs look like `DAST-1497`. Full Linear URLs also work.
- `issue list` with no flags returns your assigned issues.
- `--project` matches by exact project name.
- `--parent` creates a sub-issue under the given parent.
- `--status` is case-insensitive (e.g. started, completed, planned).
- `--limit` defaults to 100 for project list; increase to fetch more.
- New issues are created with "Todo" status (not Triage).
- Run `lr --help` or `lr <command>` for built-in help.
