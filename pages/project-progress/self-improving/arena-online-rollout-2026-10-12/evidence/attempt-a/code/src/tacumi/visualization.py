from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .camera_runtime import (
    build_deformation_arrow_panel_u8,
    build_depth_panel_u8,
    deformation_to_rgb,
)


HEADER_HEIGHT = 24
PANEL_GAP = 2


def _as_mask(value: Any, shape: tuple[int, int]) -> np.ndarray:
    mask = np.asarray(value, dtype=bool)
    if mask.shape != shape:
        return np.zeros(shape, dtype=bool)
    return mask


def render_indent(indent: Any, mask: Any, indent_max_m: float) -> np.ndarray:
    values = np.asarray(indent, dtype=np.float32)
    valid = _as_mask(mask, values.shape)
    values = np.where(valid & np.isfinite(values), values, 0.0)
    return build_depth_panel_u8(values, indent_max_m=float(indent_max_m))


def render_vector_arrows(
    vectors: Any,
    mask: Any,
    *,
    stride: int,
    scale: float,
    min_magnitude: float,
    y_axis_up: bool,
) -> np.ndarray:
    field = np.asarray(vectors, dtype=np.float32)
    if field.ndim != 3 or field.shape[-1] != 2:
        raise ValueError(f"Expected an HxWx2 vector field, got {field.shape}")
    valid = _as_mask(mask, field.shape[:2])
    return build_deformation_arrow_panel_u8(
        deformation=field,
        mask=valid,
        stride=int(stride),
        scale=float(scale),
        min_mag=float(min_magnitude),
        y_axis_up=bool(y_axis_up),
    )


def render_vector_hsv(vectors: Any, mask: Any, max_magnitude: float) -> np.ndarray:
    field = np.asarray(vectors, dtype=np.float32)
    if field.ndim != 3 or field.shape[-1] != 2:
        raise ValueError(f"Expected an HxWx2 vector field, got {field.shape}")
    valid = _as_mask(mask, field.shape[:2])
    rgb = deformation_to_rgb(field, valid, max_mag=float(max_magnitude))
    rgb[~valid] = 0.0
    return np.clip(255.0 * rgb, 0.0, 255.0).astype(np.uint8)


def _panel_with_label(panel: np.ndarray, label: str) -> np.ndarray:
    header = np.full((HEADER_HEIGHT, panel.shape[1], 3), 13, dtype=np.uint8)
    # Sensor names make the caption long on narrow panels; shrink the type
    # until it fits rather than letting the panel clip it.
    margin = 7
    available = max(panel.shape[1] - 2 * margin, 1)
    scale = 0.42
    while scale > 0.24:
        (width, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        if width <= available:
            break
        scale -= 0.02
    cv2.putText(
        header,
        label,
        (margin, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (226, 232, 238),
        1,
        cv2.LINE_AA,
    )
    return np.concatenate((header, panel), axis=0)


def _sample_stats(sample: dict[str, Any]) -> dict[str, Any]:
    stats = sample.get("stats", {})
    return stats if isinstance(stats, dict) else {}


def render_tactile_composite(
    tactile: dict[str, dict[str, Any]],
    *,
    labels: dict[str, str] | None = None,
) -> np.ndarray:
    """Render one two-pad tactile group.

    ``labels`` renames the panel captions so a multi-group composite (a dual-arm
    rig, or the six-sensor LEAP hand pair) still says which sensor each row is.
    Without it the captions stay LEFT / RIGHT.
    """
    rows: list[np.ndarray] = []
    expected_shape: tuple[int, int] | None = None
    for side in ("left", "right"):
        sample = tactile[side]
        caption = str((labels or {}).get(side, side)).upper()
        indent = np.asarray(sample["indent"], dtype=np.float32)
        deformation = np.asarray(sample["deformation"], dtype=np.float32)
        mask = _as_mask(sample["mask"], indent.shape)
        if indent.ndim != 2 or deformation.shape[:2] != indent.shape:
            raise ValueError(
                f"Incompatible {side} tactile shapes: indent={indent.shape}, "
                f"deformation={deformation.shape}"
            )
        if expected_shape is None:
            expected_shape = indent.shape
        elif indent.shape != expected_shape:
            raise ValueError(
                f"Left/right tactile dimensions differ: {expected_shape} vs {indent.shape}"
            )

        stats = _sample_stats(sample)
        if stats.get("has_contact") is False:
            mask = np.zeros_like(mask, dtype=bool)
        indent_max_m = float(stats.get("indent_max_m", 0.0015))
        stride = int(stats.get("deformation_stride", 16))
        scale = float(stats.get("deformation_scale", 2500.0))
        min_magnitude = float(stats.get("deformation_min_mag", 5.0e-5))
        mode = str(stats.get("deformation_mode", "screen"))
        hsv_max = float(
            stats.get(
                "deformation_hsv_max_mag",
                0.005 if mode in {"world_xy", "world_xz"} else 8.0,
            )
        )
        shear = np.asarray(sample.get("shear", np.zeros_like(deformation)), dtype=np.float32)
        if shear.shape != deformation.shape:
            shear = np.zeros_like(deformation)

        panels = (
            _panel_with_label(render_indent(indent, mask, indent_max_m), f"{caption} / INDENT"),
            _panel_with_label(
                render_vector_arrows(
                    deformation,
                    mask,
                    stride=stride,
                    scale=scale,
                    min_magnitude=min_magnitude,
                    y_axis_up=mode == "world_xy",
                ),
                f"{caption} / DEFORMATION",
            ),
            _panel_with_label(
                render_vector_arrows(
                    shear,
                    mask,
                    stride=stride,
                    scale=scale,
                    min_magnitude=min_magnitude,
                    y_axis_up=mode == "world_xy",
                ),
                f"{caption} / SHEAR",
            ),
            _panel_with_label(
                render_vector_hsv(deformation, mask, hsv_max),
                f"{caption} / HSV",
            ),
        )
        gap = np.zeros((panels[0].shape[0], PANEL_GAP, 3), dtype=np.uint8)
        row_parts: list[np.ndarray] = []
        for index, panel in enumerate(panels):
            if index:
                row_parts.append(gap)
            row_parts.append(panel)
        rows.append(np.concatenate(row_parts, axis=1))

    row_gap = np.zeros((PANEL_GAP, rows[0].shape[1], 3), dtype=np.uint8)
    return np.ascontiguousarray(np.concatenate((rows[0], row_gap, rows[1]), axis=0))
