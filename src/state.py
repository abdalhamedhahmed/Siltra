#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slitra/state.py - Application state management for Slitra

This module contains state management classes that are independent of UI.
"""

from typing import Dict, Any, List, Optional


class MemoryStore:
    """Pinned combinations. Each keeps its whole plan, so plans from different calculations can be compared."""
    MAX = 50

    def __init__(self):
        self.items: List[Dict[str, Any]] = []
        self._next = 1

    def __len__(self) -> int:
        return len(self.items)

    def find(self, calc: Any, src: Any) -> Optional[Dict[str, Any]]:
        return next((i for i in self.items if i["calc"] == calc and i["src"] == src), None)

    def add(self, vm: Dict[str, Any], calc: Any, src: Any, rank: int) -> Optional[Dict[str, Any]]:
        if len(self.items) >= self.MAX:
            return None
        item = dict(id=self._next, vm=vm, calc=calc, src=src, rank=rank)
        self._next += 1
        self.items.append(item)
        return item

    def remove(self, item: Dict[str, Any]) -> None:
        self.items.remove(item)

    def clear(self) -> None:
        self.items = []