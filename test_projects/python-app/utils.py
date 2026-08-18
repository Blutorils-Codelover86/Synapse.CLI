"""Utility functions for data processing."""
import hashlib
import json
from pathlib import Path


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def chunk_list(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]
