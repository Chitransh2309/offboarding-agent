from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from app.integrations.base import AccessGrantData, ActionResult, IntegrationClient, MemberData, WorkItemData

if TYPE_CHECKING:
    from app.models import AccessGrant, WorkItem


class GitHubClient(IntegrationClient):
    """org_member -> org membership, repo_access -> repo collaborator,
    team_membership -> team member. item_type covers issue/pull_request/
    review_request. resource_name for repo-scoped grants/items is
    "owner/repo"; for org-scoped grants it's the org login."""

    def __init__(self, base_url: str, token: str):
        super().__init__(base_url, token)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        # Per-connection caches. Populated on first use, reused for every
        # employee within the same sync pass (sync_service now reuses one
        # client instance per connection instead of building a fresh one
        # per employee) — turns what used to be O(employees x resources)
        # API calls into O(resources), since none of this data actually
        # depends on which employee is being checked.
        self._repos_cache: list[dict] | None = None
        self._org_login_cache: str | None = None
        self._org_roles_cache: dict[str, str] | None = None
        self._teams_cache: list[dict] | None = None
        self._team_roles_cache: dict[str, dict[str, str]] = {}
        self._repo_collaborator_roles_cache: dict[str, dict[str, str]] = {}

    def _installation_repos(self) -> list[dict]:
        if self._repos_cache is not None:
            return self._repos_cache
        all_repos: list[dict] = []
        page = 1
        while True:
            resp = self._client.get("/installation/repositories", params={"per_page": 100, "page": page}).json()
            repos = resp.get("repositories", [])
            all_repos.extend(repos)
            if len(repos) < 100:
                break
            page += 1
        self._repos_cache = all_repos
        return all_repos

    def _org_login(self) -> str | None:
        if self._org_login_cache is None:
            repos = self._installation_repos()
            self._org_login_cache = repos[0]["owner"]["login"] if repos else None
        return self._org_login_cache

    def _org_roles(self, org_login: str) -> dict[str, str]:
        """login -> role ("admin"/"member"), fetched via the two role-
        filtered list endpoints ONCE per connection, not once per
        employee — each call already returns every org member with that
        role in one shot (paginated), so no per-user lookups are needed."""
        if self._org_roles_cache is not None:
            return self._org_roles_cache
        roles: dict[str, str] = {}
        for role in ("admin", "member"):
            page = 1
            while True:
                resp = self._client.get(
                    f"/orgs/{org_login}/members", params={"role": role, "per_page": 100, "page": page}
                ).json()
                if not resp:
                    break
                for user in resp:
                    roles[user["login"]] = role
                page += 1
        self._org_roles_cache = roles
        return roles

    def _teams(self, org_login: str) -> list[dict]:
        if self._teams_cache is not None:
            return self._teams_cache
        teams: list[dict] = []
        page = 1
        while True:
            resp = self._client.get(f"/orgs/{org_login}/teams", params={"per_page": 100, "page": page}).json()
            if not resp:
                break
            teams.extend(resp)
            page += 1
        self._teams_cache = teams
        return teams

    def _team_roles(self, org_login: str, team_slug: str) -> dict[str, str]:
        if team_slug in self._team_roles_cache:
            return self._team_roles_cache[team_slug]
        roles: dict[str, str] = {}
        for role in ("maintainer", "member"):
            page = 1
            while True:
                resp = self._client.get(
                    f"/orgs/{org_login}/teams/{team_slug}/members",
                    params={"role": role, "per_page": 100, "page": page},
                ).json()
                if not resp:
                    break
                for user in resp:
                    roles[user["login"]] = role
                page += 1
        self._team_roles_cache[team_slug] = roles
        return roles

    def _repo_collaborator_roles(self, repo_full_name: str) -> dict[str, str]:
        if repo_full_name in self._repo_collaborator_roles_cache:
            return self._repo_collaborator_roles_cache[repo_full_name]
        roles: dict[str, str] = {}
        page = 1
        while True:
            resp = self._client.get(
                f"/repos/{repo_full_name}/collaborators", params={"per_page": 100, "page": page}
            ).json()
            if not resp:
                break
            for collab in resp:
                perms = collab.get("permissions", {})
                role = next(
                    (name for name, key in (("admin", "admin"), ("maintain", "maintain"), ("write", "push"), ("triage", "triage")) if perms.get(key)),
                    "read",
                )
                roles[collab["login"]] = role
            page += 1
        self._repo_collaborator_roles_cache[repo_full_name] = roles
        return roles

    def list_members(self) -> list[MemberData]:
        # Installation tokens aren't scoped with a known org login up
        # front — /installation/repositories works with just the token and
        # tells us which org this installation belongs to.
        accounts = self._installation_repos()
        if not accounts:
            return []
        org_login = accounts[0]["owner"]["login"]

        members: list[MemberData] = []
        page = 1
        while True:
            resp = self._client.get(f"/orgs/{org_login}/members", params={"per_page": 100, "page": page}).json()
            if not resp:
                break
            for user in resp:
                # GitHub org membership doesn't expose email (usually
                # private) — matched to an existing employee by handle-based
                # lookup elsewhere, or created without email pre-filled.
                members.append(MemberData(external_id=str(user["id"]), external_handle=user["login"], email=None))
            page += 1
        return members

    def list_access(self, employee_external_id: str, employee_external_handle: str | None) -> list[AccessGrantData]:
        # GitHub's team membership and search qualifiers key on the
        # username (login), never the numeric user id — employee_external_id
        # (the stable id) isn't usable in these URLs at all. Without a
        # handle there is nothing we can look up.
        if not employee_external_handle:
            return []
        handle = employee_external_handle

        org_login = self._org_login()
        if not org_login:
            return []

        grants: list[AccessGrantData] = []

        # All three lookups below are local dict/set lookups against data
        # fetched at most once per connection (cached on this client
        # instance), not a fresh API call per employee — see the cache
        # methods above for why that matters for how long a sync takes.
        org_roles = self._org_roles(org_login)
        if handle in org_roles:
            grants.append(
                AccessGrantData(
                    grant_type="org_member", external_id=org_login, resource_name=org_login, role=org_roles[handle]
                )
            )

        for team in self._teams(org_login):
            team_roles = self._team_roles(org_login, team["slug"])
            if handle in team_roles:
                grants.append(
                    AccessGrantData(
                        grant_type="team_membership",
                        external_id=f"{org_login}/{team['slug']}",
                        resource_name=team["name"],
                        role=team_roles[handle],
                    )
                )

        for repo in self._installation_repos():
            full_name = repo["full_name"]
            collab_roles = self._repo_collaborator_roles(full_name)
            if handle in collab_roles:
                grants.append(
                    AccessGrantData(
                        grant_type="repo_access",
                        external_id=full_name,
                        resource_name=full_name,
                        role=collab_roles[handle],
                    )
                )

        return grants

    def list_work_items(self, employee_external_id: str, employee_external_handle: str | None) -> list[WorkItemData]:
        if not employee_external_handle:
            return []
        handle = employee_external_handle

        items: list[WorkItemData] = []
        issues = self._client.get(
            "/search/issues", params={"q": f"assignee:{handle} is:open"}
        ).json()
        for issue in issues.get("items", []):
            item_type = "pull_request" if "pull_request" in issue else "issue"
            items.append(
                WorkItemData(
                    item_type=item_type,
                    external_id=str(issue["id"]),
                    title=issue["title"],
                    url=issue["html_url"],
                    status="in_progress" if issue.get("draft") else "open",
                )
            )
        reviews = self._client.get(
            "/search/issues", params={"q": f"review-requested:{handle} is:open is:pr"}
        ).json()
        for pr in reviews.get("items", []):
            items.append(
                WorkItemData(
                    item_type="review_request",
                    external_id=str(pr["id"]),
                    title=pr["title"],
                    url=pr["html_url"],
                    status="open",
                )
            )
        return items

    def revoke(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> ActionResult:
        if grant.grant_type == "org_member":
            resp = self._client.delete(f"/orgs/{grant.external_id}/memberships/{employee_external_handle}")
        elif grant.grant_type == "repo_access":
            owner, repo = grant.external_id.split("/", 1)
            resp = self._client.delete(f"/repos/{owner}/{repo}/collaborators/{employee_external_handle}")
        elif grant.grant_type == "team_membership":
            org_login, team_slug = grant.external_id.split("/", 1)
            resp = self._client.delete(
                f"/orgs/{org_login}/teams/{team_slug}/memberships/{employee_external_handle}"
            )
        else:
            return ActionResult(success=False, error_message=f"unknown grant_type {grant.grant_type}")

        ok = resp.status_code in (204, 200)
        return ActionResult(success=ok, raw_response={"status_code": resp.status_code})

    def verify_revoked(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> bool:
        if grant.grant_type == "org_member":
            resp = self._client.get(f"/orgs/{grant.external_id}/memberships/{employee_external_handle}")
        elif grant.grant_type == "repo_access":
            owner, repo = grant.external_id.split("/", 1)
            resp = self._client.get(f"/repos/{owner}/{repo}/collaborators/{employee_external_handle}")
        elif grant.grant_type == "team_membership":
            org_login, team_slug = grant.external_id.split("/", 1)
            resp = self._client.get(
                f"/orgs/{org_login}/teams/{team_slug}/memberships/{employee_external_handle}"
            )
        else:
            return False
        return resp.status_code == 404

    def reassign(self, work_item: "WorkItem", new_owner_external_id: str) -> ActionResult:
        owner, repo, number = self._parse_issue_ref(work_item)
        resp = self._client.patch(
            f"/repos/{owner}/{repo}/issues/{number}", json={"assignees": [new_owner_external_id]}
        )
        ok = resp.status_code == 200
        return ActionResult(success=ok, raw_response={"status_code": resp.status_code})

    def verify_reassigned(self, work_item: "WorkItem", new_owner_external_id: str) -> bool:
        owner, repo, number = self._parse_issue_ref(work_item)
        resp = self._client.get(f"/repos/{owner}/{repo}/issues/{number}")
        if resp.status_code != 200:
            return False
        assignees = [a["login"] for a in resp.json().get("assignees", [])]
        return new_owner_external_id in assignees

    @staticmethod
    def _parse_issue_ref(work_item: "WorkItem") -> tuple[str, str, str]:
        match = re.search(r"github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)", work_item.url or "")
        if not match:
            raise ValueError(f"cannot parse owner/repo/number from work_item.url={work_item.url!r}")
        return match.group(1), match.group(2), match.group(3)
