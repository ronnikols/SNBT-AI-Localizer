"""ТЗ v4.4 «Пайплайн: QA поверх перевода» — unit battery.

The pipeline is pure OPTIMIZATION on top of the existing audit phase: it
runs the same phase-1 (ids-only) and phase-2 (full verdict) scans DURING
the translation, and the tail phase adopts the results only when they are
complete. These tests pin the promises of the spec:

  1. OVERLAP — phase 1 for an early batch runs while later translation
     batches are still in flight (slow-translator mock).
  2. ADOPTION — all-or-nothing: a partial coverage makes the tail rescan.
  3. SURVIVAL — a dying judge and a failing batch follow the tail phase's
     own rules; nothing is trusted that the tail did not verify.
  4. CACHE — a cached-clean pair never enters a pipeline batch (п.2).

Everything runs INSIDE a live event loop: the pipeline starts real
asyncio tasks.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core  # noqa: E402
import tests.test_qa_phase as tq  # noqa: E402


def _params(**over):
    cfg = tq.qa_config(__import__("tempfile").gettempdir())
    cfg["batch_size"] = 10
    cfg["verdict_cache"] = False
    cfg.update(over)
    return cfg


class Recorder:
    """Ordered timeline of scan events, to prove the overlap."""

    def __init__(self):
        self.events = []

    def note(self, what):
        self.events.append(what)

    def has(self, needle):
        return any(needle in e for e in self.events)


class StubTranslator:
    provider = "Test"
    model = "stub"
    mixed_pool = [{"api_key": "test-key"}]
    api_keys = ["test-key"]
    modpack_glossary_terms = {}

    async def translate(self, texts, logger=print, check_status=None, context=""):
        # Mirrors tests/test_qa_phase.py::make_translator_stub — the tail's
        # hard-verdict path re-translates through this method.
        return [f"[retried]{t}" for t in texts]


def _scan_stub(rec, findings, delay=0.0, broken=(), fatal=()):
    """Stand-in for core._qa_scan_pairs with the same signature."""
    async def _scan(pairs, prompt, api_keys, provider, model_text, custom_base_url,
                    logger, check_status, vanilla_gloss, modpack_terms,
                    temperature=None, phase="main", batch_label="0", ids_only=False):
        if delay:
            await asyncio.sleep(delay)
        rec.note(f"scan:{phase}")
        for p in pairs:
            if p["source"] in fatal:
                raise RuntimeError("all QA keys failed: 401 (simulated)")
        for p in pairs:
            if p["source"] in broken:
                # NOT a key error: the tail's split-and-retry path.
                raise ValueError("broken JSON in the model answer (simulated)")
        if ids_only:
            return [{"id": p["id"]} for p in pairs if p["source"] in findings]
        return [{"id": p["id"], "category": "GLOSSARY_VIOLATION", "severity": "soft",
                 "issue": "simulated", "suggested": None}
                for p in pairs if p["source"] in findings]
    return _scan


class _FakeVerdictCache:
    """Hermetic stand-in — the real cache writes ~/.snbt-tr."""

    _clean = set()

    def __init__(self, *a, **k):
        pass

    @staticmethod
    def key(source, mt, cfg_hash):
        return f"{source}\0{mt}\0{cfg_hash}"

    @staticmethod
    def config_hash(*a):
        return "cfghash"

    def get_clean(self, k):
        return k in _FakeVerdictCache._clean

    def mark(self, k, state):
        if state == "clean":
            _FakeVerdictCache._clean.add(k)
        else:
            _FakeVerdictCache._clean.discard(k)

    def close(self):
        pass


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_v44_pipeline_overlaps_translation():
    """ТЗ v4.4 п.1/п.6: the audit of batch 1 runs while batch 3 is still
    being translated — the file's own translation is the producer."""
    rec = Recorder()
    BATCHES = [["src0", "src1"], ["src2", "src3"], ["src4", "src5"]]
    # batch 3 crawls far longer than the judge needs for batch 1
    DURATION = [0.10, 0.30, 1.20]

    class SlowTranslator(StubTranslator):
        def __init__(self, delay):
            self.delay = delay

        async def translate(self, texts, logger=print, check_status=None, context=""):
            rec.note(f"translate:{texts[0]}")
            await asyncio.sleep(self.delay)
            return [f"[ru]{t}" for t in texts]

    async def main():
        orig = core._qa_scan_pairs
        # the judge is SLOW on purpose: its answer for batch 1 can only land
        # after the producer has already moved on
        core._qa_scan_pairs = _scan_stub(rec, {"src0", "src1"}, delay=0.25)
        pf = None
        try:
            tr = SlowTranslator(0.1)
            pf = core._QAPrefetch(_params(), tr, lambda m: None, None,
                                  "Russian", 10)
            assert pf.ready, "pipeline must be ready for a supported provider"
            pf.start()
            # the real producer: all three batches translate concurrently and
            # every finished batch is fed the moment it lands
            tasks = [asyncio.create_task(SlowTranslator(d).translate(b,
                                                                    context="f.snbt"))
                     for b, d in zip(BATCHES, DURATION)]

            async def produce():
                for batch, t in zip(BATCHES, tasks):
                    out = await t
                    pf.feed(zip(batch, out))

            producer = asyncio.create_task(produce())
            await asyncio.sleep(0.6)
            # batch 1's audit has landed...
            assert rec.has("scan:pipeline1-j1"), rec.events
            # ...while the LAST translation batch is demonstrably unfinished
            assert not tasks[2].done(), "batch 3 must still be translating"
            await producer
            await pf.finish()
            assert pf.ready, "a full feed must leave the pipeline adoptable"
        finally:
            core._qa_scan_pairs = orig
            if pf is not None:
                pf.abort()
            for t in locals().get("tasks", []):
                t.cancel()
            await asyncio.gather(*locals().get("tasks", []), return_exceptions=True)

    _run(main())


def test_v44_adoption_is_all_or_nothing():
    """Only a COMPLETE coverage is adopted; otherwise the tail rescans."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, {"a"})
        try:
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            pf.feed([("a", "A"), ("b", "B")])
            await pf.finish()
            full = [{"id": 1, "source": "a", "translation": "A"},
                    {"id": 2, "source": "b", "translation": "B"}]
            got = pf.adopt(full)
            assert got is not None, "complete coverage must be adoptable"
            assert got["live"] == [0]
            assert got["flags_by_judge"][0] == {"a": True, "b": False}
            # a pair the pipeline never saw -> no adoption at all
            assert pf.adopt(full + [{"id": 3, "source": "c", "translation": "C"}]) is None

            # not finished yet -> no adoption
            pf2 = core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                                   "Russian", 10)
            pf2.start()
            pf2.feed([("a", "A")])
            assert pf2.adopt([{"id": 1, "source": "a", "translation": "A"}]) is None
            await pf2.finish()
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_verdict_cache_checked_before_queueing(monkeypatch):
    """ТЗ v4.4 п.2: a cached-clean pair costs no tokens — never queued."""
    rec = Recorder()
    _FakeVerdictCache._clean = set()
    monkeypatch.setattr(core, "QAVerdictCache", _FakeVerdictCache)

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, set())
        try:
            cfg = _params(verdict_cache=True)
            pf = core._QAPrefetch(cfg, StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            assert pf.vcache is not None and pf.cfg_hash
            pf.vcache.mark(pf.vcache.key("cached", "CACHED", pf.cfg_hash), "clean")
            pf.start()
            pf.feed([("cached", "CACHED"), ("fresh", "FRESH")])
            await pf.finish()
            assert "cached" in pf._cache_clean
            assert "cached" not in pf._scanned[0], "a cached pair must not be scanned"
            assert "fresh" in pf._scanned[0]
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_cache_skip_shrinks_the_ids_grid_without_crashing(monkeypatch):
    """ТЗ v4.5 п.1: the per-judge ids grid is sized by the LLM batches, but
    the adopted-scan path indexed it with the FULL-batch map. A verdict-cache
    skip (or a machine catch) narrows llm_pairs past a batch boundary, so
    every pair that used to sit in the tail batch blew up with
    IndexError('list index out of range') and the whole audit was lost.

    Twelve pairs, BATCH 10: after three cached-clean skips the grid holds ONE
    batch while pairs #11/#12 still map to batch 1 under the full-batch map.
    """
    rec = Recorder()
    _FakeVerdictCache._clean = set()
    monkeypatch.setattr(core, "QAVerdictCache", _FakeVerdictCache)

    pairs = {f"Alpha {i}": f"Альфа {i}" for i in range(1, 13)}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None, ids_only=False,
                        **kwargs):
        return []

    orig_send = core._qa_send
    orig_scan = core._qa_scan_pairs

    async def main():
        # the pipeline covers ALL twelve pairs while the tail's verdict cache
        # is still empty (nothing is skipped at feed time)
        pf = core._QAPrefetch(_params(verdict_cache=True), StubTranslator(),
                              lambda m: None, None, "Russian", 10)
        pf.start()
        pf.feed(pairs.items())
        await pf.finish()
        return pf

    try:
        # the pipeline flags exactly the pairs that the shrinking will push
        # out of the grid: with the full-batch map they belong to batch 1,
        # but after three cached skips only batch 0 exists.
        core._qa_scan_pairs = _scan_stub(rec, {"Alpha 11", "Alpha 12"})
        pf = _run(main())
        assert pf.ready and pf.adopt([{"id": i, "source": s, "translation": t}
                                      for i, (s, t) in enumerate(pairs.items(), 1)]
                                     ) is not None, "the pipeline must be adoptable"

        # now three of the twelve are cached clean for the TAIL phase only
        for src in ("Alpha 1", "Alpha 2", "Alpha 3"):
            _FakeVerdictCache._clean.add(
                _FakeVerdictCache.key(src, pairs[src], "cfghash"))

        cfg = _params(verdict_cache=True)
        cfg["prefetch"] = pf
        core._qa_send = fake_send
        core._qa_reset_counters()
        out = dict(pairs)
        lines = []
        core.run_qa_phase(out, cfg, StubTranslator(), tq.FakeCache(),
                          lines.append, None)

        # the shrinking really happened — this is the precondition of the bug
        assert any("3 clean pair(s) skipped in phase 1" in l for l in lines), lines
        # the regression: the adopted path indexed the ids grid out of range,
        # which killed the WHOLE audit before a single verdict was applied
        assert not any("phase failed" in l for l in lines), lines
        assert any("no rescan" in l for l in lines), lines
        # the flags that used to land out of range reached their pairs
        assert any("2 finding(s) over 9 pair(s)" in l for l in lines), lines
        assert out["Alpha 11"] != pairs["Alpha 11"], \
            "the adopted flag on the boundary pair was dropped"
        assert out["Alpha 12"] != pairs["Alpha 12"], \
            "the adopted flag on the boundary pair was dropped"
        # untouched pairs keep their text
        assert out["Alpha 4"] == pairs["Alpha 4"]
    finally:
        core._qa_send = orig_send
        core._qa_scan_pairs = orig_scan


def test_v44_broken_batch_blocks_adoption():
    """A batch that failed after its split retry keeps the tail in charge."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, set(), broken={"boom"})
        try:
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            pf.feed([("boom", "BOOM"), ("ok", "OK")])
            await pf.finish()
            assert pf._failed[0], "the failed pair must be recorded as uncovered"
            assert pf.adopt([{"id": 1, "source": "boom", "translation": "BOOM"},
                             {"id": 2, "source": "ok", "translation": "OK"}]) is None
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_fatal_key_error_kills_the_judge():
    """A judge whose whole key set is rejected dies — and is excluded, so
    the tail phase can fall back to single-judge mode."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, set(), fatal={"dead"})
        try:
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            pf.feed([("dead", "DEAD")])
            await pf.finish()
            assert 0 in pf._dead, "the judge must be marked dead"
            assert pf.adopt([{"id": 1, "source": "dead", "translation": "DEAD"}]) is None
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_ready_requires_everything():
    """No keys / no model / unsupported provider -> no pipeline at all.

    NOTE: `keys` is the legacy QA field the tail phase falls back to when
    the provider pool is empty — the fixture ships one, so it is cleared
    here to model a run with genuinely no keys.
    """
    class NoKeys(StubTranslator):
        mixed_pool = []
        api_keys = []

    assert core._QAPrefetch(_params(keys=[]), NoKeys(), lambda m: None, None,
                            "Russian", 10).ready is False
    assert core._QAPrefetch(_params(model=""), StubTranslator(), lambda m: None,
                            None, "Russian", 10).ready is False
    assert core._QAPrefetch(_params(provider="Ollama (Local)"), StubTranslator(),
                            lambda m: None, None, "Russian", 10).ready is False
    assert core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                            "Russian", 10).ready is True


def test_v44_feed_is_idempotent_and_drops_empty():
    """Duplicate/empty pairs never inflate the corpus."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, set())
        try:
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            pf.feed([("a", "A"), ("a", "A"), ("", "X"), ("b", "")])
            await pf.finish()
            assert pf._n == 1
            assert set(pf._source_of.values()) == {"a"}
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_take_phase2_renumbers_ids():
    """Pipelined verdicts arrive with the tail phase's own ids."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, {"flagme"})
        try:
            cfg = _params(jury_threshold=1)
            pf = core._QAPrefetch(cfg, StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            pf.feed([("flagme", "FLAGME")])
            await pf.finish()
            got = pf.take_phase2({"flagme": 77})
            assert 77 in got, got
            assert got[77][0]["id"] == 77
            assert got[77][0]["category"] == "GLOSSARY_VIOLATION"
            assert pf.take_phase2({"unknown": 1}) == {}
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_adoption_keeps_the_scanned_total_identical():
    """ТЗ v4.4 п.4: the tail's `scanned` counter (which drives verdict-cache
    clean-marking) must be the same whether or not the pipeline ran."""
    pairs = {"Alpha text": "Альфа", "Beta text": "Бета"}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None, ids_only=False,
                        **kwargs):
        return []          # everything clean — the cache-marking path

    class RecCache(tq.FakeCache):
        pass

    orig_send = core._qa_send

    def _tail(cfg):
        core._qa_reset_counters()
        out = dict(pairs)
        lines = []
        core.run_qa_phase(out, cfg, StubTranslator(), RecCache(),
                          lines.append, None)
        scanned = [l for l in lines if "scanned" in l]
        return out, scanned

    core._qa_send = fake_send
    try:
        plain_pairs, plain_scanned = _tail(_params())

        async def main():
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None,
                                  None, "Russian", 10)
            pf.start()
            pf.feed([("Alpha text", "Альфа"), ("Beta text", "Бета")])
            await pf.finish()
            return pf

        cfg = _params()
        cfg["prefetch"] = _run(main())
        core._qa_send = fake_send
        piped_pairs, piped_scanned = _tail(cfg)

        assert piped_pairs == plain_pairs
        assert piped_scanned == plain_scanned, \
            f"the scanned total drifted: {piped_scanned} vs {plain_scanned}"
        assert piped_scanned, "the tail must still report its totals"
    finally:
        core._qa_send = orig_send


def test_v44_phase2_pipelines_before_translation_ends():
    """ТЗ v4.4 п.3: the full verdict scan runs as flags arrive, not only
    once the whole file has been translated."""
    rec = Recorder()
    seen = []

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, {"flagme"})
        pf = None
        try:
            cfg = _params(jury_threshold=1)
            pf = core._QAPrefetch(cfg, StubTranslator(), lambda m: None, None,
                                  "Russian", 10)
            pf.start()
            # monkey-patch the phase-2 store so we see WHEN it fills
            orig_consider = pf._consider_phase2

            def spy(p):
                orig_consider(p)
                seen.append(("consider", p["source"]))

            pf._consider_phase2 = spy
            pf.feed([("flagme", "FLAGME")])
            # the verdict is only produced asynchronously: give the workers a
            # slice of time, WITHOUT calling finish() — the file's own
            # translation would still be running at this point
            for _ in range(60):
                await asyncio.sleep(0.02)
                if pf._p2.get("flagme"):
                    break
            assert any(w == "consider" for w, _ in seen), seen
            assert pf._p2.get("flagme"), \
                "phase 2 must complete during the translation, before finish()"
            await pf.finish()
        finally:
            core._qa_scan_pairs = orig
            if pf is not None:
                pf.abort()

    _run(main())


def test_v44_json_manager_feeds_the_pipeline():
    """ТЗ v4.4 п.1 for the JSON engine: JSONManager.process must hand every
    translated batch to the pipeline with the source recovered from the
    flat key (json5 list items included)."""
    import json as _json
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    lang = tmp / "assets" / "test" / "lang"
    lang.mkdir(parents=True)
    (lang / "en_us.json").write_text(
        _json.dumps({"a": "Hello", "b": "World", "c": "Deep"}), encoding="utf-8")
    (lang / "ru_ru.json").write_text("{}", encoding="utf-8")

    class Tr(StubTranslator):
        modpack_root = None
        target_lang_name = "Russian"

        async def translate(self, texts, logger=print, check_status=None, context=""):
            return [f"[ru]{t}" for t in texts]

    class Cache(tq.FakeCache):
        def get(self, t):
            return None

    feeds = []
    orig_feed = core._QAPrefetch.feed

    def spy(self, pairs):
        pairs = list(pairs)
        feeds.append(pairs)
        return orig_feed(self, pairs)

    core._QAPrefetch.feed = spy
    orig_scan = core._qa_scan_pairs
    core._qa_scan_pairs = _scan_stub(Recorder(), {"Hello"})
    try:
        mgr = core.JSONManager(tmp, "ru_ru", Tr(), Cache(), modpack="test",
                               policy="Overwrite (Перезаписать)")
        mgr.qa_params = _params()
        _run(mgr.process())
    finally:
        core._QAPrefetch.feed = orig_feed
        core._qa_scan_pairs = orig_scan

    assert feeds, "JSONManager.process never fed the pipeline"
    fed = dict(p for batch in feeds for p in batch)
    assert fed.get("Hello") == "[ru]Hello", fed
    assert fed.get("Deep") == "[ru]Deep", fed


def test_v44_batch_width_matches_the_tail_phase():
    """The batch width feeds the verdict-cache config hash: a different
    width would silently stop matching every verdict the tail wrote."""
    # the tail clamps qa batch_size to 10..200 (core.py); the pipeline must
    # clamp identically, whatever the TRANSLATION batch size is
    assert core._QAPrefetch(_params(batch_size=5), StubTranslator(),
                            lambda m: None, None, "Russian", 5).BATCH == 10
    assert core._QAPrefetch(_params(batch_size=500), StubTranslator(),
                            lambda m: None, None, "Russian", 500).BATCH == 200
    assert core._QAPrefetch(_params(batch_size=40), StubTranslator(),
                            lambda m: None, None, "Russian", 40).BATCH == 40
    # no QA batch size configured -> the tail's own default (40)
    cfg = _params()
    cfg.pop("batch_size")
    assert core._QAPrefetch(cfg, StubTranslator(), lambda m: None, None,
                            "Russian", 40).BATCH == 40


def test_v44_abort_stops_the_workers():
    """An aborted file must not keep spending tokens in the background."""
    rec = Recorder()

    async def main():
        orig = core._qa_scan_pairs
        core._qa_scan_pairs = _scan_stub(rec, set(), delay=5.0)
        try:
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None,
                                  None, "Russian", 10)
            pf.start()
            pf.feed([("slow", "SLOW")])
            await asyncio.sleep(0.05)
            pf.abort()
            await asyncio.sleep(0.05)
            assert all(t.done() for t in pf._tasks), \
                "abort must leave no live judge workers"
            assert pf._p2_task.done(), "abort must stop the phase-2 worker"
            # a closed pipeline accepts no more work
            pf.feed([("late", "LATE")])
            assert "late" not in pf._scanned[0]
            # abort after a normal finish() is harmless (idempotent)
            pf2 = core._QAPrefetch(_params(), StubTranslator(), lambda m: None,
                                   None, "Russian", 10)
            pf2.start()
            pf2.feed([("ok", "OK")])
            await pf2.finish()
            pf2.abort()
        finally:
            core._qa_scan_pairs = orig

    _run(main())


def test_v44_json_source_recovery_matches_the_tail():
    """json5 list items resolve through their flat "key[N]" keys exactly as
    the tail phase's QA collection does — otherwise the pipeline would feed
    the wrong source strings and adoption would never match."""
    source = {"plain": "Hello", "desc": ["para1", "para2"], "nested": [1, 2]}
    assert core._json_source_of("plain", source) == "Hello"
    assert core._json_source_of("desc[0]", source) == "para1"
    assert core._json_source_of("desc[1]", source) == "para2"
    # out-of-range / malformed / missing keys resolve to None
    assert core._json_source_of("desc[9]", source) is None
    assert core._json_source_of("missing", source) is None
    assert core._json_source_of("desc[x]", source) is None
    # a non-string element resolves to its raw value (the lookup mirrors the
    # tail exactly); the CALL SITE's isinstance filter is what drops it, and
    # such a list never reaches translation anyway (collection requires an
    # all-str list).
    assert core._json_source_of("nested[0]", source) == 1
    assert not (isinstance(core._json_source_of("nested[0]", source), str)
                and core._json_source_of("nested[0]", source))


def test_v44_adoption_leaves_the_tail_result_identical():
    """ТЗ v4.4 п.4 — the decisive promise.

    The SAME tail phase run twice (pipeline vs no pipeline) must produce
    byte-identical translations, the same verdicts and the same totals: the
    pipeline only moves WHEN phase 1/2 run, never WHAT they decide. The QA
    scan is stubbed deterministically so any difference must come from the
    adoption wiring itself.
    """
    pairs = {"Alpha text": "Альфа", "Beta text": "Бета"}
    problems_by_id = {}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None, ids_only=False,
                        **kwargs):
        for p in batch:
            problems_by_id[p["id"]] = p["source"]
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        # HARD: the pair is re-translated through the translator, so the
        # final text visibly differs from the pre-audit translation.
        return [{"id": p["id"], "category": "UNTRANSLATED", "severity": "hard",
                 "issue": "simulated", "suggested": None} for p in batch]

    orig_send = core._qa_send

    def _tail(cfg):
        core._qa_reset_counters()
        out = dict(pairs)
        lines = []
        core.run_qa_phase(out, cfg, StubTranslator(), tq.FakeCache(),
                          lines.append, None)
        return out, lines, dict(core._QA_COUNTERS)

    core._qa_send = fake_send
    try:
        # --- baseline: with NO pipeline at all -------------------------
        plain_pairs, plain_lines, plain_counters = _tail(_params())
        assert plain_pairs["Alpha text"] != "Альфа", \
            "the stub's verdict must actually change the translation"

        # --- with a pipeline whose results are complete -----------------
        async def main():
            pf = core._QAPrefetch(_params(), StubTranslator(), lambda m: None,
                                  None, "Russian", 10)
            pf.start()
            pf.feed([("Alpha text", "Альфа"), ("Beta text", "Бета")])
            await pf.finish()
            return pf

        pf = _run(main())
        cfg = _params()
        cfg["prefetch"] = pf
        core._qa_send = fake_send
        core._qa_reset_counters()
        adopted_pairs = dict(pairs)
        adopted_lines = []
        core.run_qa_phase(adopted_pairs, cfg, StubTranslator(), tq.FakeCache(),
                          adopted_lines.append, None)

        assert adopted_pairs == plain_pairs, \
            "the pipeline must not change a single translation"
        # the phase-1 scan was ADOPTED, not repeated
        assert not any("pipeline: adopting its phase-1 results failed"
                       in l for l in adopted_lines), adopted_lines
        assert any("no rescan" in l for l in adopted_lines), adopted_lines
        # the tail's own totals are untouched (п.4)
        for key in ("hard", "soft_fixed", "warnings", "unresolved"):
            assert core._QA_COUNTERS.get(key, 0) == plain_counters.get(key, 0), \
                f"{key} drifted: {core._QA_COUNTERS} vs {plain_counters}"
    finally:
        core._qa_send = orig_send
