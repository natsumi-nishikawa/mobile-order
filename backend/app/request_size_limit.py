import re
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send


JSON_REQUEST_LIMIT = 64 * 1024
IMAGE_UPLOAD_REQUEST_LIMIT = 6 * 1024 * 1024
_IMAGE_UPLOAD_PATH = re.compile(r"^/api/admin/products/[1-9][0-9]*/image$")


class RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    """Limit HTTP request bodies while forwarding accepted ASGI chunks unchanged."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    @staticmethod
    def request_limit(scope: Scope) -> int:
        if (
            scope.get("method") == "POST"
            and _IMAGE_UPLOAD_PATH.fullmatch(scope.get("path", ""))
        ):
            return IMAGE_UPLOAD_REQUEST_LIMIT
        return JSON_REQUEST_LIMIT

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.request_limit(scope)
        content_lengths = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if content_lengths:
            try:
                parsed_lengths = {int(value) for value in content_lengths}
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
            if len(parsed_lengths) != 1 or next(iter(parsed_lengths)) < 0:
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
            if next(iter(parsed_lengths)) > limit:
                await self._too_large(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await self._too_large(scope, receive, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            {"detail": "Request body is too large"},
            status_code=413,
        )(scope, receive, send)
