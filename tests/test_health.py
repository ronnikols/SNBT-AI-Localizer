"""ТЗ-health: request health — timeouts, benching, timing logs, per-key stats."""
import asyncio
import time
import logging

import httpx
import pytest

import core
from core import (
    REQUEST_TIMEOUT_LADDER,
    HTTP_CONNECT_TIMEOUT,
    health_reset,
    health_mark_start,
    health_note_request,
    health_is_benched,
    health_bench_now,
    health_summary_lines,
    health_totals,
    health_track_call,
    _key_suffix,
    _health_fmt_s,
)


@pytest.fixture(autouse=True)
def _reset_health():
    health_reset()
    health_mark_start()
    yield
    health_reset()


def collect_logs():
    """Return (log_fn, lines): log_fn appends every message to lines."""
    lines = []
    return (lambda msg: lines.append(msg)), lines


# --- п.1: timeout ladder ------------------------------------------------------

def test_ladder_180s_base():
    # Юзер m15675: ответ модели ждём 180с, а не 90с.
    assert REQUEST_TIMEOUT_LADDER[0] == 180.0
    assert max(REQUEST_TIMEOUT_LADDER) <= 240.0
    assert HTTP_CONNECT_TIMEOUT == 10.0


def test_shared_client_timeout():
    client = core.get_shared_httpx_client()
    assert client.timeout.read == 180.0
    assert client.timeout.connect == 10.0
    assert core._QA_HTTP_TIMEOUT == 180.0


# --- п.2: benching ------------------------------------------------------------

def test_two_consecutive_timeouts_bench():
    key = "cs_live_GGgu"
    health_note_request(key, 5.0, timed_out=True)
    assert not health_is_benched(key)
    health_note_request(key, 5.0, timed_out=True)
    assert health_is_benched(key)


def test_two_consecutive_failures_bench():
    key = "cs_dead_Xyz1"
    health_note_request(key, 1.0, failed=True)
    assert not health_is_benched(key)
    health_note_request(key, 1.0, failed=True)
    assert health_is_benched(key)


def test_success_resets_consec():
    key = "cs_flaky_Ab12"
    health_note_request(key, 1.0, timed_out=True)
    health_note_request(key, 2.0)  # success resets
    health_note_request(key, 1.0, timed_out=True)
    assert not health_is_benched(key)


def test_mixed_timeout_failure_benches():
    key = "cs_bad_K9z"
    health_note_request(key, 5.0, timed_out=True)
    health_note_request(key, 1.0, failed=True)
    assert health_is_benched(key)


def test_bench_now_manual():
    key = "cs_gone_Qq77"
    health_bench_now(key, "401/403")
    assert health_is_benched(key)
    # already benched: a second bench_now must not overwrite the reason
    entry = core._KEY_HEALTH[key]
    assert entry.get("bench_reason") == "401/403"


# --- п.3: health_track_call logs [TIMING]/[TIMEOUT] --------------------------

@pytest.mark.asyncio
async def test_track_call_timing_line():
    log_fn, lines = collect_logs()
    async def ok():
        await asyncio.sleep(0.01)
        return "ok"
    res = await health_track_call("k_live_TT01", "translation", "14/33",
                                 ok, log_fn, timeout_s=180.0)
    assert res == "ok"
    timing = [l for l in lines if l.startswith("[TIMING] translation batch 14/33")]
    assert timing, lines
    assert "key ...TT01" in timing[0]


@pytest.mark.asyncio
async def test_track_call_timeout_line():
    log_fn, lines = collect_logs()
    async def hang():
        raise httpx.ReadTimeout("read timed out")
    # One timeout: logged, key NOT benched yet.
    with pytest.raises(httpx.ReadTimeout):
        await health_track_call("k_hang_HG99", "QA main", "2/5",
                                hang, log_fn, timeout_s=180.0)
    assert any(l.startswith("[TIMEOUT] QA main batch 2/5 on key ...HG99 after 180s") for l in lines), lines
    assert not health_is_benched("k_hang_HG99")
    # Second consecutive timeout: bench line appears.
    with pytest.raises(httpx.ReadTimeout):
        await health_track_call("k_hang_HG99", "QA main", "2/5",
                                hang, log_fn, timeout_s=180.0)
    assert any("[POOL] key ...HG99 benched" in l for l in lines), lines
    assert health_is_benched("k_hang_HG99")


@pytest.mark.asyncio
async def test_track_call_failure_line():
    log_fn, lines = collect_logs()
    async def fail():
        raise httpx.HTTPStatusError("server error", request=httpx.Request("POST", "http://x"),
                                   response=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await health_track_call("k_500_BB55", "translation", "3/33",
                                fail, log_fn, timeout_s=180.0)
    assert any("— failed" in l for l in lines), lines


# --- п.4: summary + totals ----------------------------------------------------

def test_summary_format():
    health_note_request("cs_live_GGgu", 6.1)
    health_note_request("cs_live_GGgu", 14.2)
    health_note_request("cs_dead_Xyz1", 5.0, timed_out=True)
    health_note_request("cs_dead_Xyz1", 5.0, timed_out=True)
    lines = health_summary_lines()
    assert any("key ...GGgu: 2 request(s), avg 10." in l and "max 14.2s" in l and "0 timeout(s)" in l
               for l in lines), lines
    assert any("key ...Xyz1" in l and "2 timeout(s), benched" in l for l in lines), lines
    total = lines[-1]
    assert total.startswith("[POOL] total: 4 request(s)"), lines
    assert "2 timeout(s)" in total
    assert "1 key(s) benched" in total


def test_totals():
    health_note_request("a", 1.0)
    health_note_request("b", 2.0, timed_out=True)
    totals = health_totals()
    assert totals["requests"] == 2
    assert totals["timeouts"] == 1
    assert totals["benched_keys"] == 0
    assert isinstance(totals["wall_s"], float)


# --- helpers ------------------------------------------------------------------

def test_key_suffix():
    assert _key_suffix("cs_live_GGgu") == "GGgu"
    assert _key_suffix("abc") == "abc"
    assert _key_suffix("") == ""


def test_fmt_s():
    assert _health_fmt_s(7.23) == "7.23s"
    assert _health_fmt_s(14.25) == "14.2s"


# --- e2e: hanging key gets benched, batch moves on ----------------------------

class _FakeProvider:
    """send_request hangs on key A, succeeds on key B."""
    def __init__(self):
        self.calls = []

    async def send_request(self, texts, api_key, model, logger, check_status, context, prompt):
        self.calls.append(api_key)
        if api_key == "key_AAAA":
            raise httpx.ReadTimeout("read timed out")
        return [f"ru::{t}" for t in texts]


@pytest.mark.asyncio
async def test_hanging_key_benched_batch_moves_on(monkeypatch):
    from core import UnifiedTranslator
    log_fn, lines = collect_logs()
    tr = UnifiedTranslator.__new__(UnifiedTranslator)
    tr.mixed_pool = [
        {"api_key": "key_AAAA", "provider": "OpenAI", "model": "gpt"},
        {"api_key": "key_BBBB", "provider": "OpenAI", "model": "gpt"},
    ]
    tr.key_index = 0
    tr.key_backoff = {}
    tr.key_cooldown_until = {}
    tr.provider_instances = {"OpenAI": _FakeProvider()}
    tr.prompt = "p"

    async def no_check():
        return None
    # Chunk 1: A hangs once (bench needs TWO consecutive), B finishes it.
    res = await tr._do_raw_translation(["hello"], log_fn, no_check, "ctx")
    assert res == ["ru::hello"]
    assert health_is_benched("key_AAAA") is False

    # Cooldown from chunk 1 would mask A (10s pause) — simulate it having
    # passed, then chunk 2 hangs on A AGAIN -> benched; B takes the batch.
    tr.key_cooldown_until.clear()
    tr.key_index = 0
    res = await tr._do_raw_translation(["world"], log_fn, no_check, "ctx2")
    assert res == ["ru::world"]
    assert health_is_benched("key_AAAA")
    assert any("benched (2 consecutive timeouts)" in l for l in lines), lines


@pytest.mark.asyncio
async def test_all_keys_benched_abort():
    from core import UnifiedTranslator, AbortException
    log_fn, _ = collect_logs()
    tr = UnifiedTranslator.__new__(UnifiedTranslator)
    tr.mixed_pool = [{"api_key": "key_AAAA", "provider": "OpenAI", "model": "gpt"}]
    tr.key_index = 0
    tr.key_backoff = {}
    tr.key_cooldown_until = {}
    tr.provider_instances = {"OpenAI": _FakeProvider()}
    tr.prompt = "p"
    health_bench_now("key_AAAA", "test")
    with pytest.raises(AbortException):
        await tr._do_raw_translation(["hello"], log_fn, None, "ctx")
