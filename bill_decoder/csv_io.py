"""CSV helpers - always go through the csv module (correct quoting, UTF-8)."""
from __future__ import annotations

import csv
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def read_rows(path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_rows(path, fieldnames: list[str], rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def find_image(folder, bill_id: str) -> Path | None:
    """bill_id is the file name without extension (KESC_0002 -> bills/KESC_0002.png)."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    for p in sorted(folder.iterdir()):
        if p.stem == bill_id and p.suffix.lower() in IMAGE_EXTS:
            return p
    return None
