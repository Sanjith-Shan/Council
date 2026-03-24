"""AgentHarm dataset loader and processor."""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DATASET_NAME = "ai-safety-institute/AgentHarm"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_PATH = DATA_DIR / "agentharm_processed.json"

# (config_name, dataset_split, source_label, harmful)
SPLIT_CONFIGS = [
    ("harmful", "test_public", "test_public", True),
    ("harmless_benign", "test_public", "test_public_benign", False),
    ("harmful", "validation", "val", True),
]

try:  # Optional dependency
    from datasets import DatasetDict, load_dataset  # type: ignore
except Exception:  # pragma: no cover
    DatasetDict = None  # type: ignore
    load_dataset = None  # type: ignore

try:
    from huggingface_hub import snapshot_download  # type: ignore
except Exception:  # pragma: no cover
    snapshot_download = None  # type: ignore

logger = logging.getLogger(__name__)


def load_agentharm(force_refresh: bool = False) -> List[Dict]:
    """Load the processed AgentHarm dataset, downloading if necessary."""

    if PROCESSED_PATH.exists() and not force_refresh:
        data = json.loads(PROCESSED_PATH.read_text())
        _print_summary(data, cached=True)
        return data

    records = _build_processed_records()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.write_text(json.dumps(records, indent=2))
    _print_summary(records, cached=False)
    return records


def _build_processed_records() -> List[Dict]:
    datasets_map = _load_via_datasets()
    if not datasets_map:
        datasets_map = _load_via_snapshot()

    if not datasets_map:
        raise RuntimeError("Unable to load AgentHarm dataset via datasets or snapshot download")

    processed: List[Dict] = []
    counter = 1
    for config_name, dataset_split, source_label, harmful in SPLIT_CONFIGS:
        rows = datasets_map.get((config_name, dataset_split), [])
        for row in rows:
            description = row.get("prompt") or row.get("detailed_prompt") or row.get("name")
            tools = row.get("target_functions") or []
            processed.append(
                {
                    "id": f"ah_{counter:03d}",
                    "description": description,
                    "tools": tools,
                    "category": row.get("category") or "unknown",
                    "harmful": harmful,
                    "source_split": source_label,
                }
            )
            counter += 1
    return processed


def _load_via_datasets() -> Optional[Dict[tuple, List[Dict]]]:
    if load_dataset is None:
        return None

    datasets_map: Dict[tuple, List[Dict]] = {}
    configs = {cfg for cfg, *_ in SPLIT_CONFIGS}
    try:
        for cfg in configs:
            ds: DatasetDict = load_dataset(DATASET_NAME, cfg)  # type: ignore
            for split in ds.keys():
                datasets_map[(cfg, split)] = list(ds[split])
    except Exception as exc:  # pragma: no cover - falls back to snapshot
        logger.warning("load_dataset failed for %s: %s", DATASET_NAME, exc)
        return None
    return datasets_map


def _load_via_snapshot() -> Optional[Dict[tuple, List[Dict]]]:
    if snapshot_download is None:
        return None

    try:
        snapshot_path = Path(
            snapshot_download(DATASET_NAME, repo_type="dataset", allow_patterns=["benchmark/*.json", "benchmark/*.parquet", "benchmark/*.jsonl"], ignore_patterns=["*__pycache__*"])
        )
    except Exception as exc:  # pragma: no cover - network issues
        logger.warning("snapshot_download failed for %s: %s", DATASET_NAME, exc)
        return None

    benchmark_dir = snapshot_path / "benchmark"
    datasets_map: Dict[tuple, List[Dict]] = {}
    file_mapping = {
        ("harmful", "test_public"): benchmark_dir / "harmful_behaviors_test_public.json",
        ("harmless_benign", "test_public"): benchmark_dir / "benign_behaviors_test_public.json",
        ("harmful", "validation"): benchmark_dir / "harmful_behaviors_validation.json",
    }

    for key, file_path in file_mapping.items():
        if not file_path.exists():
            continue
        payload = json.loads(file_path.read_text())
        rows = payload.get("behaviors") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            datasets_map[key] = rows
    return datasets_map


def _print_summary(data: Iterable[Dict], cached: bool) -> None:
    data_list = list(data) if not isinstance(data, list) else data
    total = len(data_list)
    harmful_count = sum(1 for item in data_list if item.get("harmful"))
    benign_count = total - harmful_count
    categories = Counter(item.get("category", "unknown") for item in data_list)
    prefix = "Loaded cached" if cached else "Processed"
    print(f"{prefix} AgentHarm behaviors: {total} total")
    print(f" - Harmful: {harmful_count}")
    print(f" - Benign: {benign_count}")
    print(" - Categories:")
    for category, count in sorted(categories.items()):
        print(f"   * {category}: {count}")


__all__ = ["load_agentharm"]
