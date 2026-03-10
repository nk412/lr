# lr

A minimal CLI for [Linear](https://linear.app). List, view, and create issues and projects.
Doesn't search, write comments, etc. yet.

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

# List issues for a team
lr issue list --team SEARCH

# Show a specific issue (title + description + comments)
lr issue show IDO-134

# Create an issue
lr issue create --team ENG --title "Fix login bug"

# Create an issue on a project with a description
lr issue create --team ENG --title "Fix login bug" --project "Q1 Roadmap" --desc "OAuth token refresh fails after 30min"

# List projects
lr project list --team ENG
```
