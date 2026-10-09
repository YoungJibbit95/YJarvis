import asyncio
from pathlib import Path

import jarvis_agent.main as main_module
from jarvis_agent.db import Database


def _build_temp_db(tmp_path: Path) -> Database:
    whisper_model = tmp_path / "models" / "ggml-base.bin"
    whisper_model.parent.mkdir(parents=True, exist_ok=True)
    whisper_model.write_text("stub", encoding="utf-8")
    return Database(
        db_path=tmp_path / "jarvis-test.db",
        project_root=tmp_path,
        default_whisper_model=whisper_model,
    )


def test_run_perf_metrics_persistence_and_aggregates(tmp_path: Path):
    async def _run() -> None:
        db = _build_temp_db(tmp_path)
        await db.init()
        await db.create_session("session-1")

        await db.upsert_run_perf_metrics(
            run_id="run-1",
            session_id="session-1",
            intent_decision_ms=20,
            prompt_build_ms=30,
            ttft_ms=120,
            tool_exec_ms=250,
            run_total_ms=900,
            approval_wait_ms=0,
        )
        await db.upsert_run_perf_metrics(
            run_id="run-2",
            session_id="session-1",
            intent_decision_ms=40,
            prompt_build_ms=35,
            ttft_ms=140,
            tool_exec_ms=300,
            run_total_ms=1200,
            approval_wait_ms=200,
        )

        overview = await db.get_run_perf_overview()
        assert overview["sample_size"] >= 2
        assert overview["metrics"]["ttft_ms"]["p50"] >= 120
        assert overview["metrics"]["run_total_ms"]["p95"] >= 1100

    asyncio.run(_run())


def test_perf_overview_endpoint_returns_metrics(tmp_path: Path):
    async def _run() -> None:
        db = _build_temp_db(tmp_path)
        await db.init()
        await db.create_session("session-2")
        await db.upsert_run_perf_metrics(
            run_id="run-api-1",
            session_id="session-2",
            intent_decision_ms=18,
            prompt_build_ms=22,
            ttft_ms=95,
            tool_exec_ms=210,
            run_total_ms=700,
            approval_wait_ms=15,
        )

        original_database = main_module.database
        try:
            main_module.database = db
            response = await main_module.get_perf_overview()
        finally:
            main_module.database = original_database

        assert response.sample_size >= 1
        assert response.metrics["run_total_ms"].p50 >= 700
        assert response.metrics["ttft_ms"].p50 >= 90

    asyncio.run(_run())
