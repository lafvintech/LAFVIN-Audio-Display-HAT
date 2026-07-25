import json

import jsonschema
import pytest

from lafvin_hat.schemas import load_protocol_schema
from lafvin_hat.runtime.ipc.protocol import (
    ProtocolError,
    parse_request,
    success_response,
)


def test_parse_valid_request() -> None:
    request = parse_request(
        {
            "version": 1,
            "id": "request-1",
            "type": "request",
            "method": "runtime.ping",
            "params": {},
        }
    )

    assert request.request_id == "request-1"
    assert request.method == "runtime.ping"


def test_reject_unsupported_version() -> None:
    with pytest.raises(ProtocolError) as exc_info:
        parse_request(
            {
                "version": 2,
                "id": "request-1",
                "type": "request",
                "method": "runtime.ping",
                "params": {},
            }
        )

    assert exc_info.value.code == "UNSUPPORTED_VERSION"
    assert exc_info.value.request_id == "request-1"


def test_protocol_schema_accepts_runtime_response() -> None:
    jsonschema.validate(
        success_response("request-1", {"service": "lafvin-hat-runtime"}),
        load_protocol_schema(),
    )
