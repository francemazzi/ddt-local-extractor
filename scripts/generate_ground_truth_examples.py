#!/usr/bin/env python3
"""Generate per-document ground truth JSON files in Pydantic schema."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ddt_local.benchmark.ground_truth import (
    COLLECTION_FILENAME,
    load_dataset_ground_truth,
)
from ddt_local.models import DocumentoDDT  # noqa: E402


def _write_document(doc: DocumentoDDT, output_dir: Path) -> Path:
    stem = Path(doc.source_filename).stem
    out_path = output_dir / f"{stem}.json"
    payload = doc.model_dump(mode="json")
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return out_path


def _link_or_copy_pdfs(dataset_dir: Path, examples_ddt_dir: Path) -> list[Path]:
    examples_ddt_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for pdf in sorted(dataset_dir.glob("*.pdf")):
        if pdf.name == COLLECTION_FILENAME:
            continue
        target = examples_ddt_dir / pdf.name
        if target.exists() or target.is_symlink():
            target.unlink()
        try:
            target.symlink_to(pdf.resolve())
        except OSError:
            shutil.copy2(pdf, target)
        created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate examples ground truth from dataset/")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "dataset",
        help="Path to dataset directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "examples" / "ground_truth",
        help="Output directory for per-document JSON files",
    )
    parser.add_argument(
        "--ddt-output",
        type=Path,
        default=PROJECT_ROOT / "examples" / "ddt",
        help="Output directory for PDF symlinks/copies",
    )
    args = parser.parse_args()

    gt_path = args.dataset / "ground_truth_ddt.json"
    if not gt_path.exists():
        print(f"Missing ground truth file: {gt_path}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    documents = load_dataset_ground_truth(gt_path)
    written = [_write_document(doc, args.output) for doc in documents.values()]
    pdfs = _link_or_copy_pdfs(args.dataset, args.ddt_output)

    print(f"Wrote {len(written)} ground truth files to {args.output}")
    print(f"Linked/copied {len(pdfs)} PDF files to {args.ddt_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
