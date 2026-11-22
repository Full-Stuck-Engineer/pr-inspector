"""Unit tests for FileTelemetrySink."""

import json
from pathlib import Path

from pr_inspector.domain.entities import TelemetryRecord
from pr_inspector.infrastructure.telemetry.file_sink import FileTelemetrySink


def test_file_telemetry_sink_records_jsonl(tmp_path: Path):
    log_file = tmp_path / "sub" / "telemetry.jsonl"
    sink = FileTelemetrySink(log_path=log_file)

    record = TelemetryRecord(
        model="qwen2.5-coder:7b",
        input_tokens=250,
        output_tokens=80,
        latency_ms=123.45,
        timestamp="2026-11-20T23:30:00Z",
    )

    sink.record(record)
    assert log_file.exists()

    with open(log_file, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["model"] == "qwen2.5-coder:7b"
    assert data["input_tokens"] == 250
    assert data["latency_ms"] == 123.45
