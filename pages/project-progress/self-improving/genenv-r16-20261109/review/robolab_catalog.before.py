"""RoboLab ``object_catalog.json`` -> gen-env ``robotwin.asset_catalog.v1``.

Only rigid, non-static RoboLab objects whose names map onto a gen-env parser category are
exported.  Every RoboLab object is already Z-up and upright with identity orientation, so the
stable orientation is identity and gen-env's resolved orientation is a pure yaw.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

CATALOG_SCHEMA = "robotwin.asset_catalog.v1"

#: gen-env parser category -> name patterns in the RoboLab catalog (first match wins).
CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("can", re.compile(r"(^canned_|_can$|^corn_can$)")),
    ("plate", re.compile(r"^plate_(small|large)$")),
    ("bowl", re.compile(r"bowl")),
    ("mug", re.compile(r"mug$")),
    ("cup", re.compile(r"(yogurt_cup|coffee_cup)$")),
    ("apple", re.compile(r"^apple(_\d+)?$")),
    ("bottle", re.compile(r"_bottle$")),
    ("block", re.compile(r"_block$")),
)

ROUND = {"can", "plate", "bowl", "mug", "cup", "apple", "bottle"}
ALIASES = {
    "can": ("can", "soda can", "cola can"),
    "plate": ("plate", "dish"),
    "bowl": ("bowl",),
    "mug": ("mug", "coffee mug"),
    "cup": ("cup",),
    "apple": ("apple",),
    "bottle": ("bottle",),
    "block": ("block", "cube"),
}


def category_for(name: str) -> str | None:
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(name):
            return category
    return None


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _model(item: dict[str, Any], category: str, asset_root: str) -> dict[str, Any]:
    dx, dy, dz = (float(v) for v in item["dims"])
    usd = f"{asset_root.rstrip('/')}/{item['usd_path'].removeprefix('assets/')}"
    model: dict[str, Any] = {
        "model_id": 0,
        "model_path": usd,
        "metadata_path": None,
        "visual_path": usd,
        "collision_path": usd,
        "urdf_path": None,
        "scale": [1.0, 1.0, 1.0],
        "dimensions_m": [dx, dy, dz],
        "mass_kg": _positive(item.get("mass")),
        "static_friction": _positive(item.get("static_friction")),
        "dynamic_friction": _positive(item.get("dynamic_friction")),
        "restitution": None,
        "footprint_shape": "circle" if category in ROUND else "box",
        "stable_pose_id": f"robolab_{item['name']}_upright",
        "stable_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "z_policy": "origin_on_table",
        "is_static": False,
        "articulation_joints": [],
        "articulation_closed_qpos": [],
        "articulation_open_qpos": [],
        "usable": True,
        "missing": [],
    }
    if category == "plate":
        # Flat top: keep objects inside the inner 60 % of the rim, resting on the plate's top.
        model.update({
            "support_surface_shape": "circle",
            "support_surface_dimensions_m": [round(0.6 * dx, 4), round(0.6 * dy, 4)],
            "support_surface_z_offset_m": round(dz, 4),
        })
    if category == "bowl":
        model.update({
            "interior_dimensions_m": [round(0.75 * dx, 4), round(0.75 * dy, 4), round(0.8 * dz, 4)],
            "interior_floor_z_offset_m": round(0.15 * dz, 4),
        })
    return model


def build_genenv_catalog(robolab_catalog: list[dict[str, Any]], asset_root: str) -> dict[str, Any]:
    """Build a gen-env catalog dict from RoboLab catalog entries; one gen-env entry per object."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in robolab_catalog:
        name = item.get("name")
        if not name or name in seen:
            continue  # the RoboLab catalog repeats a few names; the first wins, as in RoboLab
        category = category_for(name)
        if category is None or not item.get("rigid_body", False) or item.get("static_body", False):
            continue
        if not item.get("dims") or len(item["dims"]) != 3 or not item.get("usd_path"):
            continue
        seen.add(name)
        entries.append({
            "asset_id": name,
            "semantic_name": category,
            "category": category,
            "aliases": list(ALIASES[category]),
            "colors": [],
            "materials": [],
            "load_type": "rigid",
            "asset_path": f"{asset_root.rstrip('/')}/{Path(item['usd_path']).parent.as_posix().removeprefix('assets/')}",
            "models": [_model(item, category, asset_root)],
            "available": True,
            "availability_reasons": ["robolab_usd_rigid_body"],
            "source_notes": [f"robolab class={item.get('class', '')}", f"usd={item['usd_path']}"],
        })
    entries.sort(key=lambda e: (e["category"], e["asset_id"]))
    digest = hashlib.sha256(json.dumps(robolab_catalog, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "schema_version": CATALOG_SCHEMA,
        "robotwin_root": asset_root,
        "objects_root": f"{asset_root.rstrip('/')}/objects",
        "source_commit": f"robolab-object-catalog-{digest}",
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robolab-catalog", required=True, type=Path)
    parser.add_argument("--asset-root", required=True, help="RoboLab asset root (the directory holding objects/)")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    catalog = build_genenv_catalog(json.loads(args.robolab_catalog.read_text()), args.asset_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, indent=2) + "\n")
    counts: dict[str, int] = {}
    for entry in catalog["entries"]:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    print(json.dumps({"out": str(args.out), "entries": len(catalog["entries"]), "by_category": counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
