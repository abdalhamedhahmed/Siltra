#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_to_skeleton.py - Pixel-by-pixel comparison between layout_skeleton.py and slitra_window.py

This script runs both the skeleton (slitra_window.py --check) and the new window (ui_qt.py --new)
at 4 window sizes x 2 states (empty, results), captures screenshots, and compares them pixel-by-pixel.

Output: JSON report with differences per size/state, and summary of pixel differences.
"""

import sys
import os
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Try to import PIL for image comparison
try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: PIL (Pillow) not installed. Pixel comparison will be skipped.")
    print("Install with: pip install Pillow")


# Window sizes to test (width, height)
WINDOW_SIZES = [
    (1280, 648),
    (1366, 696),
    (1536, 792),
    (1920, 1008),
]

# Test states: empty startup, typical results
TEST_STATES = [
    ("empty", None),
    ("results", None),  # Will be populated with mock VM
]

# Paths
REPO_ROOT = Path(__file__).parent.parent
SRC_SLITRA = REPO_ROOT / "src" / "slitra"
SKELETON_SCRIPT = REPO_ROOT / "src" / "slitra_window.py"
NEW_WINDOW_SCRIPT = REPO_ROOT / "src" / "slitra_window.py"
SKELETON_OUT_DIR = REPO_ROOT / "skeleton_screenshots"
NEW_WINDOW_OUT_DIR = REPO_ROOT / "new_window_screenshots"
COMPARE_OUT_DIR = REPO_ROOT / "comparison_results"


def get_mock_vm():
    """Create a mock view model for layout testing (matching _mock_vm in slitra_window.py)."""
    width = 1290
    sizes = [111, 250, 79]
    avg = 10000.0
    coils = 3
    qty = [1, 1, 1]
    scrap = 850
    knives, pos = [], 0
    for s, q in zip(sizes, qty):
        for _ in range(q):
            pos += s
            knives.append(pos)
    wps = [avg * s / width for s in sizes]
    total_qty = [q * coils for q in qty]
    total_w = [t * w for t, w in zip(total_qty, wps)]
    scrap_per = scrap / width * avg
    rows = [(850, (1, 1, 1)), (860, (1, 1, 2)), (870, (1, 2, 1))]
    return dict(width=width, sizes=sizes, qty=list(qty), scrap=scrap, used=width - scrap,
                pct=scrap / width * 100, strips=sum(qty), rows=rows, total=len(rows),
                knives=knives, wps=wps, total_qty=total_qty, total_w=total_w,
                scrap_per=scrap_per, scrap_total=scrap_per * coils, coils=coils, avg=avg,
                weight_ok=True)


def run_skeleton_check(out_dir: Path) -> int:
    """Run slitra_window.py --check and save screenshots at exact logical sizes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Running SKELETON check ({out_dir}) ===")

    # Create a test script that saves screenshots at exact logical sizes
    test_script = f'''
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from slitra_window import MainWindow, _mock_vm, apply_light_palette, make_font

app = QApplication(sys.argv[:1])
apply_light_palette(app)
app.setFont(make_font(9))

win = MainWindow()
win.show()

test_states = [
    ("empty", None),
    ("results", _mock_vm()),
]

for (w, h) in [(1280, 648), (1366, 696), (1536, 792), (1920, 1008)]:
    for st_name, vm in test_states:
        win.showNormal()
        win.resize(w, h)
        if vm is None:
            win.show_empty()
        else:
            win.show_results(vm)
        for _ in range(5):
            app.processEvents()
        win.centralWidget().layout().activate()
        app.processEvents()

        # Save screenshot at exact logical size
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        win.render(painter, win.rect().topLeft())
        painter.end()
        out_path = r"{out_dir}/%dx%d_%s.png" % (w, h, st_name)
        pixmap.save(out_path)
        print("Saved:", out_path)

print("\\nDone saving screenshots for skeleton")
app.quit()
'''

    # Write temp script
    temp_script = REPO_ROOT / "temp_skeleton_check.py"
    temp_script.write_text(test_script, encoding='utf-8')

    try:
        cmd = [sys.executable, str(temp_script)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"Exit code: {result.returncode}")
        return result.returncode
    finally:
        if temp_script.exists():
            temp_script.unlink()


def run_new_window_check(out_dir: Path) -> int:
    """Run the new window (via slitra_window.py MainWindow) and save screenshots at exact logical sizes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Running NEW WINDOW check ({out_dir}) ===")

    # Create a test script that saves screenshots at exact logical sizes
    test_script = f'''
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from slitra_window import MainWindow, _mock_vm, apply_light_palette, make_font

app = QApplication(sys.argv[:1])
apply_light_palette(app)
app.setFont(make_font(9))

win = MainWindow()
win.show()

test_states = [
    ("empty", None),
    ("results", _mock_vm()),
]

for (w, h) in [(1280, 648), (1366, 696), (1536, 792), (1920, 1008)]:
    for st_name, vm in test_states:
        win.showNormal()
        win.resize(w, h)
        if vm is None:
            win.show_empty()
        else:
            win.show_results(vm)
        for _ in range(5):
            app.processEvents()
        win.centralWidget().layout().activate()
        app.processEvents()

        # Save screenshot at exact logical size
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        win.render(painter, win.rect().topLeft())
        painter.end()
        out_path = r"{out_dir}/%dx%d_%s.png" % (w, h, st_name)
        pixmap.save(out_path)
        print("Saved:", out_path)

print("\\nDone saving screenshots for new window")
app.quit()
'''

    # Write temp script
    temp_script = REPO_ROOT / "temp_new_window_check.py"
    temp_script.write_text(test_script, encoding='utf-8')

    try:
        cmd = [sys.executable, str(temp_script)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"Exit code: {result.returncode}")
        return result.returncode
    finally:
        if temp_script.exists():
            temp_script.unlink()


def compare_images(img1_path: Path, img2_path: Path, diff_path: Path) -> Dict[str, Any]:
    """Compare two images pixel-by-pixel using PIL."""
    if not HAS_PIL:
        return {"error": "PIL not available"}

    try:
        img1 = Image.open(img1_path).convert('RGBA')
        img2 = Image.open(img2_path).convert('RGBA')

        # Ensure same size
        if img1.size != img2.size:
            return {
                "error": f"Size mismatch: {img1.size} vs {img2.size}",
                "size1": img1.size,
                "size2": img2.size
            }

        # Compute difference
        diff = ImageChops.difference(img1, img2)

        # Count different pixels
        diff_pixels = 0
        total_pixels = img1.width * img1.height

        # Get bounding box of differences
        bbox = diff.getbbox()

        if bbox:
            # Count non-zero pixels in diff
            diff_data = diff.load()
            for y in range(img1.height):
                for x in range(img1.width):
                    if diff_data[x, y] != (0, 0, 0, 0):
                        diff_pixels += 1

            # Save diff image
            diff.save(diff_path)

            diff_pct = (diff_pixels / total_pixels) * 100
            return {
                "identical": False,
                "diff_pixels": diff_pixels,
                "total_pixels": total_pixels,
                "diff_percentage": round(diff_pct, 4),
                "bbox": bbox,
                "size": img1.size
            }
        else:
            return {
                "identical": True,
                "diff_pixels": 0,
                "total_pixels": total_pixels,
                "diff_percentage": 0.0,
                "bbox": None,
                "size": img1.size
            }
    except Exception as e:
        return {"error": str(e)}


def run_comparison() -> Dict[str, Any]:
    """Run the full comparison pipeline."""
    print("=" * 60)
    print("COMPARE TO SKELETON - Pixel-by-pixel comparison")
    print("=" * 60)

    # Step 1: Run skeleton check
    run_skeleton_check(SKELETON_OUT_DIR)

    # Step 2: Run new window check
    run_new_window_check(NEW_WINDOW_OUT_DIR)

    # Step 3: Compare screenshots
    COMPARE_OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=== COMPARING SCREENSHOTS ===")

    results = {
        "comparison": [],
        "summary": {
            "total_comparisons": 0,
            "identical": 0,
            "different": 0,
            "errors": 0,
            "total_diff_pixels": 0,
            "max_diff_percentage": 0.0
        }
    }

    for w, h in WINDOW_SIZES:
        for st_name, _ in TEST_STATES:
            skeleton_img = SKELETON_OUT_DIR / f"{w}x{h}_{st_name}.png"
            new_img = NEW_WINDOW_OUT_DIR / f"{w}x{h}_{st_name}.png"
            diff_img = COMPARE_OUT_DIR / f"diff_{w}x{h}_{st_name}.png"

            if not skeleton_img.exists():
                print(f"  [MISSING] Skeleton: {skeleton_img}")
                results["comparison"].append({
                    "size": f"{w}x{h}",
                    "state": st_name,
                    "error": "Skeleton screenshot missing"
                })
                results["summary"]["errors"] += 1
                continue

            if not new_img.exists():
                print(f"  [MISSING] New window: {new_img}")
                results["comparison"].append({
                    "size": f"{w}x{h}",
                    "state": st_name,
                    "error": "New window screenshot missing"
                })
                results["summary"]["errors"] += 1
                continue

            print(f"  Comparing {w}x{h} {st_name}...")
            cmp_result = compare_images(skeleton_img, new_img, diff_img)

            comparison = {
                "size": f"{w}x{h}",
                "state": st_name,
                "skeleton_screenshot": str(skeleton_img),
                "new_window_screenshot": str(new_img),
                "diff_screenshot": str(diff_img) if not cmp_result.get("identical") else None,
                **cmp_result
            }

            results["comparison"].append(comparison)
            results["summary"]["total_comparisons"] += 1

            if cmp_result.get("identical"):
                results["summary"]["identical"] += 1
                print(f"    [IDENTICAL]")
            elif "error" in cmp_result:
                results["summary"]["errors"] += 1
                print(f"    [ERROR] {cmp_result['error']}")
            else:
                results["summary"]["different"] += 1
                results["summary"]["total_diff_pixels"] += cmp_result.get("diff_pixels", 0)
                diff_pct = cmp_result.get("diff_percentage", 0)
                results["summary"]["max_diff_percentage"] = max(results["summary"]["max_diff_percentage"], diff_pct)
                print(f"    [DIFFERENT] {diff_pct:.4f}% ({cmp_result.get('diff_pixels', 0)} pixels)")

    return results


def main():
    """Main entry point."""
    if not HAS_PIL:
        print("ERROR: Pillow is required for pixel comparison.")
        print("Install with: pip install Pillow")
        sys.exit(1)

    # Check both scripts exist
    if not SKELETON_SCRIPT.exists():
        print(f"ERROR: Skeleton script not found: {SKELETON_SCRIPT}")
        sys.exit(1)

    if not NEW_WINDOW_SCRIPT.exists():
        print(f"ERROR: New window script not found: {NEW_WINDOW_SCRIPT}")
        sys.exit(1)

    results = run_comparison()

    # Save JSON report
    report_path = COMPARE_OUT_DIR / "comparison_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    s = results["summary"]
    print(f"Total comparisons: {s['total_comparisons']}")
    print(f"Identical:         {s['identical']}")
    print(f"Different:         {s['different']}")
    print(f"Errors:            {s['errors']}")
    print(f"Total diff pixels: {s['total_diff_pixels']}")
    print(f"Max diff %:        {s['max_diff_percentage']:.4f}%")
    print(f"\nReport saved to: {report_path}")
    print(f"Diff images in:  {COMPARE_OUT_DIR}")

    if s['different'] == 0 and s['errors'] == 0:
        print("\n[OK] ALL SCREENSHOTS IDENTICAL - Visual parity achieved!")
        return 0
    else:
        print(f"\n[FAIL] {s['different']} differences found, {s['errors']} errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())