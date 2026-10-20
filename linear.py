#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "tabulate"]
# ///

import os
import sys
import re
import webbrowser
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
                state { name }
                assignee { name }
                project { name }
                projectMilestone { name }
                comments { nodes { body user { name } createdAt } }
            }
        }
        """,
        {"issueId": issue_id},
    )
    issue = data["issue"]
    print(f"# {issue['title']}\n")
    print(f"**Status:** {issue['state']['name']}")
    if issue.get("assignee"):
        print(f"**Assignee:** {issue['assignee']['name']}")
    if issue.get("project"):
        milestone = issue.get("projectMilestone")
        suffix = f" / {milestone['name']}" if milestone else ""
        print(f"**Project:** {issue['project']['name']}{suffix}")
    print()
    if issue["description"]:
        print(f"## Description\n{issue['description']}\n")
    comments = list(reversed(issue["comments"]["nodes"]))
    if comments:
        print("## Comments")
        for c in comments:
            name = c["user"]["name"] if c.get("user") else "Unknown"
            print(f"\n### {name} ({c['createdAt']})\n{c['body']}")


def get_todo_state_id(team_id):
    data = gql(
        """
        query teamStates($teamId: String!) {
            team(id: $teamId) {
                states { nodes { id name } }
            }
        }
        """,
        {"teamId": team_id},
    )
    for s in data["team"]["states"]["nodes"]:
        if s["name"].lower() == "todo":
            return s["id"]
    return None


def get_issue_id(identifier):
    """Resolve a human-readable issue identifier (e.g. DAST-1572) to its internal UUID."""
    data = gql(
        """
        query getIssue($issueId: String!) {
            issue(id: $issueId) { id }
        }
        """,
        {"issueId": identifier},
    )
    return data["issue"]["id"]


def get_user_id(handle):
    """Resolve --assignee value to a Linear user UUID.

    Accepts 'me' / '@me' for the API-key owner, or an email/displayName/name.
    Email match is exact; name match is case-insensitive substring across
    displayName and name (errors if ambiguous).
    """
    if handle.lower() in ("me", "@me"):
        data = gql("query viewer { viewer { id name } }")
        return data["viewer"]["id"]
    data = gql(
        """
        query findUser($q: String!) {
            users(filter: { or: [
                { email: { eq: $q } },
                { displayName: { containsIgnoreCase: $q } },
                { name: { containsIgnoreCase: $q } }
            ] }) {
                nodes { id email displayName name }
            }
        }
        """,
        {"q": handle},
    )
    users = data["users"]["nodes"]
    if not users:
        print(f"User '{handle}' not found.")
        sys.exit(1)
    # Prefer exact email match, then exact displayName, then unique substring.
    exact_email = [u for u in users if u.get("email", "").lower() == handle.lower()]
    if exact_email:
        return exact_email[0]["id"]
    exact_name = [u for u in users if handle.lower() in (
        (u.get("displayName") or "").lower(), (u.get("name") or "").lower()
    )]
    if len(exact_name) == 1:
        return exact_name[0]["id"]
    if len(users) == 1:
        return users[0]["id"]
    listing = ", ".join(f"{u['displayName'] or u['name']} <{u.get('email','')}>" for u in users[:5])
    print(f"User '{handle}' is ambiguous. Matches: {listing}")
    sys.exit(1)


def get_milestone_id(project_id, name):
    """Resolve a milestone name (case-insensitive) to its ID within a project."""
    data = gql(
        """
        query projectMilestones($projectId: String!) {
            project(id: $projectId) {
                projectMilestones(first: 50) { nodes { id name } }
            }
        }
        """,
        {"projectId": project_id},
    )
    milestones = data["project"]["projectMilestones"]["nodes"]
    for m in milestones:
        if m["name"].lower() == name.lower():
            return m["id"]
    valid = ", ".join(m["name"] for m in milestones) or "(none)"
    print(f"Milestone '{name}' not found in project. Valid milestones: {valid}")
    sys.exit(1)


def cmd_issue_create(args):
    opts, _ = parse_args(args, ["team", "title", "desc", "project", "parent", "assignee", "milestone"])
    team_key = opts.get("team")
    title = opts.get("title")
    if not team_key or not title:
        print("usage: lr issue create --team <team> --title <title> [--desc <description>] [--project <project_name>] [--milestone <name>] [--parent <issue_id>] [--assignee <name|email|me>]")
        sys.exit(1)
    if opts.get("milestone") and not opts.get("project"):
        print("--milestone requires --project.")
        sys.exit(1)
    team_id = get_team_id(team_key)
    variables = {"teamId": team_id, "title": title}
    todo_id = get_todo_state_id(team_id)
    if todo_id:
        variables["stateId"] = todo_id
    mutation = """
        mutation createIssue($teamId: String!, $title: String!, $desc: String, $projectId: String, $stateId: String, $parentId: String, $assigneeId: String, $projectMilestoneId: String) {
            issueCreate(input: { teamId: $teamId, title: $title, description: $desc, projectId: $projectId, stateId: $stateId, parentId: $parentId, assigneeId: $assigneeId, projectMilestoneId: $projectMilestoneId }) {
                success
                issue { identifier title url }
            }
        }
    """
    if opts.get("desc"):
        variables["desc"] = opts["desc"]
    if opts.get("project"):
        variables["projectId"] = get_project_id(opts["project"])
        if opts.get("milestone"):
            variables["projectMilestoneId"] = get_milestone_id(variables["projectId"], opts["milestone"])
    if opts.get("parent"):
        variables["parentId"] = get_issue_id(parse_issue_id(opts["parent"]))
    if opts.get("assignee"):
        variables["assigneeId"] = get_user_id(opts["assignee"])
    data = gql(mutation, variables)
    result = data["issueCreate"]
    if not result["success"]:
        print("Failed to create issue.")
        sys.exit(1)
    issue = result["issue"]
    print(f"Created {issue['identifier']}: {issue['title']}")
    print(issue["url"])


PRIORITY_MAP = {
    "none": 0, "urgent": 1, "high": 2, "medium": 3, "low": 4,
}

ESTIMATE_MAP = {
    "xs": 1, "s": 2, "m": 3, "l": 5, "xl": 7,
}


def get_state_id(issue_identifier, state_name):
    """Resolve a workflow state name to its ID for the issue's team."""
    data = gql(
        """
        query getIssueTeamStates($issueId: String!) {
            issue(id: $issueId) {
                team { states { nodes { id name } } }
            }
        }
        """,
        {"issueId": issue_identifier},
    )
    states = data["issue"]["team"]["states"]["nodes"]
    for s in states:
        if s["name"].lower() == state_name.lower():
            return s["id"]
    valid = ", ".join(s["name"] for s in states)
    print(f"State '{state_name}' not found. Valid states: {valid}")
    sys.exit(1)


def cmd_issue_open(args):
    if not args:
        print("usage: lr issue open <issue_id or url>")
        sys.exit(1)
    raw = args[0]
    if raw.startswith("http://") or raw.startswith("https://"):
        url = raw
    else:
        issue_id = parse_issue_id(raw)
        data = gql(
            """
            query getIssueUrl($issueId: String!) {
                issue(id: $issueId) { url }
            }
            """,
            {"issueId": issue_id},
        )
        if not data.get("issue"):
            print(f"Issue '{issue_id}' not found.")
            sys.exit(1)
        url = data["issue"]["url"]
    print(url)
    webbrowser.open(url)


def cmd_issue_comment(args):
    if len(args) < 2:
        print("usage: lr issue comment <issue_id or url> <body>")
        sys.exit(1)
    issue_id = parse_issue_id(args[0])
    body = args[1]
    internal_id = get_issue_id(issue_id)
    data = gql(
        """
        mutation createComment($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                success
                comment { id }
            }
        }
        """,
        {"issueId": internal_id, "body": body},
    )
    if not data["commentCreate"]["success"]:
        print("Failed to add comment.")
        sys.exit(1)
    print(f"Comment added to {issue_id}.")


def cmd_issue_edit_comment(args):
    """Replace the body of your most recent comment on an issue."""
    if len(args) < 2:
        print("usage: lr issue edit-comment <issue_id or url> <body>")
        sys.exit(1)
    issue_id = parse_issue_id(args[0])
    body = args[1]
    data = gql(
        """
        query myComments($issueId: String!) {
            viewer { id }
            issue(id: $issueId) {
                comments(first: 250) { nodes { id createdAt user { id } } }
            }
        }
        """,
        {"issueId": issue_id},
    )
    if not data.get("issue"):
        print(f"Issue '{issue_id}' not found.")
        sys.exit(1)
    viewer_id = data["viewer"]["id"]
    mine = [
        c for c in data["issue"]["comments"]["nodes"]
        if c.get("user") and c["user"]["id"] == viewer_id
    ]
    if not mine:
        print(f"You have no comments on {issue_id}.")
        sys.exit(1)
    latest = max(mine, key=lambda c: c["createdAt"])
    data = gql(
        """
        mutation updateComment($id: String!, $body: String!) {
            commentUpdate(id: $id, input: { body: $body }) { success }
        }
        """,
        {"id": latest["id"], "body": body},
    )
    if not data["commentUpdate"]["success"]:
        print("Failed to update comment.")
        sys.exit(1)
    print(f"Updated your latest comment on {issue_id}.")


def resolve_label_change(issue_id, names_csv, remove=False):
    """Return a labelIds list reflecting the issue's current labels with the
    given comma-separated names added (default) or removed. Name resolution for
    additions prefers labels scoped to the issue's team, falling back to a
    workspace-wide lookup; removals match against the issue's current labels by
    name (case-insensitive)."""
    data = gql(
        """
        query getIssueLabels($issueId: String!) {
            issue(id: $issueId) {
                labels { nodes { id name } }
                team { labels { nodes { id name } } }
            }
        }
        """,
        {"issueId": issue_id},
    )
    issue = data["issue"]
    current = {n["id"]: n["name"] for n in issue["labels"]["nodes"]}
    team_labels = issue["team"]["labels"]["nodes"]
    target_ids = set(current)
    for raw in [n.strip() for n in names_csv.split(",") if n.strip()]:
        if remove:
            matched = [lid for lid, name in current.items() if name.lower() == raw.lower()]
            if not matched:
                print(f"Label '{raw}' is not on the issue.")
                sys.exit(1)
            target_ids -= set(matched)
            continue
        match = [l for l in team_labels if l["name"].lower() == raw.lower()]
        if not match:
            match = gql(
                """
                query findLabel($name: String!) {
                    issueLabels(filter: { name: { eqIgnoreCase: $name } }) {
                        nodes { id name }
                    }
                }
                """,
                {"name": raw},
            )["issueLabels"]["nodes"]
        if not match:
            print(f"Label '{raw}' not found.")
            sys.exit(1)
        target_ids.add(match[0]["id"])
    return list(target_ids)


def cmd_issue_update(args):
    opts, rest = parse_args(args, ["priority", "status", "comment", "estimate", "assignee", "desc", "append-desc", "label", "remove-label", "project", "milestone", "team", "title"])
    if not rest:
        print("usage: lr issue update <issue_id or url> [--team <TEAM_KEY>] [--title <title>] [--priority <level>] [--status <state>] [--estimate <size>] [--assignee <name|email|me>] [--label <name[,name,...]>] [--remove-label <name[,name,...]>] [--project <name or url>] [--milestone <name>] [--desc <body>] [--append-desc <body>] [--comment <body>]")
        sys.exit(1)
    issue_id = parse_issue_id(rest[0])
    variables = {"issueId": issue_id}
    input_fields = {}
    if "priority" in opts:
        p = opts["priority"].lower()
        if p not in PRIORITY_MAP:
            print(f"Invalid priority '{opts['priority']}'. Must be one of: {', '.join(PRIORITY_MAP)}")
            sys.exit(1)
        input_fields["priority"] = PRIORITY_MAP[p]
    if "status" in opts:
        input_fields["stateId"] = get_state_id(issue_id, opts["status"])
    if "estimate" in opts:
        e = opts["estimate"].lower()
        if e in ESTIMATE_MAP:
            input_fields["estimate"] = ESTIMATE_MAP[e]
        else:
            try:
                input_fields["estimate"] = int(e)
            except ValueError:
                print(f"Invalid estimate '{opts['estimate']}'. Must be a t-shirt size ({', '.join(ESTIMATE_MAP)}) or an integer.")
                sys.exit(1)
    if "assignee" in opts:
        input_fields["assigneeId"] = get_user_id(opts["assignee"])
    if "team" in opts:
        input_fields["teamId"] = get_team_id(opts["team"])
    if "title" in opts:
        input_fields["title"] = opts["title"]
    if "project" in opts:
        input_fields["projectId"] = get_project_id(opts["project"])
    if "milestone" in opts:
        if "project" in opts:
            project_id = input_fields["projectId"]
        else:
            proj = gql(
                """
                query getIssueProject($issueId: String!) {
                    issue(id: $issueId) { project { id } }
                }
                """,
                {"issueId": issue_id},
            )["issue"].get("project")
            if not proj:
                print("Issue is not in a project; cannot set a milestone.")
                sys.exit(1)
            project_id = proj["id"]
        input_fields["projectMilestoneId"] = get_milestone_id(project_id, opts["milestone"])
    if "label" in opts and "remove-label" in opts:
        print("--label and --remove-label are mutually exclusive.")
        sys.exit(1)
    if "label" in opts:
        input_fields["labelIds"] = resolve_label_change(issue_id, opts["label"])
    if "remove-label" in opts:
        input_fields["labelIds"] = resolve_label_change(issue_id, opts["remove-label"], remove=True)
    if "desc" in opts and "append-desc" in opts:
        print("--desc and --append-desc are mutually exclusive.")
        sys.exit(1)
    if "desc" in opts:
        input_fields["description"] = opts["desc"]
    if "append-desc" in opts:
        current = gql(
            """
            query getDesc($issueId: String!) {
                issue(id: $issueId) { description }
            }
            """,
            {"issueId": issue_id},
        )["issue"]["description"] or ""
        sep = "\n\n" if current else ""
        input_fields["description"] = current + sep + opts["append-desc"]
    if not input_fields and "comment" not in opts:
        print("Nothing to update. Provide at least one option (e.g. --priority low, --status done, --estimate M, --desc <body>, --comment <body>).")
        sys.exit(1)
    if input_fields:
        variables["input"] = input_fields
        data = gql(
            """
            mutation updateIssue($issueId: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $issueId, input: $input) {
                    success
                    issue { identifier title url priority }
                }
            }
            """,
            variables,
        )
        result = data["issueUpdate"]
        if not result["success"]:
            print("Failed to update issue.")
            sys.exit(1)
        issue = result["issue"]
        print(f"Updated {issue['identifier']}: {issue['title']}")
    if "comment" in opts:
        cmd_issue_comment([issue_id, opts["comment"]])


def cmd_issue_link(args):
    opts, rest = parse_args(args, ["blocks", "blocked-by", "related", "duplicate"])
    if not rest:
        print("usage: lr issue link <issue_id or url> [--blocks <id[,id,...]>] [--blocked-by <id[,id,...]>] [--related <id[,id,...]>] [--duplicate <id>]")
        sys.exit(1)
    if not any(k in opts for k in ("blocks", "blocked-by", "related", "duplicate")):
        print("Provide at least one of --blocks, --blocked-by, --related, --duplicate.")
        sys.exit(1)
    issue_id = parse_issue_id(rest[0])
    source_uuid = get_issue_id(issue_id)

    def create_relation(src_uuid, dst_uuid, rel_type):
        data = gql(
            """
            mutation linkIssues($input: IssueRelationCreateInput!) {
                issueRelationCreate(input: $input) {
                    success
                    issueRelation { id type }
                }
            }
            """,
            {"input": {"issueId": src_uuid, "relatedIssueId": dst_uuid, "type": rel_type}},
        )
        return data["issueRelationCreate"]["success"]

    # Linear has no "blocked_by" type; we reverse a "blocks" relation instead.
    plan = [
        ("blocks", "blocks", False),
        ("blocked-by", "blocks", True),
        ("related", "related", False),
        ("duplicate", "duplicate", False),
    ]
    for label, rel_type, reverse in plan:
        if label not in opts:
            continue
        for target in [t.strip() for t in opts[label].split(",") if t.strip()]:
            target_id = parse_issue_id(target)
            target_uuid = get_issue_id(target_id)
            src, dst = (target_uuid, source_uuid) if reverse else (source_uuid, target_uuid)
            if not create_relation(src, dst, rel_type):
                print(f"Failed to link {issue_id} {label} {target_id}")
                sys.exit(1)
            print(f"Linked {issue_id} {label} {target_id}")


def get_project_id(ref):
    """Resolve a project name or URL to its internal UUID."""
    kind, value = parse_project_ref(ref)
    field = "slugId" if kind == "slug" else "name"
    data = gql(
        f"""
        query findProject($value: String!) {{
            projects(filter: {{ {field}: {{ eq: $value }} }}) {{
                nodes {{ id name }}
            }}
        }}
        """,
        {"value": value},
    )
    projects = data["projects"]["nodes"]
    if not projects:
        print(f"Project '{ref}' not found.")
        sys.exit(1)
    return projects[0]["id"]


def parse_project_ref(raw):
    """Parse a project URL or name. Returns (kind, value): 'slug' or 'name'."""
    m = re.match(r"https://linear\.app/[^/]+/project/([^/?#]+)", raw)
    if m:
        slug = m.group(1)
        slug_id = slug.rsplit("-", 1)[-1]
        return ("slug", slug_id)
    return ("name", raw)


PROJECT_FIELDS = """
    id name description content state url slugId
    status { name }
    startDate targetDate
    lead { name }
    teams { nodes { key name } }
"""


def project_status(p):
    """Prefer the workspace's custom status name over the legacy state category."""
    return (p.get("status") or {}).get("name") or p["state"]


def cmd_project_show(args):
    if not args:
        print("usage: lr project show <project_url or name>")
        sys.exit(1)
    kind, value = parse_project_ref(args[0])
    if kind == "slug":
        data = gql(
            f"""
            query findProject($slug: String!) {{
                projects(filter: {{ slugId: {{ eq: $slug }} }}) {{
                    nodes {{ {PROJECT_FIELDS} }}
                }}
            }}
            """,
            {"slug": value},
        )
    else:
        data = gql(
            f"""
            query findProject($name: String!) {{
                projects(filter: {{ name: {{ eq: $name }} }}) {{
                    nodes {{ {PROJECT_FIELDS} }}
                }}
            }}
            """,
            {"name": value},
        )
    projects = data["projects"]["nodes"]
    if not projects:
        print("Project not found.")
        sys.exit(1)
    p = projects[0]
    print(f"# {p['name']}\n")
    print(f"**State:** {project_status(p)}")
    if p.get("lead"):
        print(f"**Lead:** {p['lead']['name']}")
    teams = ", ".join(t["key"] for t in p["teams"]["nodes"])
    if teams:
        print(f"**Teams:** {teams}")
    if p.get("startDate") or p.get("targetDate"):
        print(f"**Dates:** {p.get('startDate') or '?'} → {p.get('targetDate') or '?'}")
    print(f"**URL:** {p['url']}\n")
    if p.get("description"):
        print(f"## Summary\n{p['description']}\n")
    if p.get("content"):
        print(f"## Overview\n{p['content']}\n")


def cmd_project_milestones(args):
    if not args:
        print("usage: lr project milestones <project_url or name>")
        sys.exit(1)
    project_id = get_project_id(args[0])
    data = gql(
        """
        query projectMilestones($projectId: String!) {
            project(id: $projectId) {
                name
                projectMilestones(first: 50) {
                    nodes { id name targetDate sortOrder }
                }
                issues(first: 250) {
                    nodes {
                        projectMilestone { id }
                        state { type }
                    }
                }
            }
        }
        """,
        {"projectId": project_id},
    )
    project = data["project"]
    milestones = sorted(project["projectMilestones"]["nodes"], key=lambda m: m["sortOrder"])
    if not milestones:
        print(f"No milestones in project '{project['name']}'.")
        return
    total = {}
    done = {}
    unassigned = 0
    for i in project["issues"]["nodes"]:
        mid = (i.get("projectMilestone") or {}).get("id")
        if mid is None:
            unassigned += 1
            continue
        total[mid] = total.get(mid, 0) + 1
        if i["state"]["type"] in ("completed", "canceled"):
            done[mid] = done.get(mid, 0) + 1
    rows = [
        [m["name"], m.get("targetDate") or "", f"{done.get(m['id'], 0)}/{total.get(m['id'], 0)}"]
        for m in milestones
    ]
    if unassigned:
        rows.append(["(no milestone)", "", f"-/{unassigned}"])
    print(tabulate(rows, headers=["Milestone", "Target", "Done/Issues"], tablefmt="simple"))


def cmd_project_add_milestone(args):
    opts, rest = parse_args(args, ["target"])
    if len(rest) < 2:
        print("usage: lr project add-milestone <project_url or name> <milestone_name> [--target <YYYY-MM-DD>]")
        sys.exit(1)
    project_id = get_project_id(rest[0])
    input_fields = {"projectId": project_id, "name": rest[1]}
    if opts.get("target"):
        input_fields["targetDate"] = opts["target"]
    data = gql(
        """
        mutation createMilestone($input: ProjectMilestoneCreateInput!) {
            projectMilestoneCreate(input: $input) {
                success
                projectMilestone { name targetDate }
            }
        }
        """,
        {"input": input_fields},
    )
    result = data["projectMilestoneCreate"]
    if not result["success"]:
        print("Failed to create milestone.")
        sys.exit(1)
    m = result["projectMilestone"]
    target = f" (target {m['targetDate']})" if m.get("targetDate") else ""
    print(f"Created milestone '{m['name']}'{target}")


HEALTH_LABELS = {"onTrack": "On track", "atRisk": "At risk", "offTrack": "Off track"}


def cmd_project_updates(args):
    opts, rest = parse_args(args, ["limit"])
    if not rest:
        print("usage: lr project updates <project_url or name> [--limit <n>]")
        sys.exit(1)
    limit = int(opts.get("limit") or 5)
    project_id = get_project_id(rest[0])
    data = gql(
        """
        query projectUpdates($projectId: String!) {
            project(id: $projectId) {
                name
                projectUpdates(first: 50) {
                    nodes { createdAt health body user { name } }
                }
            }
        }
        """,
        {"projectId": project_id},
    )
    project = data["project"]
    updates = sorted(
        project["projectUpdates"]["nodes"], key=lambda u: u["createdAt"], reverse=True
    )
    if not updates:
        print(f"No status updates in project '{project['name']}'.")
        return
    for u in updates[:limit]:
        date = u["createdAt"][:10]
        health = HEALTH_LABELS.get(u.get("health"), u.get("health") or "")
        author = (u.get("user") or {}).get("name", "?")
        print(f"## {date} — {health} — {author}\n")
        print(f"{u['body'].strip()}\n")


def cmd_issue_list(args):
    opts, _ = parse_args(args, ["team", "project", "milestone"])
    team = opts.get("team")
    project = opts.get("project")
    milestone = opts.get("milestone")
    if milestone and not project:
        print("--milestone requires --project.")
        sys.exit(1)

    if project:
        project_id = get_project_id(project)
        variables = {"projectId": project_id}
        if team:
            variables["teamKey"] = team
            query = """
                query projectIssues($projectId: String!, $teamKey: String!) {
                    project(id: $projectId) {
                        issues(first: 250, orderBy: updatedAt, filter: { team: { key: { eq: $teamKey } } }) {
                            nodes {
                                identifier
                                title
                                state { name }
                                assignee { name }
                                projectMilestone { name }
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
                        issues(first: 250, orderBy: updatedAt) {
                            nodes {
                                identifier
                                title
                                state { name }
                                assignee { name }
                                projectMilestone { name }
                                priority
                                updatedAt
                            }
                        }
                    }
                }
            """
        data = gql(query, variables)
        issues = data["project"]["issues"]["nodes"]
        if milestone:
            issues = [
                i for i in issues
                if (i.get("projectMilestone") or {}).get("name", "").lower() == milestone.lower()
            ]
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
    if project:
        rows = [
            [
                i["identifier"],
                i["state"]["name"],
                i["assignee"]["name"] if i.get("assignee") else "",
                (i.get("projectMilestone") or {}).get("name", ""),
                i["title"],
            ]
            for i in issues
        ]
        print(tabulate(rows, headers=["ID", "Status", "Assignee", "Milestone", "Title"], tablefmt="simple"))
        return
    rows = [
        [i["identifier"], i["state"]["name"], i["assignee"]["name"] if i.get("assignee") else "", i["title"]]
        for i in issues
    ]
    print(tabulate(rows, headers=["ID", "Status", "Assignee", "Title"], tablefmt="simple"))


def cmd_issue_search(args):
    opts, rest = parse_args(args, ["limit"])
    if not rest:
        print("usage: lr issue search <term> [--limit <n>]")
        sys.exit(1)
    term = " ".join(rest)
    limit = int(opts.get("limit") or 25)
    data = gql(
        """
        query search($term: String!, $first: Int!) {
            searchIssues(term: $term, first: $first) {
                nodes {
                    identifier
                    title
                    state { name }
                    team { key }
                    creator { name }
                    assignee { name }
                    updatedAt
                }
            }
        }
        """,
        {"term": term, "first": limit},
    )
    issues = data["searchIssues"]["nodes"]
    if not issues:
        print("No issues found.")
        return
    issues.sort(key=lambda i: i["updatedAt"], reverse=True)
    rows = [
        [
            i["identifier"],
            i["team"]["key"],
            i["state"]["name"],
            (i.get("creator") or {}).get("name", ""),
            (i.get("assignee") or {}).get("name", ""),
            i["title"],
        ]
        for i in issues
    ]
    print(tabulate(rows, headers=["ID", "Team", "Status", "Creator", "Assignee", "Title"], tablefmt="simple"))


def cmd_project_list(args):
    opts, _ = parse_args(args, ["team", "status", "limit"])
    team = opts.get("team")
    status = opts.get("status")
    limit = int(opts.get("limit") or 100)
    projects = []
    cursor = None
    while len(projects) < limit:
        batch = min(limit - len(projects), 100)
        data = gql(
            """
            query listProjects($cursor: String, $first: Int!) {
                projects(first: $first, after: $cursor, orderBy: updatedAt, includeArchived: true) {
                    nodes { id name state status { name } teams { nodes { key } } }
                    pageInfo { hasNextPage endCursor }
                }
            }
            """,
            {"cursor": cursor, "first": batch},
        )
        projects.extend(data["projects"]["nodes"])
        pi = data["projects"]["pageInfo"]
        if not pi["hasNextPage"]:
            break
        cursor = pi["endCursor"]
    if team:
        projects = [p for p in projects if any(t["key"] == team for t in p["teams"]["nodes"])]
    if status:
        projects = [
            p for p in projects
            if status.lower() in (p["state"].lower(), project_status(p).lower())
        ]
    if not projects:
        print("No projects found.")
        return
    rows = [
        [p["name"], project_status(p), ", ".join(t["key"] for t in p["teams"]["nodes"])]
        for p in projects
    ]
    print(tabulate(rows, headers=["Name", "State", "Teams"], tablefmt="simple"))


PROJECT_SUBCOMMANDS = {
    "list": cmd_project_list,
    "show": cmd_project_show,
    "milestones": cmd_project_milestones,
    "add-milestone": cmd_project_add_milestone,
    "updates": cmd_project_updates,
}


def help_project():
    print("lr project — manage Linear projects\n")
    print("Subcommands:")
    print("  list [--team <team_key>] [--status <status>] [--limit <n>]")
    print("                              List projects, optionally filtered by team and/or status")
    print("                              Status is case-insensitive (e.g. started, completed, planned)")
    print("                              --limit defaults to 100; use a higher value to fetch more")
    print("  show <project_url or name>  Show project overview (description + content)")
    print("  milestones <project_url or name>")
    print("                              List a project's milestones with done/total issue counts")
    print("  add-milestone <project_url or name> <milestone_name> [--target <YYYY-MM-DD>]")
    print("                              Create a milestone in a project")
    print("  updates <project_url or name> [--limit <n>]")
    print("                              Show a project's status updates, newest first (default 5)")


def cmd_project(args):
    if not args or args[0] not in PROJECT_SUBCOMMANDS:
        help_project()
        sys.exit(1)
    PROJECT_SUBCOMMANDS[args[0]](args[1:])


ISSUE_SUBCOMMANDS = {
    "show": cmd_issue_view,
    "list": cmd_issue_list,
    "search": cmd_issue_search,
    "create": cmd_issue_create,
    "update": cmd_issue_update,
    "comment": cmd_issue_comment,
    "edit-comment": cmd_issue_edit_comment,
    "open": cmd_issue_open,
    "link": cmd_issue_link,
}


def help_issue():
    print("lr issue — manage Linear issues\n")
    print("Subcommands:")
    print("  show <issue_id or url>      View issue details and comments")
    print("  open <issue_id or url>      Open the issue in your default browser")
    print("  list [options]              List issues (defaults to your assigned issues)")
    print("  search <term> [options]     Full-text search across all issues")
    print("  create [options]            Create a new issue")
    print("  update <issue_id> [options] Update an existing issue")
    print("  edit-comment <issue_id> <body>  Replace the body of your latest comment on the issue")
    print("  link <issue_id> [options]   Link an issue to other issues (blocks / blocked-by / related / duplicate)\n")
    print("Options for 'list':")
    print("  --team <team_key>           Filter by team key (e.g. IDO, DAST)")
    print("  --project <name or url>     Filter by project (exact name match, or project URL)")
    print("                              Can combine --team and --project")
    print("  --milestone <name>          Filter by project milestone (requires --project;")
    print("                              case-insensitive exact name match)\n")
    print("Options for 'search':")
    print("  --limit <n>                 Max results to return (default 25)\n")
    print("Options for 'create':")
    print("  --team <team_key>           Team to create the issue in (required)")
    print("  --title <title>             Issue title (required)")
    print("  --desc <description>        Issue description")
    print("  --project <name or url>     Add issue to a project (exact name match, or URL)")
    print("  --milestone <name>          Put issue on a project milestone (requires --project)")
    print("  --parent <issue_id>         Create as sub-issue of parent (e.g. DAST-1572)")
    print("  --assignee <handle>         Assignee — name, email, or 'me'\n")
    print("Options for 'update':")
    print("  --priority <level>          Set priority (none, urgent, high, medium, low)")
    print("  --status <state>            Set workflow state (e.g. todo, done, in progress)")
    print("  --estimate <size>           Set estimate (t-shirt: xs, s, m, l, xl — or integer)")
    print("  --assignee <handle>         Set assignee — name, email, or 'me'")
    print("  --label <name[,name,...]>   Add label(s) by name (additive; keeps existing)")
    print("  --remove-label <name[,...]> Remove label(s) by name from the issue")
    print("  --project <name or url>     Move the issue to a project (exact name match, or URL)")
    print("  --milestone <name>          Set the project milestone (issue must be in a project)")
    print("  --desc <body>               Replace the issue description")
    print("  --append-desc <body>        Append to the existing description (separated by blank line)")
    print("  --comment <body>            Add a comment to the issue\n")
    print("Options for 'comment':")
    print("  lr issue comment <issue_id> <body>   Add a comment to an issue\n")
    print("Options for 'link':")
    print("  --blocks <id[,id,...]>      Mark this issue as blocking the given issue(s)")
    print("  --blocked-by <id[,id,...]>  Mark this issue as blocked by the given issue(s)")
    print("  --related <id[,id,...]>     Add 'related' link to the given issue(s)")
    print("  --duplicate <id>            Mark this issue as duplicate of another")


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
    print("  issue    Manage issues (show, list, create, update)")
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
