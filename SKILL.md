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
lr issue list [--team <TEAM_KEY>] [--project <project_name or url>] [--milestone <name>]
lr issue search <term> [--limit <n>]
lr issue create --team <TEAM_KEY> --title <title> [--desc <description>] [--project <project_name>] [--milestone <name>] [--parent <issue_id>] [--assignee <name|email|me>]
lr issue update <issue_id or url> [--team <TEAM_KEY>] [--title <title>] [--priority <level>] [--status <state>] [--estimate <size>] [--assignee <name|email|me>] [--label <name[,name,...]>] [--remove-label <name[,name,...]>] [--project <project_name or url>] [--milestone <name>] [--desc <body>] [--append-desc <body>] [--comment <body>]
lr issue comment <issue_id or url> <body>
lr issue link <issue_id or url> [--blocks <id[,id,...]>] [--blocked-by <id[,id,...]>] [--related <id[,id,...]>] [--duplicate <id>]

# Projects
lr project list [--team <TEAM_KEY>] [--status <status>] [--limit <n>]
lr project show <project_url or name>
lr project milestones <project_url or name>
lr project add-milestone <project_url or name> <milestone_name> [--target <YYYY-MM-DD>]
lr project updates <project_url or name> [--limit <n>]
```

## Notes

- Issue IDs look like `DAST-1497`. Full Linear URLs also work.
- `issue list` with no flags returns your assigned issues.
- `--project` matches by exact project name; a full Linear project URL also works.
- `--milestone` on `issue list` filters by project milestone name (case-insensitive; requires `--project`). Project listings include a Milestone column.
- `project milestones` lists a project's milestones with target dates and done/total issue counts.
- `project add-milestone` creates a milestone in a project; `--target` sets an optional target date.
- `project updates` shows a project's status updates (date, health, author, body), newest first; `--limit` defaults to 5. Read-only — posting updates is not supported.
- Project listings and `project show` display the workspace's custom status name (e.g. Maintenance) rather than the legacy state category; `--status` filtering matches either.
- `--milestone` on `issue create` puts the new issue on a project milestone (requires `--project`); on `issue update` it sets the milestone of an issue already in a project. Name match is case-insensitive.
- `--project` on `issue update` moves the issue to that project; combine with `--milestone` to also place it on a milestone of the new project.
- `issue show` displays status, assignee, and project/milestone above the description.
- `--parent` creates a sub-issue under the given parent.
- `--status` is case-insensitive (e.g. started, completed, planned).
- `--limit` defaults to 100 for project list, 25 for issue search; increase to fetch more.
- `issue search` runs a full-text search across all teams (title + body). Shows team and creator columns to help disambiguate.
- `--status` on update sets workflow state (e.g. todo, done, "in progress"). Case-insensitive.
- `--comment` on update adds a comment in the same call.
- `--estimate` on update accepts a t-shirt size (xs, s, m, l, xl) or an integer. T-shirt maps: xs=1, s=2, m=3, l=5, xl=7.
- `--desc` on update replaces the description; `--append-desc` appends to it (separated by a blank line). Mutually exclusive.
- `--label` on update adds label(s) by name. Additive (keeps existing labels) and accepts a comma-separated list. Resolves names within the issue's team first, then workspace-wide.
- `lr issue link` creates Linear issue relations. `--blocks`, `--blocked-by`, and `--related` accept comma-separated lists of issue IDs.
- New issues are created with "Todo" status (not Triage).
- Run `lr --help` or `lr <command>` for built-in help.
