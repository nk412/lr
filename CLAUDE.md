# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A CLI tool for interacting with the Linear API (issue tracking). The main script is `linear.py`, a standalone Python script that uses `uv run --script` with inline dependency metadata (PEP 723).

## Running

```bash
# Requires LINEAR_API_KEY environment variable
./linear.py issue show <issue_id_or_url>
./linear.py issue list [--team <team_key>]
./linear.py issue create --team <team_key> --title <title> [--desc <description>]
```

No build step. Dependencies (`requests`, `tabulate`) are resolved automatically by `uv` from the inline script metadata. Requires Python 3.11+.

## Architecture

- `linear.py` — Single-file CLI. Uses a command/subcommand dispatch pattern via `COMMANDS` and `ISSUE_SUBCOMMANDS` dicts mapping names to handler functions. All Linear API interaction goes through the `gql()` helper which handles auth, error checking, and GraphQL execution.
- `stale_lr.sh` — Deprecated bash predecessor (in `.gitignore`). Ignore it.
