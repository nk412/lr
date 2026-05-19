# lr

A minimal CLI for [Linear](https://linear.app). List, view, create, update, and comment on issues and projects.

## Install

```bash
git clone https://github.com/nk412/lr.git
cd lr
pip install -e .
```

## Setup

1. Create a [Personal API key](https://linear.app/settings/account/security) in Linear (Settings > Account > Security & Access)
2. Add to your shell config (`~/.bashrc`, `~/.zshrc`, etc.):
   ```bash
   export LINEAR_API_KEY="lin_api_..."
   ```

3. *(Optional)* Add the [Claude Code skill](https://docs.anthropic.com/en/docs/claude-code/skills) so Claude can use `lr` directly — copy `SKILL.md` to `~/.claude/skills/`.

## Usage

```bash
# List your assigned issues
lr issue list

# List issues for a team or project (can combine)
lr issue list --team SEARCH
lr issue list --project "Q1 Roadmap"

# Show a specific issue (title + description + comments)
lr issue show IDO-134

# Open an issue in your default browser
lr issue open IDO-134

# Create an issue
lr issue create --team ENG --title "Fix login bug"

# Create an issue on a project with a description
lr issue create --team ENG --title "Fix login bug" --project "Q1 Roadmap" --desc "OAuth token refresh fails after 30min"

# Create a sub-issue
lr issue create --team ENG --title "Refresh token handler" --parent DAST-1572

# Update an issue (priority, status, estimate, or add a comment)
lr issue update IDO-134 --priority high --status "in progress"
lr issue update IDO-134 --estimate M --comment "Picking this up today"

# Add a comment
lr issue comment IDO-134 "Repro steps are in the attached log"

# List projects (optionally filter by team/status; --limit defaults to 100)
lr project list --team ENG
lr project list --status started --limit 20

# Show a project overview
lr project show "Q1 Roadmap"
```
