from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine import Engine


class _SessionStore:
    def __init__(self, session):
        self.session = session

    async def get_by_call_id(self, call_id):
        return self.session if call_id == self.session.call_id else None


class _AudioSocketServer:
    def __init__(self, *, result=True, error=None):
        self.calls = []
        self.result = result
        self.error = error

    async def send_audio(self, conn_id, payload, *, encoding, sample_rate):
        self.calls.append((conn_id, payload, encoding, sample_rate))
        if self.error:
            raise self.error
        return self.result


def _engine(session, server=None):
    engine = object.__new__(Engine)
    engine.uuidext_to_channel = {"uuid-1": "caller-1"}
    engine.conn_to_channel = {}
    engine.channel_to_conn = {}
    engine.channel_to_conns = {}
    engine.audiosocket_primary_conn = {}
    engine.session_store = _SessionStore(session)
    engine._save_session = AsyncMock()
    engine.audio_socket_server = server
    engine.config = SimpleNamespace(audiosocket=SimpleNamespace(format="slin", sample_rate=8000))
    return engine


@pytest.mark.asyncio
async def test_uuid_binding_primes_with_negotiated_format_and_rate():
    session = SimpleNamespace(
        call_id="caller-1",
        audiosocket_uuid=None,
        audiosocket_conn_id=None,
        status="initializing",
        transport_profile=SimpleNamespace(wire_encoding="slin16", wire_sample_rate=16000),
    )
    server = _AudioSocketServer()
    engine = _engine(session, server)

    assert await engine._audiosocket_handle_uuid("conn-1", "uuid-1")

    assert engine.conn_to_channel == {"conn-1": "caller-1"}
    assert engine.channel_to_conn == {"caller-1": "conn-1"}
    assert session.audiosocket_conn_id == "conn-1"
    assert session.status == "audiosocket_bound"
    assert len(server.calls) == 1
    conn_id, payload, encoding, sample_rate = server.calls[0]
    assert conn_id == "conn-1"
    assert (encoding, sample_rate) == ("slin16", 16000)
    assert len(payload) == 640  # 20 ms of 16-bit mono audio at 16 kHz
    assert payload == b"\x00" * 640


@pytest.mark.asyncio
async def test_uuid_binding_uses_8khz_profile_frame_size():
    session = SimpleNamespace(
        call_id="caller-1",
        audiosocket_uuid=None,
        audiosocket_conn_id=None,
        status="initializing",
        transport_profile=SimpleNamespace(wire_encoding="slin", wire_sample_rate=8000),
    )
    server = _AudioSocketServer()
    engine = _engine(session, server)

    assert await engine._audiosocket_handle_uuid("conn-1", "uuid-1")
    _, payload, encoding, sample_rate = server.calls[0]
    assert (encoding, sample_rate) == ("slin", 8000)
    assert len(payload) == 320  # 20 ms of 16-bit mono audio at 8 kHz


@pytest.mark.asyncio
async def test_legacy_companded_profile_falls_back_to_configured_audiosocket_format():
    session = SimpleNamespace(
        call_id="caller-1",
        audiosocket_uuid=None,
        audiosocket_conn_id=None,
        status="initializing",
        transport_profile=SimpleNamespace(format="ulaw", sample_rate=8000),
    )
    server = _AudioSocketServer()
    engine = _engine(session, server)

    assert await engine._audiosocket_handle_uuid("conn-1", "uuid-1")
    _, payload, encoding, sample_rate = server.calls[0]
    assert (encoding, sample_rate) == ("slin", 8000)
    assert len(payload) == 320


@pytest.mark.asyncio
@pytest.mark.parametrize("server", [_AudioSocketServer(result=False), _AudioSocketServer(error=RuntimeError("closed"))])
async def test_uuid_binding_survives_nonfatal_priming_failure(server):
    session = SimpleNamespace(
        call_id="caller-1",
        audiosocket_uuid=None,
        audiosocket_conn_id=None,
        status="initializing",
        transport_profile=SimpleNamespace(wire_encoding="slin", wire_sample_rate=8000),
    )
    engine = _engine(session, server)

    assert await engine._audiosocket_handle_uuid("conn-1", "uuid-1")
    assert engine.conn_to_channel["conn-1"] == "caller-1"
    assert session.audiosocket_conn_id == "conn-1"
    assert session.status == "audiosocket_bound"


@pytest.mark.asyncio
async def test_uuid_binding_without_audio_server_retains_existing_behavior():
    session = SimpleNamespace(
        call_id="caller-1",
        audiosocket_uuid=None,
        audiosocket_conn_id=None,
        status="initializing",
        transport_profile=SimpleNamespace(wire_encoding="slin", wire_sample_rate=8000),
    )
    engine = _engine(session)

    assert await engine._audiosocket_handle_uuid("conn-1", "uuid-1")
    assert engine.conn_to_channel["conn-1"] == "caller-1"
    assert session.audiosocket_uuid == "uuid-1"
    engine._save_session.assert_awaited_once_with(session)
