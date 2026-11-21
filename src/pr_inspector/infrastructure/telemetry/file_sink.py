"""File-based telemetry sink recording metrics in JSON Lines format."""

import json
from dataclasses import asdict
from pathlib import Path

from pr_inspector.domain.entities import TelemetryRecord


class FileTelemetrySink:
    """Appends telemetry records to a local JSONL log file."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or Path(".pr-inspector/telemetry.jsonl")

    def record(self, telemetry: TelemetryRecord) -> None:
        """Append record as single JSON line."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(telemetry)) + "\n")
