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
    resp.raise_for_status()
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
        print("usage: linear.py issue <issue_id or url>")
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
    opts, _ = parse_args(args, ["team", "title", "desc"])
    team_key = opts.get("team")
    title = opts.get("title")
    if not team_key or not title:
        print("usage: linear.py issue create --team <team> --title <title> [--desc <description>]")
        sys.exit(1)
    team_id = get_team_id(team_key)
    variables = {"teamId": team_id, "title": title}
    mutation = """
        mutation createIssue($teamId: String!, $title: String!, $desc: String) {
            issueCreate(input: { teamId: $teamId, title: $title, description: $desc }) {
                success
                issue { identifier title url }
            }
        }
    """
    if opts.get("desc"):
        variables["desc"] = opts["desc"]
    data = gql(mutation, variables)
    result = data["issueCreate"]
    if not result["success"]:
        print("Failed to create issue.")
        sys.exit(1)
    issue = result["issue"]
    print(f"Created {issue['identifier']}: {issue['title']}")
    print(issue["url"])


def cmd_issue_list(args):
    opts, _ = parse_args(args, ["team"])
    team = opts.get("team")

    if team:
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


ISSUE_SUBCOMMANDS = {
    "show": cmd_issue_view,
    "list": cmd_issue_list,
    "create": cmd_issue_create,
}


def cmd_issue(args):
    if not args or args[0] not in ISSUE_SUBCOMMANDS:
        print("usage: linear.py issue show <issue_id or url>")
        print("       linear.py issue list [--team <team>]")
        print("       linear.py issue create --team <team> --title <title> [--desc <description>]")
        sys.exit(1)
    ISSUE_SUBCOMMANDS[args[0]](args[1:])


COMMANDS = {
    "issue": cmd_issue,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: linear.py <{'|'.join(COMMANDS)}> ...")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
