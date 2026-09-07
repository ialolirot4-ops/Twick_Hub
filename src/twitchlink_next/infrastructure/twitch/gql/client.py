"""Twitch GQL client.

Sends the operations in ``operations.py`` (FASE 4b, raw query text) and
``playback/operations.py`` (FASE 4c, persisted queries) against
``gql.twitch.tv/gql``. Every operation this project uses needs a
Client-Integrity header except the plain metadata lookups from FASE 4b
(``OPERATIONS_REQUIRING_INTEGRITY`` — ported exactly from
TwitchGQLAPI.py's behavior). Playback operations additionally need the
user's own OAuth token (``useAuth=True`` in the original) — metadata
operations never do.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from twitchlink_next.infrastructure.twitch.config import WEB_CLIENT_ID
from twitchlink_next.infrastructure.twitch.gql.errors import (
    TwitchGQLRequestError,
    TwitchIntegrityCheckFailedError,
)
from twitchlink_next.infrastructure.twitch.gql.operations import (
    OPERATIONS_REQUIRING_INTEGRITY,
    Operation,
)

_GQL_URL = "https://gql.twitch.tv/gql"


class IntegrityHeaderSource(Protocol):
    """What the GQL client actually depends on for Integrity — not the
    full ``IntegrityAdapter`` (which needs a live QWebEngine/Twitch
    session neither this client's tests nor, per docs/architecture-
    decisions.md AD-16, this sandbox can exercise). Tests supply a fake;
    production wires the real ``IntegrityAdapter.get_integrity_async``.
    """

    async def get_headers(self) -> dict[str, str]: ...


class TwitchGQLClient:
    def __init__(
        self, http_client: httpx.AsyncClient, integrity_source: IntegrityHeaderSource
    ) -> None:
        self._http = http_client
        self._integrity_source = integrity_source

    async def send(self, operation: Operation, variables: dict[str, object]) -> dict:
        """FASE 4b metadata operations: Integrity only for the two that
        need it (OPERATIONS_REQUIRING_INTEGRITY), never a user token."""
        needs_integrity = operation in OPERATIONS_REQUIRING_INTEGRITY
        payload = operation.build_payload(variables)
        result = await self._post(payload, needs_integrity=needs_integrity)
        assert isinstance(result, dict)  # a single-operation request always gets a single response
        return result

    async def send_persisted(
        self,
        operation_name: str,
        sha256_hash: str,
        variables: dict[str, object],
        *,
        user_token: str,
    ) -> dict:
        """FASE 4c playback operations: always need Integrity + the
        user's OAuth token."""
        payload = _persisted_payload(operation_name, sha256_hash, variables)
        result = await self._post(payload, needs_integrity=True, user_token=user_token)
        assert isinstance(result, dict)  # a single-operation request always gets a single response
        return result

    async def send_persisted_batch(
        self, operations: list[tuple[str, str, dict[str, object]]], *, user_token: str
    ) -> list[dict]:
        """Same as ``send_persisted`` but for the batched-request shape
        ``getStreamPlaybackAccessToken`` uses (token + ad-handling data in
        one HTTP call, ported from TwitchGQLAPI.py)."""
        payload = [_persisted_payload(name, sha256, vars_) for name, sha256, vars_ in operations]
        result = await self._post(payload, needs_integrity=True, user_token=user_token)
        assert isinstance(result, list)  # a batched request always gets a batched response
        return result

    async def _post(
        self, payload: dict | list[dict], *, needs_integrity: bool, user_token: str | None = None
    ) -> dict | list[dict]:
        headers = {"Client-ID": WEB_CLIENT_ID, "Content-Type": "application/json"}
        if needs_integrity:
            headers.update(await self._integrity_source.get_headers())
        if user_token:
            headers["Authorization"] = f"OAuth {user_token}"

        try:
            response = await self._http.post(_GQL_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as error:
            raise TwitchGQLRequestError(str(error)) from error
        except ValueError as error:  # response.json() on a non-JSON body
            raise TwitchGQLRequestError(
                f"Twitch GQL returned a non-JSON response: {error}"
            ) from error

        for entry in data if isinstance(data, list) else [data]:
            for gql_error in entry.get("errors", []):
                if gql_error.get("message") == "failed integrity check":
                    raise TwitchIntegrityCheckFailedError

        return data


def _persisted_payload(operation_name: str, sha256_hash: str, variables: dict[str, object]) -> dict:
    return {
        "operationName": operation_name,
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha256_hash}},
        "variables": variables,
    }
