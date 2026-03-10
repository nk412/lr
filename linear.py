#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "tabulate"]
# ///

import os
import sys
import re
import requests
from tabulate import tabulate

API_URL = "https://api.linear.app/graphql"
API_KEY = os.environ.get("LINEAR_API_KEY")


def gql(query, variables=None):
    if not API_KEY:
        print("LINEAR_API_KEY not set")
        sys.exit(1)
    resp = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": API_KEY, "Content-Type": "application/json"},
    )
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text}")
        sys.exit(1)
    data = resp.json()
    if "errors" in data:
        print(f"GraphQL error: {data['errors']}")
        sys.exit(1)
    return data["data"]


def parse_issue_id(raw):
    m = re.match(r"https://linear\.app/.*/issue/([^/]+)", raw)
    return m.group(1) if m else raw


def parse_args(args, flags):
    """Parse --flag value pairs from args. flags is a list of flag names (without --)."""
    result = {}
    rest = []
    i = 0
    while i < len(args):
        key = args[i].lstrip("-")
        if args[i].startswith("--") and key in flags and i + 1 < len(args):
            result[key] = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return result, rest


def get_team_id(team_key):
    data = gql(
        """
        query getTeam($key: String!) {
            teams(filter: { key: { eq: $key } }) {
                nodes { id name }
            }
        }
        """,
        {"key": team_key},
    )
    teams = data["teams"]["nodes"]
    if not teams:
        print(f"Team '{team_key}' not found.")
        sys.exit(1)
    return teams[0]["id"]


def cmd_issue_view(args):
    if not args:
        print("usage: lr issue <issue_id or url>")
        sys.exit(1)
    issue_id = parse_issue_id(args[0])
    data = gql(
        """
        query getIssue($issueId: String!) {
            issue(id: $issueId) {
                title
                description
                comments { nodes { body user { name } createdAt } }
            }
        }
        """,
        {"issueId": issue_id},
    )
    issue = data["issue"]
    print(f"# {issue['title']}\n")
    if issue["description"]:
        print(f"## Description\n{issue['description']}\n")
    comments = list(reversed(issue["comments"]["nodes"]))
    if comments:
        print("## Comments")
        for c in comments:
            name = c["user"]["name"] if c.get("user") else "Unknown"
            print(f"\n### {name} ({c['createdAt']})\n{c['body']}")


def cmd_issue_create(args):
    opts, _ = parse_args(args, ["team", "title", "desc", "project"])
    team_key = opts.get("team")
    title = opts.get("title")
    if not team_key or not title:
        print("usage: lr issue create --team <team> --title <title> [--desc <description>] [--project <project_name>]")
        sys.exit(1)
    team_id = get_team_id(team_key)
    variables = {"teamId": team_id, "title": title}
    mutation = """
        mutation createIssue($teamId: String!, $title: String!, $desc: String, $projectId: String) {
            issueCreate(input: { teamId: $teamId, title: $title, description: $desc, projectId: $projectId }) {
                success
                issue { identifier title url }
            }
        }
    """
    if opts.get("desc"):
        variables["desc"] = opts["desc"]
    if opts.get("project"):
        variables["projectId"] = get_project_id(opts["project"])
    data = gql(mutation, variables)
    result = data["issueCreate"]
    if not result["success"]:
        print("Failed to create issue.")
        sys.exit(1)
    issue = result["issue"]
    print(f"Created {issue['identifier']}: {issue['title']}")
    print(issue["url"])


def get_project_id(name):
    data = gql(
        """
        query findProject($name: String!) {
            projects(filter: { name: { eq: $name } }) {
                nodes { id name }
            }
        }
        """,
        {"name": name},
    )
    projects = data["projects"]["nodes"]
    if not projects:
        print(f"Project '{name}' not found.")
        sys.exit(1)
    return projects[0]["id"]


def cmd_issue_list(args):
    opts, _ = parse_args(args, ["team", "project"])
    team = opts.get("team")
    project = opts.get("project")

    if project:
        project_id = get_project_id(project)
        variables = {"projectId": project_id}
        if team:
            variables["teamKey"] = team
            query = """
                query projectIssues($projectId: String!, $teamKey: String!) {
                    project(id: $projectId) {
                        issues(first: 50, orderBy: updatedAt, filter: { team: { key: { eq: $teamKey } } }) {
                            nodes {
                                identifier
                                title
                                state { name }
                                assignee { name }
                                priority
                                updatedAt
                            }
                        }
                    }
                }
            """
        else:
            query = """
                query projectIssues($projectId: String!) {
                    project(id: $projectId) {
                        issues(first: 50, orderBy: updatedAt) {
                            nodes {
                                identifier
                                title
                                state { name }
                                assignee { name }
                                priority
                                updatedAt
                            }
                        }
                    }
                }
            """
        data = gql(query, variables)
        issues = data["project"]["issues"]["nodes"]
    elif team:
        data = gql(
            """
            query teamIssues($teamKey: String!) {
                teams(filter: { key: { eq: $teamKey } }) {
                    nodes {
                        issues(first: 50, orderBy: updatedAt) {
                            nodes {
                                identifier
                                title
                                state { name }
                                assignee { name }
                                priority
                                updatedAt
                            }
                        }
                    }
                }
            }
            """,
            {"teamKey": team},
        )
        teams = data["teams"]["nodes"]
        if not teams:
            print(f"Team '{team}' not found.")
            sys.exit(1)
        issues = teams[0]["issues"]["nodes"]
    else:
        data = gql(
            """
            query listIssues {
                viewer {
                    assignedIssues(first: 50, orderBy: updatedAt) {
                        nodes {
                            identifier
                            title
                            state { name }
                            assignee { name }
                            priority
                            updatedAt
                        }
                    }
                }
            }
            """
        )
        issues = data["viewer"]["assignedIssues"]["nodes"]

    if not issues:
        print("No issues found.")
        return
    issues.sort(key=lambda i: i["updatedAt"], reverse=True)
    rows = [
        [i["identifier"], i["state"]["name"], i["assignee"]["name"] if i.get("assignee") else "", i["title"]]
        for i in issues
    ]
    print(tabulate(rows, headers=["ID", "Status", "Assignee", "Title"], tablefmt="simple"))


def cmd_project_list(args):
    opts, _ = parse_args(args, ["team", "status"])
    team = opts.get("team")
    status = opts.get("status")
    data = gql(
        """
        query listProjects {
            projects(first: 100, orderBy: updatedAt) {
                nodes { id name state teams { nodes { key } } }
            }
        }
        """
    )
    projects = data["projects"]["nodes"]
    if team:
        projects = [p for p in projects if any(t["key"] == team for t in p["teams"]["nodes"])]
    if status:
        projects = [p for p in projects if p["state"].lower() == status.lower()]
    if not projects:
        print("No projects found.")
        return
    rows = [
        [p["name"], p["state"], ", ".join(t["key"] for t in p["teams"]["nodes"])]
        for p in projects
    ]
    print(tabulate(rows, headers=["Name", "State", "Teams"], tablefmt="simple"))


PROJECT_SUBCOMMANDS = {
    "list": cmd_project_list,
}


def help_project():
    print("lr project — manage Linear projects\n")
    print("Subcommands:")
    print("  list [--team <team_key>] [--status <status>]")
    print("                              List projects, optionally filtered by team and/or status")
    print("                              Status is case-insensitive (e.g. started, completed, planned)")


def cmd_project(args):
    if not args or args[0] not in PROJECT_SUBCOMMANDS:
        help_project()
        sys.exit(1)
    PROJECT_SUBCOMMANDS[args[0]](args[1:])


ISSUE_SUBCOMMANDS = {
    "show": cmd_issue_view,
    "list": cmd_issue_list,
    "create": cmd_issue_create,
}


def help_issue():
    print("lr issue — manage Linear issues\n")
    print("Subcommands:")
    print("  show <issue_id or url>      View issue details and comments")
    print("  list [options]              List issues (defaults to your assigned issues)")
    print("  create [options]            Create a new issue\n")
    print("Options for 'list':")
    print("  --team <team_key>           Filter by team key (e.g. IDO, DAST)")
    print("  --project <project_name>    Filter by project name (exact match)")
    print("                              Can combine --team and --project\n")
    print("Options for 'create':")
    print("  --team <team_key>           Team to create the issue in (required)")
    print("  --title <title>             Issue title (required)")
    print("  --desc <description>        Issue description")
    print("  --project <project_name>    Add issue to a project (exact name match)")


def cmd_issue(args):
    if not args or args[0] not in ISSUE_SUBCOMMANDS:
        help_issue()
        sys.exit(1)
    ISSUE_SUBCOMMANDS[args[0]](args[1:])


COMMANDS = {
    "issue": cmd_issue,
    "project": cmd_project,
}


def help_main():
    print("lr — CLI for the Linear API\n")
    print("Requires LINEAR_API_KEY environment variable.\n")
    print("Commands:")
    print("  issue    Manage issues (show, list, create)")
    print("  project  Manage projects (list)\n")
    print("Run 'lr <command>' with no subcommand for detailed help.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        help_main()
        sys.exit(0 if len(sys.argv) >= 2 else 1)
    if sys.argv[1] not in COMMANDS:
        help_main()
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
