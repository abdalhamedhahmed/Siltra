#!/usr/bin/env python
"""Test that table_cell_style is properly defined"""
import os
import sys
sys.path.insert(0, r'C:\Users\Abdalhamed Ahmed\Desktop\fac')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Test that module-level styles are importable
from reports import table_cell_style, body_style_base, small_body_style_base
print(f"table_cell_style name: {table_cell_style.name}")
print(f"body_style_base name: {body_style_base.name}")
print(f"small_body_style_base name: {small_body_style_base.name}")
print("SUCCESS: All module-level styles importable")

# Verify TableCell style has correct properties
print(f"\ntable_cell_style fontSize: {table_cell_style.fontSize}")
print(f"table_cell_style leading: {table_cell_style.leading}")
print(f"table_cell_style textColor: {table_cell_style.textColor}")