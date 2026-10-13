import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class CustomerSelectionConnectionManager:
    """In-process WebSocket rooms keyed by visit session ID."""

    def __init__(
        self,
        max_connections: int = 1000,
        max_connections_per_session: int = 100,
        max_pending_auth: int = 100,
    ) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._pending_auth = 0
        self.max_connections = max_connections
        self.max_connections_per_session = max_connections_per_session
        self.max_pending_auth = max_pending_auth

    def reserve_pending_auth(self) -> bool:
        if self._pending_auth >= self.max_pending_auth:
            return False
        self._pending_auth += 1
        return True

    def release_pending_auth(self) -> None:
        self._pending_auth = max(0, self._pending_auth - 1)

    def connect(self, session_id: int, websocket: WebSocket) -> bool:
        total = sum(len(group) for group in self._connections.values())
        group = self._connections[session_id]
        if total >= self.max_connections or len(group) >= self.max_connections_per_session:
            return False
        group.add(websocket)
        return True

    def disconnect(self, session_id: int, websocket: WebSocket) -> None:
        group = self._connections.get(session_id)
        if group is None:
            return
        group.discard(websocket)
        if not group:
            self._connections.pop(session_id, None)

    async def broadcast_selection_changed(self, session_id: int) -> None:
        message = {"type": "selections_changed", "session_id": session_id}
        for websocket in tuple(self._connections.get(session_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:
                logger.exception("Failed to notify customer selection update")
                self.disconnect(session_id, websocket)

    async def close_session(self, session_id: int) -> None:
        for websocket in tuple(self._connections.get(session_id, ())):
            try:
                await websocket.send_json({"type": "session_ended", "session_id": session_id})
                await websocket.close(code=4001, reason="Visit session ended")
            except Exception:
                logger.exception("Failed to close customer WebSocket")
            finally:
                self.disconnect(session_id, websocket)


customer_selection_connections = CustomerSelectionConnectionManager()
