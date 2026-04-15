#!/usr/bin/env python3
"""Merge OpenLane JSON config fragments.

Usage:
    python3 merge_configs.py --stage 2_floorplan
    python3 merge_configs.py --stage 4_placement --output config.placement.json
    python3 merge_configs.py --manifest all.json --output config.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge staged OpenLane JSON configs")
    parser.add_argument(
        "--config-dir",
        default="config_stages",
        help="Directory containing numbered stage JSON files (default: config_stages)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Manifest JSON array of file names inside config-dir (example: all.json)",
    )
    parser.add_argument(
        "--stage",
        choices=["1_syn", "2_floorplan", "3_powerplan", "4_placement", "5_cts", "6_routing", "7_signoff", "timing"],
        default=None,
        help="Merge 1_syn.json plus one stage file",
    )
    parser.add_argument(
        "--output",
        default="config.json",
        help="Output merged JSON path (default: config.json)",
    )

    args = parser.parse_args()
    config_dir = Path(args.config_dir)

    if args.manifest and args.stage:
        raise ValueError("Use either --manifest or --stage, not both")

    if args.manifest:
        manifest_path = config_dir / args.manifest
        with manifest_path.open("r", encoding="utf-8") as f:
            names = json.load(f)
        if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
            raise ValueError(f"Manifest {manifest_path} must be a JSON array of file names")
        parts = [config_dir / name for name in names]
    elif args.stage:
        parts = [config_dir / "1_syn.json", config_dir / f"{args.stage}.json"]
    else:
        raise ValueError("Provide either --stage or --manifest")

    merged: Dict[str, Any] = {}
    for part in parts:
        merged = deep_merge(merged, load_json(part))

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
        f.write("\n")

    print(f"Merged {len(parts)} files into {output_path}")


if __name__ == "__main__":
    main()
