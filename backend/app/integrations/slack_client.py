from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.integrations.base import AccessGrantData, ActionResult, IntegrationClient, MemberData, WorkItemData

if TYPE_CHECKING:
    from app.models import AccessGrant, WorkItem


class SlackClient(IntegrationClient):
    """channel_member -> conversations.join then conversations.kick. Join
    first is required — kick fails with not_in_channel if the bot itself
    isn't already a member of the channel, which was silently breaking
    every real revoke until this was added (needs the channels:join
    scope). admin_role revoke calls admin.users.setRegular, but that scope
    (admin.users:read/write) is Enterprise Grid-only and deliberately NOT
    requested in the default connect flow — it breaks Slack's app-manifest
    validation for a normal workspace app. So admin_role revoke will
    reliably come back success=False with a missing_scope error from
    Slack, captured in raw_response — a known, visible gap, not a silent
    no-op. Full account deactivation is out of reach outside Enterprise
    Grid; channel-level revoke (which the requested scopes do cover) is
    the primary path."""

    def __init__(self, base_url: str, token: str):
        super().__init__(base_url, token)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        # Per-connection caches — see GitHubClient for why this matters:
        # without it, the channel list and every channel's member list get
        # re-fetched from scratch for every single employee in a sync pass.
        self._channels_cache: list[dict] | None = None
        self._channel_members_cache: dict[str, set[str]] = {}

    def _channels(self) -> list[dict]:
        if self._channels_cache is not None:
            return self._channels_cache
        channels: list[dict] = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            resp = self._client.get("/conversations.list", params=params).json()
            channels.extend(resp.get("channels", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        self._channels_cache = channels
        return channels

    def _channel_members(self, channel_id: str) -> set[str]:
        if channel_id in self._channel_members_cache:
            return self._channel_members_cache[channel_id]
        members: set[str] = set()
        cursor = None
        while True:
            params: dict = {"channel": channel_id}
            if cursor:
                params["cursor"] = cursor
            resp = self._client.get("/conversations.members", params=params).json()
            members.update(resp.get("members", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        self._channel_members_cache[channel_id] = members
        return members

    def list_members(self) -> list[MemberData]:
        members: list[MemberData] = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            resp = self._client.get("/users.list", params=params).json()
            for user in resp.get("members", []):
                if user.get("is_bot") or user.get("deleted") or user.get("id") == "USLACKBOT":
                    continue
                profile = user.get("profile", {})
                members.append(
                    MemberData(
                        external_id=user["id"],
                        external_handle=profile.get("display_name") or user.get("name"),
                        email=profile.get("email"),
                    )
                )
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return members

    def list_access(self, employee_external_id: str, employee_external_handle: str | None) -> list[AccessGrantData]:
        grants: list[AccessGrantData] = []
        for channel in self._channels():
            if employee_external_id in self._channel_members(channel["id"]):
                grants.append(
                    AccessGrantData(
                        grant_type="channel_member",
                        external_id=channel["id"],
                        resource_name=f"#{channel['name']}",
                        role="member",
                    )
                )
        return grants

    def list_work_items(self, employee_external_id: str, employee_external_handle: str | None) -> list[WorkItemData]:
        # Slack has no native task concept; workflows/reminders vary per
        # workspace, so this stays empty unless a workspace-specific
        # workflow integration is added later.
        return []

    def revoke(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> ActionResult:
        if grant.grant_type == "channel_member":
            # conversations.kick requires the BOT ITSELF to already be a
            # member of the channel — this was silently failing with
            # not_in_channel on every real channel because nothing ever
            # ensured the bot had joined first. conversations.join is safe
            # to call even if already a member (returns ok with an
            # already_in_channel note, not an error). It only actually
            # fails for channel types the bot can't self-join — private
            # channels — which needs a manual invite, not a retry.
            join_resp = self._client.post("/conversations.join", json={"channel": grant.external_id}).json()
            if not join_resp.get("ok") and join_resp.get("error") != "already_in_channel":
                return ActionResult(
                    success=False,
                    raw_response=join_resp,
                    error_message=(
                        f"bot could not join this channel to revoke access ({join_resp.get('error')}) — "
                        "likely a private channel; invite the bot into it manually, then retry"
                    ),
                )

            resp = self._client.post(
                "/conversations.kick", json={"channel": grant.external_id, "user": employee_external_id}
            )
            body = resp.json()
            return ActionResult(success=body.get("ok", False), raw_response=body)
        if grant.grant_type == "admin_role":
            resp = self._client.post(
                "/admin.users.setRegular",
                json={"user_id": employee_external_id, "team_id": grant.external_id},
            )
            body = resp.json()
            return ActionResult(success=body.get("ok", False), raw_response=body)
        return ActionResult(success=False, error_message=f"unknown grant_type {grant.grant_type}")

    def verify_revoked(
        self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None
    ) -> bool:
        if grant.grant_type == "channel_member":
            members = self._client.get(
                "/conversations.members", params={"channel": grant.external_id}
            ).json()
            return employee_external_id not in members.get("members", [])
        if grant.grant_type == "admin_role":
            info = self._client.get("/users.info", params={"user": employee_external_id}).json()
            return not info.get("user", {}).get("is_admin", False)
        return False

    def reassign(self, work_item: "WorkItem", new_owner_external_id: str) -> ActionResult:
        return ActionResult(success=False, error_message="Slack has no reassignable work items")

    def verify_reassigned(self, work_item: "WorkItem", new_owner_external_id: str) -> bool:
        return False
