"""Multipart uploads, binary downloads and raw or streamed responses (DESIGN 7 and 8)."""

from __future__ import annotations

import asyncio
import io
import pathlib
import re

import httpx
import pytest

import didit
from didit._files import to_httpx_file
from didit.types import SessionImportJob
from tests.mock_api import MockAPI

PDF = b"%PDF-1.4\n% synthetic\n"
IMAGE = b"\x89PNG\r\n\x1a\nsynthetic"


def _parts(request: httpx.Request) -> dict[str, tuple[str | None, str | None, bytes]]:
    """name -> (filename, content type, content) of a multipart body."""
    content_type = request.headers["content-type"]
    boundary = content_type.split("boundary=")[1].encode()
    out: dict[str, tuple[str | None, str | None, bytes]] = {}
    for chunk in request.content.split(b"--" + boundary):
        if b"\r\n\r\n" not in chunk:
            continue
        head, _, body = chunk.partition(b"\r\n\r\n")
        text = head.decode()
        name = re.search(r'name="([^"]+)"', text)
        filename = re.search(r'filename="([^"]*)"', text)
        ctype = re.search(r"Content-Type: (\S+)", text)
        assert name is not None
        out[name.group(1)] = (
            filename.group(1) if filename else None,
            ctype.group(1) if ctype else None,
            body.removesuffix(b"\r\n"),
        )
    return out


def test_multipart_upload_with_bytes_path_and_stream(tmp_path: pathlib.Path) -> None:
    back = tmp_path / "back.jpg"
    back.write_bytes(IMAGE)
    api = MockAPI().json(200, {"request_id": "r"})
    api.client().id_verification.verify(
        front_image=("front.png", IMAGE, "image/png"),
        back_image=back,
        perform_document_liveness=False,
        minimum_age=18,
        metadata={"flow": "onboarding"},
        vendor_data="user-1",
    )
    request = api.last
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert "x-api-key" in request.headers
    parts = _parts(request)
    assert parts["front_image"] == ("front.png", "image/png", IMAGE)
    assert parts["back_image"] == ("back.jpg", "image/jpeg", IMAGE)
    assert parts["perform_document_liveness"][2] == b"false"
    assert parts["minimum_age"][2] == b"18"
    assert parts["metadata"][2] == b'{"flow":"onboarding"}'
    assert parts["vendor_data"][2] == b"user-1"
    assert parts["vendor_data"][0] is None


def test_streams_are_read_once_and_resent_on_retry() -> None:
    stream = io.BytesIO(IMAGE)
    stream.name = "/tmp/selfie.webp"
    api = MockAPI().add(httpx.ConnectError("refused")).json(200, {})
    api.client().passive_liveness.check(user_image=stream)
    assert len(api.requests) == 2
    for request in api.requests:
        assert _parts(request)["user_image"] == ("selfie.webp", "image/webp", IMAGE)


def test_file_inputs() -> None:
    assert to_httpx_file(b"x") == ("upload", b"x", "application/octet-stream")
    assert to_httpx_file(bytearray(b"x")) == ("upload", b"x", "application/octet-stream")
    assert to_httpx_file(("doc.pdf", PDF)) == ("doc.pdf", PDF, "application/pdf")
    assert to_httpx_file((None, PDF, "application/pdf")) == ("upload", PDF, "application/pdf")
    with pytest.raises(TypeError, match="binary mode"):
        to_httpx_file(io.StringIO("text"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="path, bytes or a binary stream"):
        to_httpx_file(42)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="file tuple"):
        to_httpx_file(("a", b"b", "c", "d"))  # type: ignore[arg-type]


def test_json_or_multipart_operation_picks_the_encoding() -> None:
    job = {"uuid": "j-1", "status": "pending", "import_type": "user_verification"}
    api = MockAPI().json(201, job).json(201, job)
    client = api.client()
    result = client.sessions.imports.create(source_file_url="https://example.com/users.csv")
    assert isinstance(result, SessionImportJob)
    assert api.last.headers["content-type"] == "application/json"
    assert api.last_json() == {"source_file_url": "https://example.com/users.csv"}
    client.sessions.imports.create(
        file=("users.csv", b"a,b\n1,2\n"), import_type="user_verification"
    )
    parts = _parts(api.last)
    assert parts["file"] == ("users.csv", "text/csv", b"a,b\n1,2\n")
    assert parts["import_type"][2] == b"user_verification"


def test_multipart_without_files_is_still_multipart() -> None:
    api = MockAPI().json(200, {})
    api.client().database_validation.validate(
        issuing_state="BRA", services=["bra_cpf"], consent=True
    )
    assert api.last.headers["content-type"] == "application/json"
    assert api.last_json() == {"issuing_state": "BRA", "services": ["bra_cpf"], "consent": True}
    api.json(200, {})
    api.client().database_validation.validate(
        issuing_state="ARG", selfie=IMAGE, services=["arg_renaper"]
    )
    parts = _parts(api.last)
    assert parts["services"][2] == b'["arg_renaper"]'
    assert parts["selfie"][0] == "upload"


def test_binary_response_returns_bytes() -> None:
    api = MockAPI().add(
        httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    )
    pdf = api.client().sessions.generate_pdf("s-1")
    assert pdf == PDF
    assert api.last.headers["accept"] == "application/pdf, application/json"


def test_raw_response() -> None:
    api = MockAPI().add(
        httpx.Response(200, json={"session_id": "s-1"}, headers={"x-request-id": "req_7"})
    )
    raw = api.client().sessions.with_raw_response.retrieve_decision("s-1")
    assert isinstance(raw, didit.APIResponse)
    assert raw.status_code == 200
    assert raw.request_id == "req_7"
    assert raw.headers["x-request-id"] == "req_7"
    assert raw.method == "GET"
    assert raw.url.path == "/v3/session/s-1/decision/"
    assert raw.retries_taken == 0
    assert raw.elapsed >= 0
    assert raw.json() == {"session_id": "s-1"}
    assert "req_7" in repr(raw)
    decision = raw.parse()
    assert decision.session_id == "s-1"
    assert raw.parse() is decision
    assert raw.text() == '{"session_id":"s-1"}'
    assert raw.read() == b'{"session_id":"s-1"}'


def test_raw_response_counts_retries() -> None:
    api = MockAPI().add(httpx.Response(503)).json(200, {})
    raw = api.client().sessions.with_raw_response.retrieve_decision("s")
    assert raw.retries_taken == 1


def test_streaming_response(tmp_path: pathlib.Path) -> None:
    api = MockAPI().add(
        httpx.Response(200, content=PDF * 100, headers={"content-type": "application/pdf"})
    )
    target = tmp_path / "report.pdf"
    with api.client().sessions.with_streaming_response.generate_pdf("s-1") as response:
        assert response.status_code == 200
        response.write_to_file(str(target))
    assert target.read_bytes() == PDF * 100

    api.add(httpx.Response(200, content=b"line1\nline2\n", headers={"content-type": "text/csv"}))
    with api.client().sessions.with_streaming_response.generate_pdf("s-1") as response:
        assert list(response.iter_lines()) == ["line1", "line2"]
    api.add(httpx.Response(200, content=PDF))
    with api.client().sessions.with_streaming_response.generate_pdf("s-1") as response:
        assert b"".join(response.iter_bytes()) == PDF
    api.add(httpx.Response(200, content=b"abc"))
    with api.client().sessions.with_streaming_response.generate_pdf("s-1") as response:
        assert "".join(response.iter_text()) == "abc"
        assert response.parse() == b"abc"


def test_streaming_error_is_raised_on_enter() -> None:
    api = MockAPI().add(httpx.Response(404, json={"detail": "missing"}))
    with (
        pytest.raises(didit.NotFoundError),
        api.client().sessions.with_streaming_response.generate_pdf("s"),
    ):
        pass


def test_nested_raw_response_accessors() -> None:
    job = {"uuid": "j-1"}
    api = MockAPI().json(200, job)
    raw = api.client().sessions.with_raw_response.imports.retrieve("j-1")
    assert raw.parse().uuid == "j-1"
    api.json(200, job)
    with api.client().sessions.with_streaming_response.imports.retrieve("j-1") as streamed:
        assert streamed.parse().uuid == "j-1"


def test_async_files_and_responses(tmp_path: pathlib.Path) -> None:
    api = MockAPI()
    api.json(200, {})
    api.add(httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}))
    api.add(httpx.Response(200, json={"session_id": "s"}, headers={"x-request-id": "req_a"}))
    api.add(httpx.Response(200, content=PDF))
    api.add(httpx.Response(200, content=b"a\nb\n"))
    api.add(httpx.Response(200, content=b"xyz"))
    target = tmp_path / "async.pdf"

    async def run() -> None:
        client = api.async_client()
        await client.face_match.compare(user_image=IMAGE, ref_image=("ref.jpg", IMAGE))
        assert "ref_image" in _parts(api.last)
        assert await client.sessions.generate_pdf("s") == PDF
        raw = await client.sessions.with_raw_response.retrieve_decision("s")
        assert isinstance(raw, didit.AsyncAPIResponse)
        assert raw.request_id == "req_a"
        assert (await raw.parse()).session_id == "s"
        assert await raw.json() == {"session_id": "s"}
        assert await raw.text() == '{"session_id":"s"}'
        assert await raw.read() == b'{"session_id":"s"}'
        async with client.sessions.with_streaming_response.generate_pdf("s") as response:
            await response.write_to_file(str(target))
        async with client.sessions.with_streaming_response.generate_pdf("s") as response:
            assert [line async for line in response.iter_lines()] == ["a", "b"]
        async with client.sessions.with_streaming_response.generate_pdf("s") as response:
            assert "".join([t async for t in response.iter_text()]) == "xyz"

    asyncio.run(run())
    assert target.read_bytes() == PDF


def test_async_streamed_bytes() -> None:
    api = MockAPI().add(httpx.Response(200, content=PDF)).json(200, {"uuid": "j"})

    async def run() -> None:
        client = api.async_client()
        async with client.sessions.with_streaming_response.generate_pdf("s") as response:
            assert b"".join([c async for c in response.iter_bytes()]) == PDF
        async with client.sessions.with_streaming_response.imports.retrieve("j") as streamed:
            assert (await streamed.parse()).uuid == "j"

    asyncio.run(run())
