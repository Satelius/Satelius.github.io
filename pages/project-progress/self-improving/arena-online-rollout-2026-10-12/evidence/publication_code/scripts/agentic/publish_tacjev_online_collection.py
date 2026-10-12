#!/usr/bin/env python3
"""Publish genuine online attempts; retain diagnostics and gate training views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "src"):
    sys.path.insert(0, str(directory))

from tacharness.isaaclab.tacjev_online_dataset import publish_online_collection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--known-error-receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = publish_online_collection(args.run, args.output, known_error_receipts=args.known_error_receipt)
    print(json.dumps({key: result[key] for key in ("catalog", "manifest", "manifest_sha256",
        "diagnostic_episodes", "positive_episodes", "sample_count", "training_sample_count")}))


if __name__ == "__main__":
    main()
