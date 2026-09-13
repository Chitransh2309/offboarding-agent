from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.integrations.base import AccessGrantData, ActionResult, IntegrationClient, MemberData, WorkItemData

if TYPE_CHECKING:
    from app.models import AccessGrant, WorkItem


class NotionClient(IntegrationClient):
    """IMPORTANT LIMITATION: Notion's public API has no endpoint to remove a
    user's access to a page/database — sharing is only manageable from the
    Notion UI by a workspace member. list_access() can observe who owns/last
    edited pages the integration can see; revoke()/verify_revoked() cannot
    actually change or confirm removal via API and return success=False with
    a clear error rather than silently no-op. Flagged in the implementation
    plan's per-platform connection table — surface this to the customer at
    connect time, don't let it fail silently inside an offboarding run."""

    def __init__(self, base_url: str, token: str):
        super().__init__(base_url, token)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
            },
            timeout=30.0,
        )

    def list_members(self) -> list[MemberData]:
        members: list[MemberData] = []
        cursor = None
        while True:
            params = {"start_cursor": cursor} if cursor else {}
            resp = self._client.get("/users", params=params).json()
            for user in resp.get("results", []):
                if user.get("type") != "person":
                    continue
                members.append(
                    MemberData(
                        external_id=user["id"],
                        external_handle=user.get("name"),
                        email=user.get("person", {}).get("email"),
                    )
                )
            cursor = resp.get("next_cursor")
            if not resp.get("has_more"):
                break
        return members

    def list_accessible_pages(self) -> list[dict]:
        """Every page (any owner) currently shared with this integration —
        used to let an admin pick a real, already-shared page from a list
        instead of pasting a raw page id, since there's no way for us to
        discover pages that haven't been explicitly shared at all."""
        pages: list[dict] = []
        cursor = None
        while True:
            payload: dict = {"filter": {"property": "object", "value": "page"}}
            if cursor:
                payload["start_cursor"] = cursor
            resp = self._client.post("/search", json=payload).json()
            for page in resp.get("results", []):
                pages.append({"id": page["id"], "title": _extract_title(page) or "(untitled)"})
            cursor = resp.get("next_cursor")
            if not resp.get("has_more"):
                break
        return pages

    def list_access(self, employee_external_id: str, employee_external_handle: str | None) -> list[AccessGrantData]:
        grants: list[AccessGrantData] = []
        cursor = None
        while True:
            payload = {"start_cursor": cursor} if cursor else {}
            resp = self._client.post("/search", json=payload).json()
            for page in resp.get("results", []):
                owner_id = page.get("created_by", {}).get("id")
                if owner_id == employee_external_id:
                    title = _extract_title(page)
                    grants.append(
                        AccessGrantData(
                            grant_type="page_access",
                            external_id=page["id"],
                            resource_name=title,
                            role="owner",
                        )
                    )
            cursor = resp.get("next_cursor")
            if not resp.get("has_more"):
                break
        return grants

    def list_work_items(self, employee_external_id: str, employee_external_handle: str | None) -> list[WorkItemData]:
        # Notion pages aren't "tasks" in the work_items sense unless the
        # workspace models them as a database with an assignee property —
        # left empty here; a workspace-specific database query can be added
        # if the customer's Notion setup tracks tasks that way.
        return []

    def create_report_page(
        self,
        parent_page_id: str,
        title: str,
        narrative: str | None,
        revoked_items: list[tuple[str, str, str]],
        reassigned_items: list[tuple[str, str]],
    ) -> dict:
        """Writes a real Notion page under an admin-configured parent page
        — unlike revoke(), Notion's API fully supports content creation,
        this isn't blocked by the same access-enumeration limitation.
        revoked_items: (system, resource_name, verify_status) tuples.
        reassigned_items: (work_item_title, new_owner_name) tuples."""

        def bullet(text: str) -> dict:
            return {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
            }

        def heading(text: str) -> dict:
            return {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
            }

        def paragraph(text: str) -> dict:
            return {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
            }

        children: list[dict] = []
        if narrative:
            children.append(heading("Summary"))
            children.append(paragraph(narrative))

        children.append(heading(f"Access revoked ({len(revoked_items)})"))
        if revoked_items:
            children.extend(bullet(f"{system}: {resource} — {status}") for system, resource, status in revoked_items)
        else:
            children.append(paragraph("No active access grants at time of offboarding."))

        children.append(heading(f"Work reassigned ({len(reassigned_items)})"))
        if reassigned_items:
            children.extend(bullet(f"{item} -> {owner}") for item, owner in reassigned_items)
        else:
            children.append(paragraph("No open work items required reassignment."))

        resp = self._client.post(
            "/pages",
            json={
                "parent": {"page_id": parent_page_id},
                "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
                # Notion caps page-creation children at 100 blocks per call.
                "children": children[:100],
            },
        )
        resp.raise_for_status()
        return resp.json()

    def revoke(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> ActionResult:
        return ActionResult(
            success=False,
            error_message=(
                "Notion's public API does not support removing page access programmatically; "
                "this grant requires manual removal in the Notion UI by a workspace member."
            ),
        )

    def verify_revoked(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> bool:
        return False

    def reassign(self, work_item: "WorkItem", new_owner_external_id: str) -> ActionResult:
        return ActionResult(success=False, error_message="Notion work items are not reassignable via this client")

    def verify_reassigned(self, work_item: "WorkItem", new_owner_external_id: str) -> bool:
        return False


def _extract_title(page: dict) -> str | None:
    properties = page.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            if title_parts:
                return "".join(part.get("plain_text", "") for part in title_parts)
    return None
