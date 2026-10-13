import asyncio
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.customer_auth import resolve_current_customer
from app.database import get_db
from app.websocket_manager import customer_selection_connections

router = APIRouter(tags=["Customer WebSocket"])
logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 5
SESSION_CHECK_INTERVAL_SECONDS = 30
MAX_MESSAGE_BYTES = 8192
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.getenv("CUSTOMER_WS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
}


async def _close_safely(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        logger.debug("WebSocket was already closed", exc_info=True)


@router.websocket("/ws/customer/selections")
async def customer_selections_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),  # noqa: B008
):
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    if not customer_selection_connections.reserve_pending_auth():
        await websocket.close(code=1013, reason="Too many pending connections")
        return

    await websocket.accept()
    session_id: int | None = None
    pending_reserved = True
    try:
        try:
            raw_message = await asyncio.wait_for(
                websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await _close_safely(websocket, 1008, "Authentication timeout")
            return

        if len(raw_message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            await _close_safely(websocket, 1009, "Message too large")
            return

        try:
            message = json.loads(raw_message)
            token = message.get("token") if message.get("type") == "auth" else None
        except (json.JSONDecodeError, AttributeError):
            token = None

        if not isinstance(token, str) or not token:
            await _close_safely(websocket, 1008, "Authentication required")
            return

        try:
            customer = resolve_current_customer(token, db)
        except HTTPException:
            await _close_safely(websocket, 1008, "Authentication failed")
            return

        session_id = customer.session.id
        if not customer_selection_connections.connect(session_id, websocket):
            await _close_safely(websocket, 1013, "Connection limit reached")
            return

        customer_selection_connections.release_pending_auth()
        pending_reserved = False
        await websocket.send_json({"type": "authenticated", "session_id": session_id})

        while True:
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=SESSION_CHECK_INTERVAL_SECONDS
                )
                if len(raw_message.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await _close_safely(websocket, 1009, "Message too large")
                    return
                if raw_message == '{"type":"ping"}':
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                db.expire_all()
                try:
                    resolve_current_customer(token, db)
                except HTTPException:
                    await _close_safely(websocket, 4001, "Visit session ended")
                    return
    except WebSocketDisconnect:
        pass
    finally:
        if pending_reserved:
            customer_selection_connections.release_pending_auth()
        if session_id is not None:
            customer_selection_connections.disconnect(session_id, websocket)
