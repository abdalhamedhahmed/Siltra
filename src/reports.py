"""
PDF and Excel Report Generator for Coil Slitting Optimizer
Shared data builder so PDF and Excel outputs always agree.
"""

from decimal import Decimal, ROUND_HALF_UP
import math
import os
import sys
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Make 'src' importable as a top-level package regardless of CWD,
# since the package now lives at src/ (flat layout).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.graphics import renderPDF

# Import app info for consistent branding
from app_info import APP_NAME, FACTORY_NAME, APP_VERSION

# Core calculation engine (used by build_report_data and cutting-drawing helpers)
import core


# Module-level ParagraphStyles for consistent reuse across PDF export
table_cell_style = ParagraphStyle(
    'TableCell',
    fontSize=8,
    leading=10,
    textColor=HexColor('#1a1a1a'),
)

body_style_base = ParagraphStyle(
    'ReportBodyBase',
    fontSize=9,
    leading=12,
    textColor=HexColor('#1a1a1a'),
)

small_body_style_base = ParagraphStyle(
    'SmallBodyBase',
    parent=body_style_base,
    fontSize=8,
    leading=10,
)


# ============================================================
# SWATCH FLOWABLE - Solid color square for legend tables
# ============================================================
from reportlab.platypus import Flowable
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect

class ColorSwatch(Flowable):
    """A solid color square swatch for table cells. No text, just a filled rectangle."""
    def __init__(self, color_hex, size=4*mm):
        Flowable.__init__(self)
        self.color_hex = color_hex
        self.size = size
        self.width = size
        self.height = size

    def draw(self):
        # Create a drawing with a solid filled rectangle
        d = Drawing(self.size, self.size)
        rect = Rect(0, 0, self.size, self.size, fillColor=HexColor(self.color_hex), strokeColor=None)
        d.add(rect)
        # Render the drawing at (0, 0)
        renderPDF.draw(d, self.canv, 0, 0)


# Report colors (same as app theme)
REPORT_COLORS = {
    # Strip colors by order entered
    'strip_0': '#E69F00',  # Orange
    'strip_1': '#56B4E9',  # Sky Blue
    'strip_2': '#009E73',  # Bluish Green
    'strip_3': '#F0E442',  # Yellow
    'strip_4': '#CC79A7',  # Reddish Purple
    'strip_5': '#0072B2',  # Blue
    'strip_6': '#D55E00',  # Vermilion
    # Scrap
    'scrap': '#E8590C',
    # Neutrals
    'title_band': '#1f2933',
    'section_header': '#e5e7eb',
    'best_row': '#e3f3e8',
    'table_borders': '#d5d9de',
    'zebra_rows': '#f3f4f6',
}


def hex_color(hex_str):
    """Convert hex string to reportlab HexColor."""
    return HexColor(hex_str)


def build_report_data(
    result: Dict[str, Any],
    selected_index: int,
    settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build shared report data from a calculation result and selected combination index.
    Reads ONLY from the calculation result object and saved settings, never from widget text.

    Returns a dict with all data needed by both PDF and Excel exporters, including:
    - selected_combination: the chosen combo with all computed fields
    - true_N: total combinations found (even when capped)
    - coil_params: coil width, number of coils, strip sizes, scrap range
    - weight_verification: Decimal-based difference check
    - strip_data: ordered strip info with quantities, widths, colors
    - knife_positions: cumulative positions for the cutting plan
    - build_id: from settings or generated from timestamp
    """

    if settings is None:
        settings = {}

    # Get the selected combination (by index in the filtered/results list)
    all_combos = result.get('all_combinations', [])
    filtered_combos = result.get('filtered_combinations', [])

    if not all_combos:
        return {'error': 'No combinations available'}

    # Use selected_index if valid, otherwise default to 0 (Best)
    if selected_index is not None and 0 <= selected_index < len(filtered_combos):
        selected = filtered_combos[selected_index]
    else:
        selected = filtered_combos[0] if filtered_combos else all_combos[0]

    # True total N - from result metadata (capped at 1,000,000)
    true_N = result.get('total_combinations', len(all_combos))

    # Coil parameters from the core calculation
    coil_width = selected.get('coil_width', settings.get('coil_width', 1250.0))
    num_coils = selected.get('num_coils', settings.get('num_coils', 1))
    strip_sizes = selected.get('strip_sizes', settings.get('strip_sizes', []))
    min_scrap = selected.get('min_scrap', settings.get('min_scrap', 0.0))
    max_scrap = selected.get('max_scrap', settings.get('max_scrap', 30.0))
    at_least_once = selected.get('at_least_once', settings.get('at_least_once', True))

    # Strip quantities from the selected combination
    qs = selected.get('qs', [])
    total_width = selected.get('total_width', 0.0)
    scrap_mm = selected.get('scrap_mm', 0.0)
    scrap_pct = selected.get('scrap_pct', 0.0)
    total_strips = selected.get('total_strips', 0)

    # Weight verification using Decimal (from core.py verify_weight_balance pattern)
    total_coil_weight = selected.get('total_coil_weight', settings.get('total_coil_weight', 10000.0))
    coil_weights = selected.get('coil_weights', settings.get('coil_weights', []))
    if not coil_weights:
        # Try to get from settings or compute from total
        coil_weights = [total_coil_weight / num_coils] * num_coils

    details = selected.get('details', {})

    if isinstance(details, dict) and details.get('details'):
        detail_list = details['details']
        # Use the full details dict which includes scrap_weight_total
        details_for_verify = details
    else:
        # Recalculate from scratch using core.py logic
        detail_list = core.calculate_combination_details(
            tuple(qs), coil_width, total_coil_weight, num_coils, strip_sizes
        ).get('details', [])
        # Wrap in the structure that _verify_weight_balance expects
        details_for_verify = {'details': detail_list}

    # Compute weight verification using the full details structure
    weight_diff, strips_total_weight, scrap_weight_total = _verify_weight_balance(
        total_coil_weight, num_coils, {'details': details_for_verify}, coil_width, coil_weights
    )

    # Build strip data with colors (order: sizes entered)
    strip_data = []
    for i, (size, qty) in enumerate(zip(strip_sizes, qs)):
        strip_data.append({
            'size': size,
            'qty_per_coil': qty,
            'qty_total': qty * num_coils,
            'color': REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000',
        })

    # Add scrap data if scrap > 0
    if scrap_mm > 0:
        strip_data.append({
            'size': scrap_mm,
            'qty_per_coil': 0,
            'qty_total': 0,
            'color': REPORT_COLORS['scrap'],
            'is_scrap': True,
        })

    # Calculate knife positions (cumulative from left with clearance)
    knife_positions = _calculate_knife_positions(strip_sizes, qs, scrap_mm, CLEARANCE_PER_SIDE)

    # Build ID from settings or timestamp
    build_id = settings.get(
        'build_id',
        f"{os.path.basename(__file__)}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    return {
        'selected_combination': selected,
        'true_N': true_N,
        'coil_params': {
            'coil_width': coil_width,
            'num_coils': num_coils,
            'strip_sizes': strip_sizes,
            'min_scrap': min_scrap,
            'max_scrap': max_scrap,
            'at_least_once': at_least_once,
        },
        'strip_data': strip_data,
        'knife_positions': knife_positions,
        'weight_verification': {
            'total_coil_weight': total_coil_weight,
            'strips_total_weight': float(strips_total_weight),
            'scrap_weight_total': float(scrap_weight_total),
            'difference': float(weight_diff) if weight_diff else 0.0,
            'passes': abs(float(weight_diff)) <= 0.01 if weight_diff is not None else None,
        },
        'build_id': build_id,
        'all_combinations': all_combos,
        'filtered_combinations': filtered_combos,
        'stopped_early': result.get('stopped_early', False),
        # Phase E: Job order fields
        'job_number': selected.get('job_number', ''),
        'order_phase': selected.get('order_phase', 'Initial Job Order'),
        'consignment': selected.get('consignment', ''),
    }

def _verify_weight_balance(
    total_coil_weight: float, num_coils: int,
    details_res: Dict[str, Any], coil_width: float,
    coil_weights: Optional[List[float]] = None
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Verify total weight = strips weight + scrap weight.
    Returns tuple of (difference, strips_total_weight, scrap_weight_total).

    details_res is expected to have structure: {'details': {'details': detail_list, 'scrap_weight_total': ...}}
    """
    try:
        cw_dec = Decimal(str(coil_width))
        tot_weight_dec = Decimal(str(total_coil_weight))
    except (ValueError, TypeError):
        return Decimal('0.0'), Decimal('0.0'), Decimal('0.0')

    if cw_dec == 0:
        return tot_weight_dec, Decimal('0.0'), Decimal('0.0')

    # Extract detail list and scrap_weight_total from the core.py result structure
    detail_list = []
    scrap_weight_total = Decimal('0.0')

    if isinstance(details_res, dict) and 'details' in details_res:
        inner = details_res['details']
        if isinstance(inner, dict):
            # Get the detail list
            if 'details' in inner:
                detail_list = inner['details']
            # Get scrap_weight_total if available
            if 'scrap_weight_total' in inner:
                scrap_weight_total = Decimal(str(inner['scrap_weight_total']))
        elif isinstance(inner, list):
            detail_list = inner

    # If no scrap_weight_total, calculate it using per-coil weights if available
    if scrap_weight_total == 0 and detail_list:
        total_width_used = sum(d['size'] * d['q_per_coil'] for d in detail_list)
        scrap_width = float(cw_dec) - total_width_used
        if scrap_width > 0 and num_coils > 0:
            if coil_weights:
                # Calculate scrap weight using individual coil weights
                scrap_weight_total = Decimal('0.0')
                for cw in coil_weights:
                    weight_per_coil = Decimal(str(cw))
                    scrap_weight_total += weight_per_coil * (Decimal(str(scrap_width)) / cw_dec)
            else:
                # Fallback to average weight
                scrap_weight_per_coil = (tot_weight_dec / Decimal(str(num_coils))) * (Decimal(str(scrap_width)) / cw_dec)
                scrap_weight_total = scrap_weight_per_coil * Decimal(str(num_coils))

    # Sum weight_total from detail list
    strips_total_w = sum(Decimal(str(d['weight_total'])) for d in detail_list)

    used_weight = strips_total_w + scrap_weight_total

    return tot_weight_dec - used_weight, strips_total_w, scrap_weight_total


CLEARANCE_PER_SIDE = 0.150  # mm, hardcoded default (OptiStack spec)


def _calculate_knife_positions(strip_sizes: List[float], qs: List[int], scrap_mm: float = 0.0, clearance: float = CLEARANCE_PER_SIDE) -> List[Dict[str, Any]]:
    """Calculate cumulative knife positions from left edge with clearance."""
    positions = []
    cumulative = 0.0
    knife_num = 1
    for size, qty in zip(strip_sizes, qs):
        for _ in range(qty):
            cumulative += size
            positions.append({
                'knife': knife_num,
                'position': round(cumulative, 3),
                'strip_width': size,
                'clearance': clearance,
                'shim_stack': '0.100 + 0.050',  # Fixed shim stack
            })
            knife_num += 1
            cumulative += clearance * 2  # clearance per side
    # Last position: only add coil edge if scrap > 0, otherwise it's the same as last cut
    if scrap_mm > 0:
        positions.append({
            'knife': knife_num,
            'position': round(cumulative, 3),
            'strip_width': scrap_mm,
            'clearance': 0,
            'shim_stack': '—',
            'action': 'Coil edge (scrap starts here)',
        })
    else:
        # Scrap is 0: the last cut IS the coil edge
        if positions:
            positions[-1]['action'] = 'Coil edge (no scrap)'
    return positions


def get_build_id() -> str:
    """Get the current build ID from settings or generate one."""
    settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'settings.json')
    try:
        import json
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                s = json.load(f)
            return s.get('build_id', get_build_id())
    except (OSError, json.JSONDecodeError):
        pass
    return f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


# ============================================================
# PDF EXPORT (using reportlab)
# ============================================================

def export_pdf(
    report_data: Dict[str, Any],
    filepath: str,
    title: str = None,
    version: str = None
) -> bool:
    """
    Export the job order as a 2-page PDF:
    Page 1: Job Order Sheet for the selected combination
    Page 2: Top Combinations table (up to 25 rows)
    """
    if title is None:
        title = f"{FACTORY_NAME} - Job Order"
    if version is None:
        version = APP_VERSION

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
            PageBreak, KeepTogether, Image, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm, inch
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        from reportlab.graphics.shapes import Drawing, Rect, String, Line
        from reportlab.graphics import renderPDF
    except ImportError:
        print("PDF export requires reportlab library")
        return False

    # Page setup: A4 landscape, 12mm margins
    page_w, page_h = landscape(A4)
    margin = 12 * mm
    content_w = page_w - 2 * margin
    content_h = page_h - 2 * margin

    # Build PDF with metadata
    build_id = report_data['build_id']
    doc = SimpleDocTemplate(
        filepath,
        pagesize=landscape(A4),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title,
        subject=f"Build ID: {build_id}",
    )

    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        spaceAfter=4,
        textColor=colors.white,
        alignment=TA_LEFT,
    )

    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        spaceAfter=2,
        textColor=colors.white,
        alignment=TA_RIGHT,
    )

    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        fontName='Helvetica-Bold',
        textColor=HexColor('#1a1a1a'),
        spaceBefore=8,
        spaceAfter=4,
    )

    body_style = body_style_base
    small_body_style = small_body_style_base
    # table_cell_style is defined at module level

    # --- PAGE 1: Job Order Sheet ---

    # 1. Title band with logo, title, version, date
    # Create a table for the header band
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Title band table (single row, 3 columns: logo | title | version/date)
    title_data = [[
        Paragraph(title, title_style),
        Paragraph(f"Version {version}  |  {now_str}", subtitle_style),
    ]]

    # We'll add logo to the left - for now use text placeholder
    title_table = Table(title_data, colWidths=[content_w * 0.7, content_w * 0.3])
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), hex_color(REPORT_COLORS['title_band'])),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 8))

    # 2. Formula F{rank} of {N} line with BEST badge
    selected = report_data['selected_combination']
    rank = selected.get('rank', 1)
    true_N = report_data['true_N']
    is_best = selected.get('is_best', rank == 1)

    rank_parts = [Paragraph(f"<b>Formula F{rank} of {true_N:,}</b>", body_style)]
    if is_best:
        rank_parts.append(Paragraph(
            '<font color="#1e7a24" size="10"><b>BEST COMBINATION</b></font>',
            body_style
        ))
    else:
        best_combo = next((c for c in report_data.get('all_combinations', []) if c.get('is_best')), None)
        if best_combo:
            rank_parts.append(Paragraph(
                f'<font color="#6b7280" size="10">Best is Formula F1 (scrap {best_combo.get("scrap_mm", 0):.1f} mm)</font>',
                body_style
            ))

    num_coils = report_data['coil_params']['num_coils']
    if num_coils > 1:
        rank_parts.append(Paragraph(
            f'<font color="#6b7280" size="10">Same plan applies to each of the {num_coils} coils</font>',
            body_style
        ))

    rank_table = Table([[rank_parts]], colWidths=[content_w])
    rank_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(rank_table)
    story.append(Spacer(1, 8))

    # 3. Two blocks side by side: Input parameters | Summary
    coil_params = report_data['coil_params']

    # Input Parameters block
    input_data = []
    input_data.append([Paragraph("<b>Input Parameters</b>", section_header_style), ""])

    # Coil info
    input_data.append([Paragraph(f"Number of coils:", body_style), Paragraph(str(num_coils), body_style)])
    input_data.append([Paragraph(f"Coil width (mm):", body_style), Paragraph(f"{coil_params['coil_width']:.0f}", body_style)])

    # Scrap range
    input_data.append([Paragraph(f"Scrap range (mm):", body_style), Paragraph(f"{coil_params['min_scrap']:.0f} to {coil_params['max_scrap']:.0f}", body_style)])
    input_data.append([Paragraph(f"Every size at least once:", body_style), Paragraph("Yes" if coil_params['at_least_once'] else "No", body_style)])

    # Strip sizes moved to separate full-width row below (see strip_sizes_data below)
    strip_sizes = coil_params['strip_sizes']

    # Coil weights
    coil_weights = selected.get('coil_weights', [])
    if not coil_weights:
        # Try to get from settings or compute from total
        total_weight = selected.get('total_coil_weight', 10000.0)
        coil_weights = [total_weight / num_coils] * num_coils

    if num_coils <= 12:
        for i, w in enumerate(coil_weights):
            input_data.append([Paragraph(f"Coil {i+1} weight (kg):", body_style), Paragraph(f"{w:.2f}", body_style)])
    else:
        for i in range(12):
            input_data.append([Paragraph(f"Coil {i+1} weight (kg):", body_style), Paragraph(f"{coil_weights[i]:.2f}", body_style)])
        input_data.append([Paragraph(f"+ {num_coils - 12} more coils", body_style), ""])

    input_table = Table(input_data, colWidths=[content_w * 0.45, content_w * 0.25])
    input_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, hex_color(REPORT_COLORS['table_borders'])),
        ('BACKGROUND', (0, 0), (1, 0), hex_color(REPORT_COLORS['section_header'])),
        ('SPAN', (0, 0), (1, 0)),
    ]))

    # Summary block
    total_width = selected.get('total_width', 0.0)
    scrap_mm = selected.get('scrap_mm', 0.0)
    scrap_pct = selected.get('scrap_pct', 0.0)
    total_strips = selected.get('total_strips', 0)
    total_weight = selected.get('total_coil_weight', 10000.0)

    avg_weight_per_coil = total_weight / num_coils if num_coils > 0 else 0
    scrap_weight_per_coil = avg_weight_per_coil * (scrap_mm / coil_params['coil_width']) if coil_params['coil_width'] > 0 else 0
    scrap_weight_total = scrap_weight_per_coil * num_coils

    summary_data = []
    summary_data.append([Paragraph("<b>Summary</b>", section_header_style), ""])
    summary_data.append([Paragraph("Used width (mm):", body_style), Paragraph(f"{total_width:.0f}", body_style)])
    summary_data.append([Paragraph("Scrap width (mm):", body_style), Paragraph(f"{scrap_mm:.0f}", body_style)])
    summary_data.append([Paragraph("Scrap (%):", body_style), Paragraph(f"{scrap_pct:.2f}%", body_style)])
    summary_data.append([Paragraph("Strips per coil:", body_style), Paragraph(str(total_strips), body_style)])

    if num_coils > 1:
        summary_data.append([Paragraph("Total strips (all coils):", body_style), Paragraph(str(total_strips * num_coils), body_style)])
        summary_data.append([Paragraph("Avg weight/coil (kg):", body_style), Paragraph(f"{avg_weight_per_coil:.2f}", body_style)])

    summary_data.append([Paragraph("Scrap weight/coil (kg):", body_style), Paragraph(f"{scrap_weight_per_coil:.2f}", body_style)])
    summary_data.append([Paragraph("Scrap weight total (kg):", body_style), Paragraph(f"{scrap_weight_total:.2f}", body_style)])
    summary_data.append([Paragraph("Total weight (kg):", body_style), Paragraph(f"{total_weight:.2f}", body_style)])

    summary_table = Table(summary_data, colWidths=[content_w * 0.45, content_w * 0.25])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, hex_color(REPORT_COLORS['table_borders'])),
        ('BACKGROUND', (0, 0), (1, 0), hex_color(REPORT_COLORS['section_header'])),
        ('SPAN', (0, 0), (1, 0)),
    ]))

    # Combine side by side with 8mm gutter
    gutter = 8 * mm
    combined_table = Table([[input_table, summary_table]], colWidths=[content_w * 0.5 - gutter/2, content_w * 0.5 - gutter/2])
    combined_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), gutter),
        ('LEFTPADDING', (1, 0), (1, 0), gutter),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    story.append(combined_table)
    story.append(Spacer(1, 6))

    # Strip sizes row - full width with wrapping chips
    strip_sizes = coil_params['strip_sizes']
    if strip_sizes:
        chips = []
        for i, size in enumerate(strip_sizes):
            color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
            chips.append(f'<font backColor="{color}" color="#FFFFFF" size="9"><b> {int(size)} mm </b></font>')

        # Create wrapping row - chips with 3mm gaps
        chip_text = "   ".join(chips)  # 3mm gap between chips
        strip_sizes_data = [[
            Paragraph("<b>Strip sizes:</b>", body_style),
            Paragraph(chip_text, body_style)
        ]]
        strip_sizes_table = Table(strip_sizes_data, colWidths=[content_w * 0.15, content_w * 0.85])
        strip_sizes_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(strip_sizes_table)
        story.append(Spacer(1, 6))

    # 4. Cutting plan drawing - to-scale drawing (16mm height max)
    drawing = _create_cutting_drawing(
        report_data, content_w, 16 * mm
    )
    story.append(drawing)
    story.append(Spacer(1, 6))

    # Ruler with knife positions
    ruler_data = _create_ruler_table(report_data, content_w)
    story.append(ruler_data)
    story.append(Spacer(1, 6))

    # 5. Strip legend table
    legend_table = _create_strip_legend_table(report_data, content_w)
    story.append(legend_table)
    story.append(Spacer(1, 6))

    # 6. Knife setup table
    knife_table = _create_knife_table(report_data, content_w)
    story.append(knife_table)
    story.append(Spacer(1, 6))

    # 7. Weight verification line
    wv = report_data['weight_verification']
    diff = wv.get('difference', 0)
    passes = wv.get('passes', False)
    strips_total = wv.get('strips_total_weight', 0)
    scrap_total = wv.get('scrap_weight_total', 0)
    total_w = wv.get('total_coil_weight', 0)

    # Use the actual printed numbers for verification
    printed_total = strips_total + scrap_total
    diff_display = printed_total - total_w
    passes_display = abs(diff_display) <= 0.01

    wv_color = "#1e7a24" if passes_display else "#dc2626"
    wv_text = "PASS" if passes_display else "FAIL"
    if not passes_display:
        wv_text += f" (printed: {printed_total:.2f} + {scrap_total:.2f} = {printed_total + scrap_total:.2f}, expected: {total_w:.2f})"
    wv_line = Paragraph(
        f'<b>Weight verification: Sum(Total weight column) + Scrap weight total = {printed_total:.2f} + {scrap_total:.2f} = {printed_total + scrap_total:.2f} kg vs Total coils weight {total_w:.2f} kg → Difference = {diff_display:.2f} kg - <font color="{wv_color}">{wv_text}</font></b>',
        body_style
    )
    story.append(wv_line)
    story.append(Spacer(1, 10))

    # 8. Hand-writing line
    handwrite = Paragraph(
        'Job / order no: ____________  Prepared by: ____________  Operator: ____________  Date: ____________',
        ParagraphStyle('Handwrite', parent=body_style, fontSize=9, leading=14, spaceBefore=4)
    )
    story.append(handwrite)
    story.append(Spacer(1, 10))

    # 9. Footer - only "Developed by Abdalhamed | Coil Slitting Optimizer v3.7.1"
    # Build ID goes in PDF metadata (Subject) instead
    footer_text = f"Developed by Abdalhamed | Coil Slitting Optimizer v{version}"

    # Two-pass page numbering: first pass to count pages, second pass to render with total
    def build_pdf_with_page_numbers():
        # We need to build the story twice because reportlab consumes flowables during build.
        # Define a function to build the complete story.
        def build_complete_story():
            story_local = []

            # --- PAGE 1: Job Order Sheet ---
            # 1. Title band with logo, title, version, date
            title_data = [[
                Paragraph(title, title_style),
                Paragraph(f"Version {version}  |  {now_str}", subtitle_style),
            ]]
            title_table = Table(title_data, colWidths=[content_w * 0.7, content_w * 0.3])
            title_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), hex_color(REPORT_COLORS['title_band'])),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story_local.append(title_table)
            story_local.append(Spacer(1, 8))

            # 2. Formula F{rank} of {N} line with BEST badge
            selected = report_data['selected_combination']
            rank = selected.get('rank', 1)
            true_N = report_data['true_N']
            is_best = selected.get('is_best', rank == 1)

            rank_text = f"Formula F{rank} of {true_N:,}"
            if is_best:
                rank_text += "  -  <b><font color='#1e7a24'>BEST</font></b>"

            rank_para = Paragraph(rank_text, ParagraphStyle('RankLine', parent=body_style, fontSize=11, leading=14, spaceAfter=4, alignment=TA_CENTER))
            story_local.append(rank_para)
            story_local.append(Spacer(1, 4))

            # 3. Input parameters + Summary side by side
            coil_params = report_data['coil_params']
            num_coils = coil_params['num_coils']

            # Get material-weight calculation fields from selected combination
            material_type = selected.get('material_type', 'HR')
            thickness = selected.get('thickness', 0.5)
            theoretical_length = selected.get('theoretical_length_m', 0.0)
            consignment = selected.get('consignment', '')

            input_data = []
            input_data.append([Paragraph("<b>Input Parameters</b>", section_header_style), ""])
            input_data.append([Paragraph("Consignment:", body_style), Paragraph(consignment, body_style)])
            input_data.append([Paragraph("Material type:", body_style), Paragraph(material_type, body_style)])
            input_data.append([Paragraph("Thickness (mm):", body_style), Paragraph(f"{thickness:.3f}", body_style)])
            input_data.append([Paragraph("Theoretical length (m):", body_style), Paragraph(f"{theoretical_length:.1f}", body_style)])
            input_data.append([Paragraph("Number of coils:", body_style), Paragraph(str(num_coils), body_style)])
            input_data.append([Paragraph("Coil width (mm):", body_style), Paragraph(f"{coil_params['coil_width']:.0f}", body_style)])
            input_data.append([Paragraph("Scrap range (mm):", body_style), Paragraph(f"{coil_params['min_scrap']:.0f} to {coil_params['max_scrap']:.0f}", body_style)])
            input_data.append([Paragraph("Every size at least once:", body_style), Paragraph("Yes" if coil_params['at_least_once'] else "No", body_style)])

            coil_weights = selected.get('coil_weights', [])
            if not coil_weights:
                total_weight = selected.get('total_coil_weight', 10000.0)
                coil_weights = [total_weight / num_coils] * num_coils

            if num_coils <= 12:
                for i, w in enumerate(coil_weights):
                    input_data.append([Paragraph(f"Coil {i+1} weight (kg):", body_style), Paragraph(f"{w:.2f}", body_style)])
            else:
                for i in range(12):
                    input_data.append([Paragraph(f"Coil {i+1} weight (kg):", body_style), Paragraph(f"{coil_weights[i]:.2f}", body_style)])
                input_data.append([Paragraph(f"+ {num_coils - 12} more coils", body_style), Paragraph("", body_style)])

            input_table = Table(input_data, colWidths=[content_w * 0.35, content_w * 0.15])
            input_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, hex_color(REPORT_COLORS['table_borders'])),
                ('BACKGROUND', (0, 0), (1, 0), hex_color(REPORT_COLORS['section_header'])),
                ('SPAN', (0, 0), (1, 0)),
            ]))

            # Summary block
            total_width = selected.get('total_width', 0.0)
            scrap_mm = selected.get('scrap_mm', 0.0)
            scrap_pct = selected.get('scrap_pct', 0.0)
            total_strips = selected.get('total_strips', 0)
            total_weight = selected.get('total_coil_weight', 10000.0)

            avg_weight_per_coil = total_weight / num_coils if num_coils > 0 else 0
            scrap_weight_per_coil = avg_weight_per_coil * (scrap_mm / coil_params['coil_width']) if coil_params['coil_width'] > 0 else 0
            scrap_weight_total = scrap_weight_per_coil * num_coils

            summary_data = []
            summary_data.append([Paragraph("<b>Summary</b>", section_header_style), ""])
            summary_data.append([Paragraph("Used width (mm):", body_style), Paragraph(f"{total_width:.0f}", body_style)])
            summary_data.append([Paragraph("Scrap width (mm):", body_style), Paragraph(f"{scrap_mm:.0f}", body_style)])
            summary_data.append([Paragraph("Scrap (%):", body_style), Paragraph(f"{scrap_pct:.2f}%", body_style)])
            summary_data.append([Paragraph("Strips per coil:", body_style), Paragraph(str(total_strips), body_style)])

            if num_coils > 1:
                summary_data.append([Paragraph("Total strips (all coils):", body_style), Paragraph(str(total_strips * num_coils), body_style)])
                summary_data.append([Paragraph("Avg weight/coil (kg):", body_style), Paragraph(f"{avg_weight_per_coil:.2f}", body_style)])

            summary_data.append([Paragraph("Scrap weight/coil (kg):", body_style), Paragraph(f"{scrap_weight_per_coil:.2f}", body_style)])
            summary_data.append([Paragraph("Scrap weight total (kg):", body_style), Paragraph(f"{scrap_weight_total:.2f}", body_style)])
            summary_data.append([Paragraph("Total weight (kg):", body_style), Paragraph(f"{total_weight:.2f}", body_style)])

            summary_table = Table(summary_data, colWidths=[content_w * 0.45, content_w * 0.25])
            summary_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, hex_color(REPORT_COLORS['table_borders'])),
                ('BACKGROUND', (0, 0), (1, 0), hex_color(REPORT_COLORS['section_header'])),
                ('SPAN', (0, 0), (1, 0)),
            ]))

            # Combine side by side with 8mm gutter
            gutter = 8 * mm
            combined_table = Table([[input_table, summary_table]], colWidths=[content_w * 0.5 - gutter/2, content_w * 0.5 - gutter/2])
            combined_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (0, 0), (0, 0), gutter),
                ('LEFTPADDING', (1, 0), (1, 0), gutter),
                ('RIGHTPADDING', (1, 0), (1, 0), 0),
            ]))
            story_local.append(combined_table)
            story_local.append(Spacer(1, 6))

            # Strip sizes row - full width with wrapping chips
            strip_sizes = coil_params['strip_sizes']
            if strip_sizes:
                chips = []
                for i, size in enumerate(strip_sizes):
                    color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
                    chips.append(f'<font backColor="{color}" color="#FFFFFF" size="9"><b> {int(size)} mm </b></font>')

                chip_text = "   ".join(chips)
                strip_sizes_data = [[
                    Paragraph("<b>Strip sizes:</b>", body_style),
                    Paragraph(chip_text, body_style)
                ]]
                strip_sizes_table = Table(strip_sizes_data, colWidths=[content_w * 0.15, content_w * 0.85])
                strip_sizes_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                story_local.append(strip_sizes_table)
                story_local.append(Spacer(1, 6))

            # 4. Cutting plan drawing - to-scale drawing (16mm height max)
            drawing = _create_cutting_drawing(
                report_data, content_w, 16 * mm
            )
            story_local.append(drawing)
            story_local.append(Spacer(1, 6))

            # Ruler with knife positions
            ruler_data = _create_ruler_table(report_data, content_w)
            story_local.append(ruler_data)
            story_local.append(Spacer(1, 6))

            # 5. Strip legend table
            legend_table = _create_strip_legend_table(report_data, content_w)
            story_local.append(legend_table)
            story_local.append(Spacer(1, 6))

            # 6. Knife setup table
            knife_table = _create_knife_table(report_data, content_w)
            story_local.append(knife_table)
            story_local.append(Spacer(1, 6))

            # 7. Weight verification line
            wv = report_data['weight_verification']
            diff = wv.get('difference', 0)
            passes = wv.get('passes', False)
            strips_total = wv.get('strips_total_weight', 0)
            scrap_total = wv.get('scrap_weight_total', 0)
            total_w = wv.get('total_coil_weight', 0)

            printed_total = strips_total + scrap_total
            diff_display = printed_total - total_w
            passes_display = abs(diff_display) <= 0.01

            wv_color = "#1e7a24" if passes_display else "#dc2626"
            wv_text = "PASS" if passes_display else "FAIL"
            if not passes_display:
                wv_text += f" (printed: {printed_total:.2f} + {scrap_total:.2f} = {printed_total + scrap_total:.2f}, expected: {total_w:.2f})"
            wv_line = Paragraph(
                f'<b>Weight verification: Sum(Total weight column) + Scrap weight total = {printed_total:.2f} + {scrap_total:.2f} = {printed_total + scrap_total:.2f} kg vs Total coils weight {total_w:.2f} kg → Difference = {diff_display:.2f} kg - <font color="{wv_color}">{wv_text}</font></b>',
                body_style
            )
            story_local.append(wv_line)
            story_local.append(Spacer(1, 10))

            # 8. Hand-writing line
            handwrite = Paragraph(
                'Job / order no: ____________  Prepared by: ____________  Operator: ____________  Date: ____________',
                ParagraphStyle('Handwrite', parent=body_style, fontSize=9, leading=14, spaceBefore=4)
            )
            story_local.append(handwrite)
            story_local.append(Spacer(1, 10))

            # Page 1 done - add page break
            story_local.append(PageBreak())

            # --- PAGE 2: Top Combinations ---
            title2_data = [[
                Paragraph(f"{FACTORY_NAME} - Top Combinations", title_style),
                Paragraph(f"Version {version}  |  {now_str}", subtitle_style),
            ]]
            title2_table = Table(title2_data, colWidths=[content_w * 0.7, content_w * 0.3])
            title2_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), hex_color(REPORT_COLORS['title_band'])),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story_local.append(title2_table)
            story_local.append(Spacer(1, 8))

            # Get top combinations
            combos = report_data.get('all_combinations', [])
            if not combos:
                combos = report_data.get('filtered_combinations', [])

            combos = sorted(combos, key=lambda x: (x.get('scrap_mm', 9999), x.get('total_strips', 9999)))

            TOP_N_PDF = 25
            top_combos = combos[:TOP_N_PDF]
            is_capped = len(combos) > TOP_N_PDF or report_data.get('stopped_early', False)

            num_sizes = len(strip_sizes)

            col_rank = 40
            col_qty = 50 * num_sizes
            col_width = 60
            col_scrap_mm = 50
            col_scrap_pct = 50
            col_strips = 50
            col_mix = 140

            remaining = content_w - col_rank - col_qty - col_width - col_scrap_mm - col_scrap_pct - col_strips - col_mix
            if remaining > 0:
                col_qty += remaining * 0.5
                col_mix += remaining * 0.5

            headers = [Paragraph("<b>Rank</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER))]
            for i, size in enumerate(strip_sizes):
                color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
                headers.append(Paragraph(
                    f'<b><font color="{color}">{int(size)}mm</font></b>',
                    ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)
                ))
            headers.extend([
                Paragraph("<b>Width<br/>(mm)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph("<b>Scrap<br/>(mm)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph("<b>Scrap<br/>(%)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph("<b>Strips</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph("<b>Mix to scale</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
            ])

            combos_table_data = [headers]

            for idx, combo in enumerate(top_combos):
                is_best = combo.get('is_best', False)
                is_selected = combo == selected
                row_rank = combo.get('rank', idx + 1)

                row = []
                rank_text = str(row_rank)
                if is_best:
                    rank_text += " Best"
                if is_selected and not is_best:
                    rank_text += " Selected"

                row.append(Paragraph(rank_text, ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))

                qs = combo.get('qs', [])
                for j, qty in enumerate(qs):
                    row.append(Paragraph(str(qty), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))

                row.append(Paragraph(f"{combo.get('total_width', 0):.0f}", ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(f"{combo.get('scrap_mm', 0):.0f}", ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(f"{combo.get('scrap_pct', 0):.2f}", ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(str(combo.get('total_strips', 0)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))

                mix_drawing = _create_mix_bar(combo, strip_sizes, col_mix)
                row.append(mix_drawing)

                combos_table_data.append(row)

            if selected not in top_combos:
                sep_row = [Paragraph("...", ParagraphStyle('s', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)) for _ in headers]
                combos_table_data.append(sep_row)

                is_best = selected.get('is_best', False)
                row_rank = selected.get('rank', len(combos))
                row = []
                rank_text = "F%d" % row_rank
                if is_best:
                    rank_text += " Best"
                rank_text += " Selected"
                row.append(Paragraph(rank_text, ParagraphStyle('r', parent=body_style, fontSize=7, alignment=TA_CENTER, fontName='Helvetica-Bold')))

                qs = selected.get('qs', [])
                for j, qty in enumerate(qs):
                    row.append(Paragraph(str(qty), ParagraphStyle('r', parent=body_style, fontSize=7, alignment=TA_CENTER)))

                row.append(Paragraph(f"{selected.get('total_width', 0):.0f}", ParagraphStyle('r', parent=body_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(f"{selected.get('scrap_mm', 0):.0f}", ParagraphStyle('r', parent=body_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(f"{selected.get('scrap_pct', 0):.2f}", ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))
                row.append(Paragraph(str(selected.get('total_strips', 0)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)))
                row.append(_create_mix_bar(selected, strip_sizes, col_mix))

                combos_table_data.append(row)

            from reportlab.platypus import KeepTogether
            combos_table = Table(combos_table_data, colWidths=[
                col_rank, *( [col_qty // max(1, num_sizes)] * num_sizes ),
                col_width, col_scrap_mm, col_scrap_pct, col_strips, col_mix
            ])

            table_style_cmds = [
                ('BACKGROUND', (0, 0), (-1, 0), hex_color(REPORT_COLORS['section_header'])),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('GRID', (0, 0), (-1, -1), 0.5, hex_color(REPORT_COLORS['table_borders'])),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, hex_color(REPORT_COLORS['zebra_rows'])]),
            ]

            if len(top_combos) > 0:
                table_style_cmds.append(('BACKGROUND', (0, 1), (-1, 1), hex_color(REPORT_COLORS['best_row'])))

            combos_table.setStyle(TableStyle(table_style_cmds))
            story_local.append(combos_table)
            story_local.append(Spacer(1, 8))

            if is_capped:
                info_text = f"Showing top {TOP_N_PDF} of {true_N:,} combinations. The full list is in the Excel file."
                story_local.append(Paragraph(info_text, ParagraphStyle('info', parent=body_style, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))
            else:
                story_local.append(Paragraph(f"Showing all {len(combos):,} combinations", ParagraphStyle('info', parent=body_style, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

            return story_local

        # First pass: build to a temporary buffer with a counter to get total page count
        from io import BytesIO
        temp_buffer = BytesIO()
        temp_doc = SimpleDocTemplate(
            temp_buffer,
            pagesize=landscape(A4),
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
        )

        # Build story for first pass
        story_for_counting = build_complete_story()

        # Use a mutable container for total pages
        page_info = {'total': 0}

        def counting_callback(canvas, doc):
            page_info['total'] = max(page_info['total'], doc.page)

        # First build just to count pages
        temp_doc.build(story_for_counting, onFirstPage=counting_callback, onLaterPages=counting_callback)
        total_pages = page_info['total']

        # Second pass: build actual PDF with correct total
        def add_page_number(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 7.5)
            canvas.setFillColor(HexColor('#666666'))
            canvas.drawCentredString(page_w / 2, margin / 2, footer_text)
            canvas.drawRightString(page_w - margin, margin / 2, f"Page {doc.page} of {total_pages}")
            canvas.restoreState()

        # Build story again for actual PDF (story is consumed by first build)
        story_for_pdf = build_complete_story()
        doc.build(story_for_pdf, onFirstPage=add_page_number, onLaterPages=add_page_number)

    # Build PDF using two-pass page numbering
    build_pdf_with_page_numbers()
    return True


def _create_cutting_drawing(report_data: Dict[str, Any], width: float, height: float):
    """Create a to-scale cutting plan drawing."""
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    selected = report_data['selected_combination']
    strip_sizes = report_data['coil_params']['strip_sizes']
    qs = selected.get('qs', [])
    scrap_mm = selected.get('scrap_mm', 0)
    coil_width = report_data['coil_params']['coil_width']

    drawing = Drawing(width, height)

    # Calculate scale
    total_used = sum(s * q for s, q in zip(strip_sizes, qs)) + scrap_mm
    scale = width / coil_width if coil_width > 0 else 1

    x = 0
    for i, (size, qty) in enumerate(zip(strip_sizes, qs)):
        color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
        for _ in range(qty):
            w_px = size * scale
            rect = Rect(x, 0, w_px, height, fillColor=hex_color(color), strokeColor=None)
            drawing.add(rect)

            # Add label if wide enough
            if w_px > 12:
                text = String(x + w_px/2, height/2, str(int(size)), fontSize=7, textAnchor='middle', fillColor=colors.black)
                drawing.add(text)

            x += w_px

    # Scrap block
    if scrap_mm > 0:
        w_px = scrap_mm * scale
        if w_px < 3:
            w_px = 3  # Minimum 3pt
        rect = Rect(x, 0, w_px, height, fillColor=hex_color(REPORT_COLORS['scrap']), strokeColor=colors.black, strokeWidth=0.5)
        drawing.add(rect)

        if w_px > 12:
            text = String(x + w_px/2, height/2, f"Scrap {int(scrap_mm)}mm", fontSize=7, textAnchor='middle', fillColor=colors.white)
            drawing.add(text)

    return drawing


def _create_ruler_table(report_data: Dict[str, Any], width: float):
    """Create ruler with knife positions using Drawing for true position alignment."""
    from reportlab.graphics.shapes import Drawing, Line, String
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth

    knife_positions = report_data['knife_positions']
    coil_width = report_data['coil_params']['coil_width']
    strip_sizes = report_data['coil_params']['strip_sizes']
    qs = report_data['selected_combination'].get('qs', [])
    scrap_mm = report_data['selected_combination'].get('scrap_mm', 0)

    # Calculate scale
    scale = width / coil_width if coil_width > 0 else 1

    # Drawing height
    height = 14 * mm
    drawing = Drawing(width, height)

    # Base line
    base_y = height / 2
    drawing.add(Line(0, base_y, width, base_y, strokeColor=colors.black, strokeWidth=1))

    # Collect all tick positions and labels first (for collision detection)
    ticks = []  # list of (x, label_text, font_size, is_scrap_label, priority)

    # Left edge (0) - highest priority, never dropped
    ticks.append((0, "0", 6, False, 100))

    # Draw ticks at TRUE positions (aligned with bar blocks)
    # Start from left edge (0)
    cumulative = 0
    for i, (size, qty) in enumerate(zip(strip_sizes, qs)):
        for _ in range(qty):
            cumulative += size
            x = cumulative * scale
            ticks.append((x, str(int(cumulative)), 6, False, 50))

    # Scrap boundary tick (if scrap > 0)
    if scrap_mm > 0:
        x = cumulative * scale
        ticks.append((x, f"Scrap {int(scrap_mm)}mm", 5, True, 30))

    # Right edge (coil edge) - highest priority, never dropped
    right_x = coil_width * scale
    ticks.append((right_x, str(int(coil_width)), 6, False, 100))

    # Collision detection: sort by x position, remove overlapping labels
    # Keep minimum 1.5mm gap between labels
    min_gap_mm = 1.5 * mm
    font_name = 'Helvetica'

    # Sort by x position
    ticks.sort(key=lambda t: t[0])

    # Filter out overlapping labels (keep higher priority)
    kept_ticks = []
    for tick in ticks:
        x, label, font_size, is_scrap, priority = tick
        # Estimate label width
        label_width = stringWidth(label, font_name, font_size)
        half_width = label_width / 2

        # Check collision with already kept ticks
        collision = False
        for kept in kept_ticks:
            kept_x, kept_label, kept_font_size, kept_is_scrap, kept_priority = kept
            kept_label_width = stringWidth(kept_label, font_name, kept_font_size)
            kept_half_width = kept_label_width / 2

            # Check if labels would overlap
            if abs(x - kept_x) < (half_width + kept_half_width + min_gap_mm):
                collision = True
                # Keep the higher priority one
                if priority <= kept_priority:
                    # Current tick has lower/equal priority, skip it
                    break
                else:
                    # Current tick has higher priority, remove the kept one
                    kept_ticks.remove(kept)
                    # Continue checking against other kept ticks
        else:
            # No collision or we won the collision
            kept_ticks.append(tick)

    # Draw kept ticks
    for tick in kept_ticks:
        x, label, font_size, is_scrap, priority = tick
        drawing.add(Line(x, base_y - 4, x, base_y + 4, strokeColor=colors.black, strokeWidth=1))
        text_color = colors.red if is_scrap else colors.black
        text_anchor = 'start' if x == 0 else ('end' if x == right_x else 'middle')
        text = String(x, base_y + 6, label, fontSize=font_size, textAnchor=text_anchor, fillColor=text_color)
        drawing.add(text)

    # Add "mm" unit once at far right (just beyond the last tick)
    # Place it at the right edge of the drawing with small offset
    mm_label_x = width - 2 * mm
    mm_text = String(mm_label_x, base_y + 6, "mm", fontSize=5, textAnchor='end', fillColor=colors.black)
    drawing.add(mm_text)

    return drawing


def _create_strip_legend_table(report_data: Dict[str, Any], width: float):
    """Create strip legend table."""
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER

    strip_data = report_data['strip_data']
    num_coils = report_data['coil_params']['num_coils']

    # table_cell_style is defined at module level

    headers = [Paragraph("<b>Color</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Size (mm)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Qty/coil</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Total qty</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Width used (mm)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Weight/strip (kg)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
               Paragraph("<b>Total weight (kg)</b>", ParagraphStyle('h', parent=table_cell_style, fontSize=8, alignment=TA_CENTER))]

    data = [headers]

    total_width = 0
    total_weight = 0
    total_qty = 0

    for strip in strip_data:
        is_scrap = strip.get('is_scrap', False)
        size = strip['size']
        qty = strip['qty_per_coil']
        color = strip['color']

        width_used = size * qty
        total_width += width_used

        # Get weight from details
        weight_one = 0
        weight_total = 0
        selected = report_data['selected_combination']
        details = selected.get('details', {})
        if isinstance(details, dict) and details.get('details'):
            for d in details['details']:
                if d['size'] == size and not is_scrap:
                    weight_one = d['weight_one']
                    weight_total = d['weight_total']
                    break

        total_weight += weight_total
        total_qty += qty * num_coils

        color_cell = ColorSwatch(color, 4*mm)

        row = [
            color_cell,
            Paragraph(str(int(size)) if not is_scrap else f"Scrap {int(size)}", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
            Paragraph(str(qty) if not is_scrap else "—", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
            Paragraph(str(qty * num_coils) if not is_scrap else "—", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
            Paragraph(f"{width_used:.0f}" if not is_scrap else f"{size:.0f}", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
            Paragraph(f"{weight_one:.2f}" if not is_scrap else "—", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
            Paragraph(f"{weight_total:.2f}" if not is_scrap else "—", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        ]
        data.append(row)

    # Total row
    total_row = [
        Paragraph("", ParagraphStyle('r', parent=table_cell_style, fontSize=8)),
        Paragraph("<b>TOTAL</b>", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        Paragraph("", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        Paragraph(f"<b>{total_qty}</b>", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        Paragraph(f"<b>{total_width:.0f}</b>", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        Paragraph("", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
        Paragraph(f"<b>{total_weight:.2f}</b>", ParagraphStyle('r', parent=table_cell_style, fontSize=8, alignment=TA_CENTER)),
    ]
    data.append(total_row)

    # Add scrap row if exists
    scrap_strips = [s for s in strip_data if s.get('is_scrap')]
    if scrap_strips:
        scrap = scrap_strips[0]
        scrap_weight_per_coil = (scrap['size'] / report_data['coil_params']['coil_width']) * (selected.get('total_coil_weight', 10000) / num_coils) if num_coils > 0 else 0
        scrap_weight_total = scrap_weight_per_coil * num_coils

        scrap_row = [
            ColorSwatch(scrap['color'], 4*mm),
            Paragraph(f"<b>Scrap {int(scrap['size'])}</b>", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            Paragraph("—", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            Paragraph("—", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            Paragraph(f"<b>{int(scrap['size'])}</b>", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            Paragraph(f"<b>{scrap_weight_per_coil:.2f}</b>", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            Paragraph(f"<b>{scrap_weight_total:.2f}</b>", ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
        ]
        data.insert(-1, scrap_row)  # Before total

    legend_table = Table(data, colWidths=[width*0.08, width*0.12, width*0.12, width*0.12, width*0.18, width*0.19, width*0.19])
    legend_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), hex_color(REPORT_COLORS['section_header'])),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, hex_color(REPORT_COLORS['table_borders'])),
        ('ROWBACKGROUNDS', (0, 1), (-2, -1), [colors.white, hex_color(REPORT_COLORS['zebra_rows'])]),
        ('BACKGROUND', (0, -1), (-1, -1), hex_color(REPORT_COLORS['section_header'])),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    return legend_table


def _create_knife_table(report_data: Dict[str, Any], width: float):
    """Create knife setup table with 0.150mm clearance per side."""
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    knife_positions = report_data['knife_positions']
    coil_width = report_data['coil_params']['coil_width']

    # If many knives, use two columns
    use_two_cols = len(knife_positions) > 15

    # New headers with clearance and shim stack columns
    headers = [
        Paragraph("<b>Knife #</b>", ParagraphStyle('h', fontSize=7, alignment=TA_CENTER)),
        Paragraph("<b>Position (mm)</b>", ParagraphStyle('h', fontSize=7, alignment=TA_CENTER)),
        Paragraph("<b>Strip Width (mm)</b>", ParagraphStyle('h', fontSize=7, alignment=TA_CENTER)),
        Paragraph("<b>Clearance (mm)</b>", ParagraphStyle('h', fontSize=7, alignment=TA_CENTER)),
        Paragraph("<b>Shim Stack</b>", ParagraphStyle('h', fontSize=7, alignment=TA_CENTER)),
    ]

    if use_two_cols:
        # Split into two groups
        mid = len(knife_positions) // 2 + 1
        group1 = knife_positions[:mid]
        group2 = knife_positions[mid:]

        data1 = [headers]
        for i, kp in enumerate(group1):
            data1.append([
                Paragraph(str(kp.get('knife', i+1)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('position', 0)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('strip_width', 0)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('clearance', 0.150)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('shim_stack', '0.100 + 0.050')), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            ])

        data2 = [headers]
        for i, kp in enumerate(group2):
            data2.append([
                Paragraph(str(kp.get('knife', mid + i + 1)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('position', 0)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('strip_width', 0)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('clearance', 0.150)), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('shim_stack', '0.100 + 0.050')), ParagraphStyle('r', fontSize=7, alignment=TA_CENTER)),
            ])

        t1 = Table(data1, colWidths=[width*0.1, width*0.15, width*0.15, width*0.15, width*0.15])
        t2 = Table(data2, colWidths=[width*0.1, width*0.15, width*0.15, width*0.15, width*0.15])

        for t in [t1, t2]:
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), hex_color(REPORT_COLORS['section_header'])),
                ('GRID', (0, 0), (-1, -1), 0.5, hex_color(REPORT_COLORS['table_borders'])),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))

        # Note row
        note = Paragraph(f"<b>Coil edge: {int(coil_width)} mm | Clearance: 0.150 mm per side (OptiStack)</b>", ParagraphStyle('n', parent=table_cell_style, fontSize=7, alignment=TA_LEFT))

        combined = Table([[t1, t2], [note, ""]], colWidths=[width/2, width/2])
        combined.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('SPAN', (0, 1), (1, 1)),
        ]))
        return combined
    else:
        data = [headers]
        for i, kp in enumerate(knife_positions):
            data.append([
                Paragraph(str(kp.get('knife', i+1)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('position', 0)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('strip_width', 0)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('clearance', 0.150)), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
                Paragraph(str(kp.get('shim_stack', '0.100 + 0.050')), ParagraphStyle('r', parent=table_cell_style, fontSize=7, alignment=TA_CENTER)),
            ])

        t = Table(data, colWidths=[width*0.1, width*0.15, width*0.15, width*0.15, width*0.15])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), hex_color(REPORT_COLORS['section_header'])),
            ('GRID', (0, 0), (-1, -1), 0.5, hex_color(REPORT_COLORS['table_borders'])),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        note = Paragraph(f"<b>Coil edge: {int(coil_width)} mm</b>", ParagraphStyle('n', parent=table_cell_style, fontSize=8, alignment=TA_LEFT))
        combined = Table([[t], [note]], colWidths=[width])
        combined.setStyle(TableStyle([
            ('SPAN', (0, 1), (0, 1)),
            ('TOPPADDING', (0, 1), (0, 1), 4),
        ]))
        return combined


def _create_mix_bar(combo: Dict[str, Any], strip_sizes: List[float], width: float):
    """Create a small horizontal bar showing the mix to scale."""
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib.units import mm

    qs = combo.get('qs', [])
    scrap_mm = combo.get('scrap_mm', 0)
    coil_width = sum(s * q for s, q in zip(strip_sizes, qs)) + scrap_mm

    drawing = Drawing(width, 12)
    scale = width / coil_width if coil_width > 0 else 1

    x = 0
    for i, (size, qty) in enumerate(zip(strip_sizes, qs)):
        color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
        for _ in range(qty):
            w_px = size * scale
            rect = Rect(x, 1, w_px, 10, fillColor=hex_color(color), strokeColor=None)
            drawing.add(rect)
            x += w_px

    # Scrap segment (minimum 2pt if scrap > 0)
    if scrap_mm > 0:
        w_px = max(2, scrap_mm * scale)
        rect = Rect(x, 1, w_px, 10, fillColor=hex_color(REPORT_COLORS['scrap']), strokeColor=None)
        drawing.add(rect)

    return drawing



def _create_cutting_drawing_png(report_data: Dict[str, Any], width: int, height: int):
    """Create a PNG image of the cutting plan drawing for Excel embedding."""
    try:
        from PIL import Image, ImageDraw
        from io import BytesIO

        selected = report_data['selected_combination']
        strip_sizes = report_data['coil_params']['strip_sizes']
        qs = selected.get('qs', [])
        scrap_mm = selected.get('scrap_mm', 0)
        coil_width = report_data['coil_params']['coil_width']

        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)

        # Calculate scale
        total_used = sum(s * q for s, q in zip(strip_sizes, qs)) + scrap_mm
        scale = width / coil_width if coil_width > 0 else 1

        x = 0
        for i, (size, qty) in enumerate(zip(strip_sizes, qs)):
            color = REPORT_COLORS[f'strip_{i}'] if i < 7 else '#000000'
            for _ in range(qty):
                w_px = max(1, int(size * scale))
                draw.rectangle([x, 0, x + w_px, height], fill=color)

                # Add label if wide enough
                if w_px > 30:
                    try:
                        from PIL import ImageFont
                        font = ImageFont.load_default()
                        text = str(int(size))
                        bbox = draw.textbbox((0, 0), text, font=font)
                        text_w = bbox[2] - bbox[0]
                        if text_w < w_px - 4:
                            draw.text((x + w_px/2 - text_w/2, height/2 - 7), text, fill='black', font=font)
                    except Exception:
                        pass

                x += w_px

        # Scrap block
        if scrap_mm > 0:
            w_px = max(3, int(scrap_mm * scale))
            draw.rectangle([x, 0, x + w_px, height], fill=REPORT_COLORS['scrap'], outline='black')

        # Save to bytes
        buf = BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Failed to create cutting drawing PNG: {e}")
        return None