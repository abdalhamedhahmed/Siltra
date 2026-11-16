#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slitra/view_models.py - View model builders for Slitra

This module contains pure functions that build view models from calculation data.
No UI dependencies - only standard library and typing.
"""

from typing import Dict, Any, List


def plan_vm(cfg: Dict[str, Any], scrap: float, qty: List[int]) -> Dict[str, Any]:
    """
    Everything the 'Selected Combination' area needs for ONE plan (any row of the results).
    Now uses material-weight calculation engine for accurate strip weights.
    """
    width, sizes, avg, coils = cfg["width"], cfg["sizes"], cfg["avg"], cfg["coils"]
    material_type = cfg.get("material_type", "HR")
    thickness_mm = cfg.get("thickness", 0.5)
    theoretical_length_m = cfg.get("theoretical_length_m", 0.0)

    # Compute knife positions
    knives, pos = [], 0
    for s_, q in zip(sizes, qty):
        for _ in range(q):
            pos += s_
            knives.append(pos)

    # Calculate weights using material-weight engine if we have the data
    if theoretical_length_m > 0 and thickness_mm > 0:
        try:
            import material_calc
            # Weight per strip for each size
            wps = material_calc.CoilWeightCalculator.compute_strip_weights(
                material_type, theoretical_length_m, sizes, thickness_mm
            )
            # Total weight per strip size (qty * coils)
            total_qty = [q * coils for q in qty]
            total_w = [wps[i] * total_qty[i] for i in range(len(sizes))]

            # Scrap weight
            scrap_per_coil = material_calc.CoilWeightCalculator.compute_scrap_weight(
                material_type, theoretical_length_m, scrap, thickness_mm
            )
            scrap_total = scrap_per_coil * coils
        except Exception:
            # Fallback to simple calculation
            wps = [avg * s_ / width for s_ in sizes]
            total_qty = [q * coils for q in qty]
            total_w = [t * w for t, w in zip(total_qty, wps)]
            scrap_per_coil = scrap / width * avg
            scrap_total = scrap_per_coil * coils
    else:
        # Fallback to simple calculation
        wps = [avg * s_ / width for s_ in sizes]
        total_qty = [q * coils for q in qty]
        total_w = [t * w for t, w in zip(total_qty, wps)]
        scrap_per_coil = scrap / width * avg
        scrap_total = scrap_per_coil * coils

    return dict(
        width=width,
        sizes=sizes,
        qty=list(qty),
        scrap=scrap,
        used=width - scrap,
        pct=scrap / width * 100,
        strips=sum(qty),
        knives=knives,
        wps=wps,
        total_qty=total_qty,
        total_w=total_w,
        scrap_per=scrap_per_coil,
        scrap_total=scrap_total,
        coils=coils,
        avg=avg,
        weight_ok=abs(sum(total_w) + scrap_total - coils * avg) < 0.05,
        # New fields for material-weight display
        material_type=material_type,
        thickness_mm=thickness_mm,
        theoretical_length_m=theoretical_length_m,
    )


def plan_text(vm: Dict[str, Any]) -> str:
    """Generate text representation of a plan view model."""
    return " + ".join("%dx%d" % (q, sz) for sz, q in zip(vm["sizes"], vm["qty"]) if q) or "-"