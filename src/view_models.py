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
    Ported LINE FOR LINE from layout_skeleton.py.
    """
    width, sizes, avg, coils = cfg["width"], cfg["sizes"], cfg["avg"], cfg["coils"]
    knives, pos = [], 0
    for s_, q in zip(sizes, qty):
        for _ in range(q):
            pos += s_
            knives.append(pos)
    wps = [avg * s_ / width for s_ in sizes]
    total_qty = [q * coils for q in qty]
    total_w = [t * w for t, w in zip(total_qty, wps)]
    scrap_per = scrap / width * avg
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
        scrap_per=scrap_per,
        scrap_total=scrap_per * coils,
        coils=coils,
        avg=avg,
        weight_ok=abs(sum(total_w) + scrap_per * coils - coils * avg) < 0.05
    )


def plan_text(vm: Dict[str, Any]) -> str:
    """Generate text representation of a plan view model."""
    return " + ".join("%dx%d" % (q, sz) for sz, q in zip(vm["sizes"], vm["qty"]) if q) or "-"