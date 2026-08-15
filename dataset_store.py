from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from youtube_service import ReportResult


SCHEMA_VERSION = 1


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def report_to_dataset(report: ReportResult, exclusion_days: int, window_days: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "query": {"exclusion_days": exclusion_days, "window_days": window_days},
        "report": asdict(report),
    }


def validate_dataset(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("This dataset version is not supported.")
    query = data.get("query", {})
    report = data.get("report", {})
    required = ("rows", "catalog", "start_date", "end_date", "generated_at")
    if not all(key in report for key in required):
        raise ValueError("The file is not a complete Back Catalog Pulse dataset.")
    exclusion = int(query.get("exclusion_days", 0))
    window = int(query.get("window_days", 0))
    if exclusion < 1 or window < 1:
        raise ValueError("The dataset has invalid query parameters.")
    return data


def save_dataset(directory: Path, data: dict[str, Any]) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    generated_value = data["report"]["generated_at"]
    generated = generated_value if isinstance(generated_value, datetime) else datetime.fromisoformat(generated_value.replace("Z", "+00:00"))
    base = generated.strftime("%Y%m%d-%H%M%S")
    filename = f"{base}-exclude-{data['query']['exclusion_days']}-window-{data['query']['window_days']}.json"
    path = directory / filename
    suffix = 2
    while path.exists():
        path = directory / f"{base}-{suffix}-exclude-{data['query']['exclusion_days']}-window-{data['query']['window_days']}.json"
        suffix += 1
    path.write_text(json.dumps(data, indent=2, default=_json_default), encoding="utf-8")
    return path.name


def load_dataset(directory: Path, filename: str) -> dict[str, Any]:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".json"):
        raise ValueError("Invalid dataset filename.")
    return validate_dataset(json.loads((directory / safe_name).read_text(encoding="utf-8")))


def list_datasets(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    items = []
    for path in directory.glob("*.json"):
        try:
            data = load_dataset(directory, path.name)
            report = data["report"]
            items.append({
                "filename": path.name,
                "generated_at": report["generated_at"],
                "exclusion_days": data["query"]["exclusion_days"],
                "window_days": data["query"]["window_days"],
                "row_count": len(report["rows"]),
                "eligible_count": len(report.get("catalog", report["rows"])),
                "total_count": len(report.get("catalog", report["rows"])) + report.get("excluded_recent_count", 0) if report.get("excluded_recent_count") is not None else None,
            })
        except (ValueError, OSError, json.JSONDecodeError, KeyError):
            continue
    return sorted(items, key=lambda item: item["generated_at"], reverse=True)


def import_dataset(directory: Path, raw: bytes, original_name: str) -> str:
    if len(raw) > 25 * 1024 * 1024:
        raise ValueError("Dataset is larger than the 25 MB import limit.")
    data = validate_dataset(json.loads(raw.decode("utf-8")))
    clean_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(original_name).stem).strip("-.") or "imported"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{clean_stem}.json"
    counter = 2
    while path.exists():
        path = directory / f"{clean_stem}-{counter}.json"
        counter += 1
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path.name
