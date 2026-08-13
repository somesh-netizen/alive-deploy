# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

"""
Google Cloud Firestore automatic-memory store backend (P3-T5).

Automatic per-turn ``TopicStore`` surface over the shared
``coded_tools.toolbox.memory_backends`` Firestore adapter — one adapter
implementation, two surfaces (the explicit ``MemoryTool`` and this
``TopicStore``). The ``google-cloud-firestore`` client library is
lazy-imported inside the adapter's methods, so importing this module
never requires it to be installed.

Tenancy is derived ENTIRELY from the server-side ``sly_data["user_id"]``
(never from LLM-supplied args): the resolved user id is folded into the
namespace before it reaches the adapter, so a prompt can never widen its
own memory scope. The blocking adapter calls run in a worker thread so
the async ``TopicStore`` contract is honored without stalling the loop.
"""

from __future__ import annotations

import asyncio
from typing import Any
from typing import ClassVar
from typing import override

from coded_tools.toolbox.memory_backends import get_memory
from middleware.persistent_memory.topic_store import TopicStore


class FirestoreStore(TopicStore):
    """One Firestore doc per ``(scoped-namespace, topic)``, scoped by user_id."""

    _BACKEND: ClassVar[str] = "firestore"
    _DEFAULT_USER_ID: ClassVar[str] = "default_user"
    _DEFAULT_SLY_KEY: ClassVar[str] = "memory"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        sly_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Build the Firestore-backed store from the HOCON ``storage`` dict.

        :param config:   Raw ``storage`` dict (non-secret refs + ``sly_key``).
        :param sly_data: Per-request data; supplies secrets and ``user_id``.
        """
        super().__init__()
        self._sly_data: dict[str, Any] | None = sly_data
        self._warned_default_user: bool = False
        self._backend: Any = get_memory(self._BACKEND, self._build_conn(config))

    def _build_conn(self, config: dict[str, Any] | None) -> dict[str, Any]:
        """
        Merge non-secret storage refs with secrets pulled from ``sly_data``.

        Connection secrets (credentials, …) come ONLY from
        ``sly_data[sly_key]``; ``config`` carries the non-secret selection.

        :param config: Raw ``storage`` dict; may be ``None``.
        :return: Connection dict for the memory-backend adapter.
        """
        data: dict[str, Any] = config or {}
        sly_key: str = str(data.get("sly_key") or self._DEFAULT_SLY_KEY)
        secrets: dict[str, Any] = dict((self._sly_data or {}).get(sly_key) or {})
        conn: dict[str, Any] = {key: value for key, value in data.items() if key not in ("backend", "sly_key")}
        conn.update(secrets)
        return conn

    def _scoped(self, namespace: str) -> str:
        """
        Fold the server-side user id into the namespace for tenant isolation.

        :param namespace: ``"<network>.<agent>"`` key.
        :return: Tenant-scoped namespace ``"<network>.<agent>/<user_id>"``.
        """
        return f"{namespace}/{self._user_id()}"

    def _user_id(self) -> str:
        """
        Resolve the tenant user id from server-side ``sly_data`` only.

        Never reads LLM-supplied args. Falls back to a shared default with
        a one-time warning when no ``user_id`` is present.

        :return: The active user id string.
        """
        if self._sly_data:
            user_id: str | None = self._sly_data.get("user_id")
            if user_id:
                return str(user_id)
        if not self._warned_default_user:
            self.logger.warning(
                "No user_id in sly_data; falling back to '%s'. All users will share one memory scope.",
                self._DEFAULT_USER_ID,
            )
            self._warned_default_user = True
        return self._DEFAULT_USER_ID

    @override
    async def _read_topic(self, namespace: str, topic: str) -> str | None:
        """
        Return one topic's content, or ``None`` if absent.

        :param namespace: ``"<network>.<agent>"`` key.
        :param topic:     Topic name.
        :return: The topic's content, or ``None``.
        """
        return await asyncio.to_thread(self._backend.read, self._scoped(namespace), topic)

    @override
    async def _write_topic(self, namespace: str, topic: str, content: str) -> None:
        """
        Create or overwrite one topic.

        :param namespace: ``"<network>.<agent>"`` key.
        :param topic:     Topic name.
        :param content:   New content for the topic.
        """
        await asyncio.to_thread(self._backend.write, self._scoped(namespace), topic, content)

    @override
    async def _remove_topic(self, namespace: str, topic: str) -> bool:
        """
        Delete one topic; return ``True`` if it existed.

        :param namespace: ``"<network>.<agent>"`` key.
        :param topic:     Topic name.
        :return: ``True`` if a topic was removed.
        """
        return await asyncio.to_thread(self._backend.remove, self._scoped(namespace), topic)

    @override
    async def _read_bucket(self, namespace: str) -> dict[str, str]:
        """
        Return the agent's ``{topic: content}`` dict for this tenant.

        :param namespace: ``"<network>.<agent>"`` key.
        :return: The full memory dict; empty if none yet.
        """
        hits: list[dict[str, str]] = await asyncio.to_thread(self._backend.search, self._scoped(namespace), "")
        return {h["topic"]: h.get("content", "") for h in hits if h.get("topic")}

    @override
    def _lock_key(self, namespace: str, topic: str) -> tuple[str, ...]:
        """
        Per-user, per-topic lock key.

        :param namespace: ``"<network>.<agent>"`` key.
        :param topic:     Topic name.
        :return: The lock-cache key for this topic.
        """
        return (self._BACKEND, self._user_id(), namespace, topic)

    @override
    def _list_lock_key(self, namespace: str) -> tuple[str, ...]:
        """
        Per-user, per-namespace lock key for list/search ops.

        :param namespace: ``"<network>.<agent>"`` key.
        :return: The lock-cache key for list/search ops.
        """
        return (f"{self._BACKEND}-list", self._user_id(), namespace)
