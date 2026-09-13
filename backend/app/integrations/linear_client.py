from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.integrations.base import AccessGrantData, ActionResult, IntegrationClient, MemberData, WorkItemData

if TYPE_CHECKING:
    from app.models import AccessGrant, WorkItem


class LinearClient(IntegrationClient):
    """workspace_member -> Linear org membership, revoked via userSuspend.
    Confirmed against Linear's live GraphQL schema via introspection
    (2026-09-14) — the original guess, workspaceMemberDelete, does not
    exist and would have failed on every real revoke call. Issue
    reassignment via issueUpdate was already correct and well-documented.

    userSuspend requires the admin OAuth scope (added to the connect flow
    in app/api/integrations.py) AND the connecting Linear account being a
    workspace admin — discovered from a real offboarding run returning a
    FORBIDDEN "Access denied" GraphQL error on every revoke. If either
    condition isn't met, revoke reliably comes back success=False with
    that error captured in raw_response/error_message — a known, visible
    gap, not a silent no-op."""

    def __init__(self, base_url: str, token: str):
        super().__init__(base_url, token)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": token, "Content-Type": "application/json"},
            timeout=30.0,
        )

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        resp = self._client.post("", json={"query": query, "variables": variables or {}})
        resp.raise_for_status()
        return resp.json()

    def list_members(self) -> list[MemberData]:
        # Filtered client-side rather than via the `filter` arg because
        # Linear's own OAuth apps and system bots show up in this list as
        # `app: true` users (e.g. this app's own OAuth identity, "Linear"
        # the system bot) — real employees always have app: false.
        result = self._graphql(
            "query { users(filter: { active: { eq: true } }) { nodes { id name email app } } }"
        )
        nodes = result.get("data", {}).get("users", {}).get("nodes", [])
        return [
            MemberData(external_id=u["id"], external_handle=u.get("name"), email=u.get("email"))
            for u in nodes
            if not u.get("app")
        ]

    def list_access(self, employee_external_id: str, employee_external_handle: str | None) -> list[AccessGrantData]:
        result = self._graphql(
            """
            query($id: String!) {
              user(id: $id) {
                id
                organization { id name urlKey }
              }
            }
            """,
            {"id": employee_external_id},
        )
        # (result.get("data") or {}) not result.get("data", {}) — GraphQL
        # puts an explicit `"data": null` alongside top-level errors, so the
        # dict .get default never kicks in (it only applies when the key is
        # absent, not when present with value None) and a bare .get("data",
        # {}).get(...) chain raises AttributeError on any GraphQL-level
        # error instead of surfacing it. Same fix applied throughout this
        # file.
        user = (result.get("data") or {}).get("user")
        if not user:
            return []
        org = user["organization"]
        return [
            AccessGrantData(
                grant_type="workspace_member",
                # urlKey (the workspace slug), not the raw org id — lets the
                # frontend link straight to https://linear.app/{urlKey}.
                # Safe to use as external_id here because Linear's
                # revoke()/verify_revoked() act on the employee id, never on
                # grant.external_id, for this grant_type. Trade-off: if a
                # workspace's slug is ever renamed, the old row won't match
                # on next sync and a new one gets created instead of
                # updated in place — acceptable, slug renames are rare.
                external_id=org["urlKey"],
                resource_name=org["name"],
                role="member",
            )
        ]

    def list_work_items(self, employee_external_id: str, employee_external_handle: str | None) -> list[WorkItemData]:
        result = self._graphql(
            """
            query($id: String!) {
              user(id: $id) {
                assignedIssues(filter: { state: { type: { neq: "completed" } } }) {
                  nodes { id identifier title url state { name type } }
                }
              }
            }
            """,
            {"id": employee_external_id},
        )
        nodes = ((result.get("data") or {}).get("user") or {}).get("assignedIssues", {}).get("nodes", [])
        items = []
        for issue in nodes:
            state_type = issue["state"]["type"]
            status = "in_progress" if state_type == "started" else "open"
            items.append(
                WorkItemData(
                    item_type="issue",
                    external_id=issue["id"],
                    title=issue["title"],
                    url=issue["url"],
                    status=status,
                )
            )
        return items

    def revoke(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> ActionResult:
        # userSuspend, confirmed against Linear's live GraphQL schema via
        # introspection (workspaceMemberDelete, the original guess, does
        # not exist). Suspending is the real workspace-level revoke —
        # blocks login and access org-wide, not a per-team removal.
        result = self._graphql(
            """
            mutation($userId: String!) {
              userSuspend(id: $userId) { success }
            }
            """,
            {"userId": employee_external_id},
        )
        success = (result.get("data") or {}).get("userSuspend", {}).get("success", False)
        errors = result.get("errors")
        return ActionResult(success=success and not errors, raw_response=result, error_message=str(errors) if errors else None)

    def verify_revoked(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> bool:
        result = self._graphql(
            "query($id: String!) { user(id: $id) { active } }", {"id": employee_external_id}
        )
        user = (result.get("data") or {}).get("user")
        return user is None or user.get("active") is False

    def reassign(self, work_item: "WorkItem", new_owner_external_id: str) -> ActionResult:
        result = self._graphql(
            """
            mutation($issueId: String!, $assigneeId: String!) {
              issueUpdate(id: $issueId, input: { assigneeId: $assigneeId }) {
                success
                issue { id assignee { id } }
              }
            }
            """,
            {"issueId": work_item.external_id, "assigneeId": new_owner_external_id},
        )
        payload = (result.get("data") or {}).get("issueUpdate") or {}
        success = payload.get("success", False)
        return ActionResult(success=success, raw_response=result)

    def verify_reassigned(self, work_item: "WorkItem", new_owner_external_id: str) -> bool:
        result = self._graphql(
            "query($id: String!) { issue(id: $id) { assignee { id } } }", {"id": work_item.external_id}
        )
        issue = (result.get("data") or {}).get("issue") or {}
        assignee = issue.get("assignee")
        return assignee is not None and assignee.get("id") == new_owner_external_id
