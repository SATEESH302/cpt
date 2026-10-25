import io
import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, configure_logging


def test_logging_privacy_and_correlation(client: TestClient) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("diagnostic")
    logger.addHandler(handler)
    try:
        response = client.get("/_test/unexpected?patient=secret-query", headers={
            "Authorization": "Bearer private-token"
        })
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    entries = [json.loads(line) for line in output.splitlines()]
    assert [entry["event"] for entry in entries] == [
        "request_started", "unexpected_error", "request_completed"
    ]
    assert all(
        entry["request_id"] == response.headers["x-request-id"] for entry in entries
    )
    assert entries[-1]["method"] == "GET"
    assert entries[-1]["path"] == "/_test/unexpected"
    assert entries[-1]["status"] == 500
    assert entries[-1]["duration_ms"] >= 0
    assert entries[1]["exception_type"] == "RuntimeError"
    for secret in ("secret-query", "private-token", "secret prescription content"):
        assert secret not in output


def test_no_duplicate_handlers() -> None:
    configure_logging("DEBUG")
    configure_logging("INFO")
    handlers = logging.getLogger("diagnostic").handlers
    assert sum(
        bool(getattr(handler, "diagnostic_handler", False)) for handler in handlers
    ) == 1
    assert logging.getLogger("uvicorn.access").disabled is True


def test_health_path_template_and_unknown_paths(client: TestClient) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("diagnostic")
    logger.addHandler(handler)
    try:
        client.get("/api/v1/health?token=private-query")
        client.get("/private-patient-data")
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    entries = [json.loads(line) for line in output.splitlines()]
    assert entries[0]["path"] == "/api/v1/health"
    assert entries[-1]["path"] == "[unmatched]"
    assert "private-query" not in output
    assert "private-patient-data" not in output
