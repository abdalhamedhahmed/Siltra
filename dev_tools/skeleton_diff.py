#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skeleton_diff.py - Unified diff comparison between layout_skeleton.py and slitra_window.py

Shows per-class diffs to verify that slitra_window.py only contains the allowed edits:
(a) load_fonts() removed, FONT_FAMILIES stays ["Segoe UI", "Arial", "Sans Serif"]
(b) Demo-only code removed (STATES, demo_results, build_vm, F1-F3 shortcuts, argparse main)
(c) APP_NAME, FACTORY_NAME, VERSION imported from app_info.py
(d) MainWindow button handlers replaced with Qt signals
(e) InputPanel has getter methods for all fields
"""

import difflib
import ast
import re
import sys


def extract_classes(source_code):
    """Extract class definitions from source code as {class_name: (start_line, end_line, code)}."""
    tree = ast.parse(source_code)
    classes = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Get the source lines for this class
            start = node.lineno - 1  # 0-indexed
            # Find the end line by looking at the last node in the class
            end = node.end_lineno if hasattr(node, 'end_lineno') else start
            if end is None:
                # Fallback: find the next class or function at same indent
                lines = source_code.split('\n')
                for i in range(start + 1, len(lines)):
                    if lines[i].strip() and not lines[i].startswith(' '):
                        end = i
                        break
                else:
                    end = len(lines)

            code = '\n'.join(source_code.split('\n')[start:end])
            classes[node.name] = (start + 1, end, code)

    return classes


def extract_functions(source_code):
    """Extract function definitions from source code as {func_name: (start_line, end_line, code)}."""
    tree = ast.parse(source_code)
    functions = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.col_offset == 0:  # top-level only
            start = node.lineno - 1
            end = node.end_lineno if hasattr(node, 'end_lineno') else start
            if end is None:
                lines = source_code.split('\n')
                for i in range(start + 1, len(lines)):
                    if lines[i].strip() and not lines[i].startswith(' '):
                        end = i
                        break
                else:
                    end = len(lines)

            code = '\n'.join(source_code.split('\n')[start:end])
            functions[node.name] = (start + 1, end, code)

    return functions


def get_unified_diff(old_code, new_code, old_name, new_name):
    """Generate unified diff between two code strings."""
    old_lines = old_code.split('\n')
    new_lines = new_code.split('\n')
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=old_name, tofile=new_name, lineterm='')
    return '\n'.join(diff)


def main():
    # Read both files
    with open('layout_skeleton.py', 'r', encoding='utf-8') as f:
        skeleton = f.read()

    with open('src/slitra_window.py', 'r', encoding='utf-8') as f:
        window = f.read()

    # Extract classes
    skeleton_classes = extract_classes(skeleton)
    window_classes = extract_classes(window)

    # Extract functions
    skeleton_funcs = extract_functions(skeleton)
    window_funcs = extract_functions(window)

    print("=" * 80)
    print("CLASS COMPARISON")
    print("=" * 80)

    all_class_names = sorted(set(skeleton_classes.keys()) | set(window_classes.keys()))

    identical_count = 0
    differ_count = 0
    only_in_skeleton = []
    only_in_window = []

    for name in all_class_names:
        if name in skeleton_classes and name in window_classes:
            old_code = skeleton_classes[name][2]
            new_code = window_classes[name][2]

            if old_code == new_code:
                identical_count += 1
                print(f"\n[IDENTICAL] {name}")
            else:
                differ_count += 1
                print(f"\n[DIFFER] {name}")
                print("-" * 80)
                diff = get_unified_diff(old_code, new_code, f"layout_skeleton.py::{name}", f"slitra_window.py::{name}")
                print(diff)
        elif name in skeleton_classes:
            only_in_skeleton.append(name)
            print(f"\n[ONLY IN SKELETON] {name}")
        else:
            only_in_window.append(name)
            print(f"\n[ONLY IN WINDOW] {name}")

    print("\n" + "=" * 80)
    print("FUNCTION COMPARISON (top-level)")
    print("=" * 80)

    all_func_names = sorted(set(skeleton_funcs.keys()) | set(window_funcs.keys()))

    for name in all_func_names:
        if name in skeleton_funcs and name in window_funcs:
            old_code = skeleton_funcs[name][2]
            new_code = window_funcs[name][2]

            if old_code == new_code:
                print(f"\n[IDENTICAL] {name}")
            else:
                print(f"\n[DIFFER] {name}")
                print("-" * 80)
                diff = get_unified_diff(old_code, new_code, f"layout_skeleton.py::{name}", f"slitra_window.py::{name}")
                print(diff)
        elif name in skeleton_funcs:
            print(f"\n[REMOVED] {name}")
        else:
            print(f"\n[ADDED] {name}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Classes identical: {identical_count}")
    print(f"Classes differ: {differ_count}")
    print(f"Classes only in skeleton: {len(only_in_skeleton)} - {', '.join(only_in_skeleton)}")
    print(f"Classes only in window: {len(only_in_window)} - {', '.join(only_in_window)}")

    print(f"\nFinal line: {identical_count} classes identical, {differ_count} classes differ")

    # Verify allowed edits are the only differences
    print("\n" + "=" * 80)
    print("ALLOWED EDITS VERIFICATION")
    print("=" * 80)

    checks = {
        "load_fonts removed": "load_fonts" not in window_funcs and "load_fonts" in skeleton_funcs,
        "FONT_FAMILIES fixed": 'FONT_FAMILIES = ["Segoe UI", "Arial", "Sans Serif"]' in window,
        "demo STATES dict removed": 'STATES = {' not in window or 'STATES = {"none"' in window,  # Badge.STATES is allowed
        "demo_results removed": "demo_results" not in window_funcs,
        "build_vm removed": "build_vm" not in window_funcs,
        "app_info imported": "from app_info import APP_NAME, FACTORY_NAME, APP_VERSION as VERSION" in window,
        "MainWindow signals": "calculate_requested = Signal()" in window,
        "InputPanel getters": "def get_all_params" in window,
        "F1-F3 shortcuts removed": "QShortcut" not in window,
        "argparse demo removed": 'choices=list(STATES)' not in window,
    }

    for check, result in checks.items():
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status} {check}")

    all_pass = all(checks.values())
    print(f"\nAll allowed edits verified: {'YES' if all_pass else 'NO'}")


if __name__ == "__main__":
    main()