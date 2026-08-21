import json

import pytest
from fastapi import Request

from app.core.errors import AppError, app_error_handler


@pytest.mark.anyio
async def test_app_error_uses_server_generated_request_id() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/example",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        }
    )
    request.state.request_id = "generated-request-id"

    response = await app_error_handler(request, AppError(409, "CONFLICT", "冲突"))

    assert json.loads(response.body)["error"]["traceId"] == "generated-request-id"
