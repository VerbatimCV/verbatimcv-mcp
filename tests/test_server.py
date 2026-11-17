import json
from pathlib import Path

import httpx2
import pytest
from mcp import Client
from verbatimcv_mcp import server as srv

KEY = "vcv_" + "a" * 43
GOLDEN = Path(__file__).resolve().parents[3] / "tests" / "golden" / "inputs"
RESULT = {"schema_version": "2026-11-01", "candidate": {"full_name": "Daniel Whitford"}}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def api(monkeypatch):
    """Route the tool's HTTP calls to a handler; records every request."""
    monkeypatch.setenv("VERBATIMCV_API_KEY", KEY)
    monkeypatch.delenv("VERBATIMCV_API_URL", raising=False)
    state = {"requests": [], "respond": lambda r: httpx2.Response(200, json=RESULT)}

    def handler(request):
        state["requests"].append(request)
        return state["respond"](request)

    monkeypatch.setattr(
        srv,
        "_client",
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return state


async def call(args):
    async with Client(srv.server) as client:
        return await client.call_tool("parse_resume", args)


def text(result):
    """The tool's text, without the SDK's "Error executing tool parse_resume: " prefix on errors."""
    return result.content[0].text.removeprefix("Error executing tool parse_resume: ")


async def test_tool_is_listed_with_agent_description():
    async with Client(srv.server) as client:
        tools = (await client.list_tools()).tools
    tool = next(t for t in tools if t.name == "parse_resume")
    assert (
        "verbatim quote" in tool.description
        and "confirm_before_acting" in tool.description
    )
    assert (
        tool.annotations.read_only_hint is False
        and tool.annotations.open_world_hint is True
    )


async def test_parse_local_pdf_returns_result_as_structured_json(api):
    pdf = next(GOLDEN.glob("16_*"))
    result = await call({"file_path": str(pdf)})
    assert not result.is_error
    assert result.structured_content == RESULT
    assert json.loads(text(result)) == RESULT
    req = api["requests"][0]
    assert req.url == "https://api.verbatimcv.com/v1/parse"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["user-agent"].startswith("verbatimcv-mcp/")
    assert (
        pdf.name.encode() not in req.content
    )  # the filename (often the candidate's name) isn't sent


async def test_parse_url_sends_form_field(api):
    result = await call({"url": "https://cv.example.com/jane.pdf"})
    assert not result.is_error and b"jane.pdf" in api["requests"][0].content


@pytest.mark.parametrize(
    "content", [b"-----BEGIN OPENSSH PRIVATE KEY-----\n", b"plain notes", b""]
)
async def test_non_cv_local_files_are_never_uploaded(api, tmp_path, content):
    secret = tmp_path / "Jane_Doe_id_rsa"
    secret.write_bytes(content)
    result = await call({"file_path": str(secret)})
    assert result.is_error and text(result).startswith("UNSUPPORTED_FORMAT")
    assert api["requests"] == []
    assert "Jane_Doe" not in text(result) and str(tmp_path) not in text(result)


async def test_missing_file_and_directory(api, tmp_path):
    for path in (tmp_path / "Jane_Doe_cv.pdf", tmp_path):
        result = await call({"file_path": str(path)})
        assert result.is_error and text(result).startswith("FILE_NOT_FOUND")
        assert "Jane_Doe" not in text(result)
    assert api["requests"] == []


async def test_too_large_file_not_uploaded(api, tmp_path):
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-1.7\n" + b"0" * srv.MAX_BYTES)
    result = await call({"file_path": str(big)})
    assert (
        result.is_error
        and text(result).startswith("FILE_TOO_LARGE")
        and api["requests"] == []
    )


@pytest.mark.parametrize(
    "args", [{}, {"file_path": "/x.pdf", "url": "https://a.b/c.pdf"}]
)
async def test_exactly_one_input(api, args):
    result = await call(args)
    assert result.is_error and "exactly one" in text(result) and api["requests"] == []


@pytest.mark.parametrize("key", ["", "sk-ant-123", "vcv_short"])
async def test_missing_or_malformed_key_fails_without_network(api, monkeypatch, key):
    monkeypatch.setenv("VERBATIMCV_API_KEY", key)
    result = await call({"url": "https://cv.example.com/cv.pdf"})
    assert (
        result.is_error
        and text(result).startswith("INVALID_API_KEY")
        and api["requests"] == []
    )


async def test_plain_http_api_url_refused(api, monkeypatch):
    monkeypatch.setenv("VERBATIMCV_API_URL", "http://evil.example.com")
    result = await call({"url": "https://cv.example.com/cv.pdf"})
    assert result.is_error and "https://" in text(result) and api["requests"] == []


async def test_api_errors_pass_code_message_and_retry_after(api):
    api["respond"] = lambda r: httpx2.Response(
        429,
        headers={"Retry-After": "42"},
        json={
            "error": {"code": "RATE_LIMITED", "message": "Too many requests."},
            "request_id": "r",
        },
    )
    result = await call({"url": "https://cv.example.com/cv.pdf"})
    assert result.is_error
    assert text(result) == "RATE_LIMITED: Too many requests. Retry after 42 seconds."


async def test_non_json_and_network_errors_are_clean(api):
    api["respond"] = lambda r: httpx2.Response(502, text="<html>booting</html>")
    result = await call({"url": "https://cv.example.com/private/jane-doe.pdf"})
    assert result.is_error and text(result).startswith("SERVICE_UNAVAILABLE")

    def down(request):
        raise httpx2.ConnectError(
            "failed to connect to https://cv.example.com/private/jane-doe.pdf"
        )

    api["respond"] = down
    result = await call({"url": "https://cv.example.com/private/jane-doe.pdf"})
    assert result.is_error and text(result).startswith("SERVICE_UNAVAILABLE")
    assert "jane-doe" not in text(result)
