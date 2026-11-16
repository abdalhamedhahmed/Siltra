#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Material Weight Calculation Engine for Slitra

Pure math module - no Qt dependencies.
All steel material types use density 7.85 g/cm³.
"""

from typing import Dict, List, Tuple


class CoilWeightCalculator:
    """Material-weight calculation engine for coil slitting."""

    # Density in g/cm³ for all 6 material types (all steel)
    DENSITIES = {
        'HR': 7.85,    # Hot Rolled
        'CR': 7.85,    # Cold Rolled
        'GI': 7.85,    # Galvanized Iron
        'GL': 7.85,    # Galvalume
        'PPCR': 7.85,  # Pre-Painted Cold Rolled
        'CRBA': 7.85,  # Carbon Reinforced Base Alloy
    }

    @classmethod
    def get_density(cls, material: str) -> float:
        """Get density for a material type."""
        return cls.DENSITIES.get(material.upper(), 7.85)

    @classmethod
    def calculate_base_weight(cls, length_m: float, width_mm: float, thickness_mm: float, density: float) -> float:
        """
        Calculate weight of a single strip.
        weight (kg) = length_m * width_mm * thickness_mm * density / 1000
        """
        return (length_m * width_mm * thickness_mm * density) / 1000.0

    @classmethod
    def total_weight(cls, material: str, length_m: float, width_mm: float, thickness_mm: float) -> float:
        """Calculate total weight for a given material and dimensions."""
        density = cls.get_density(material)
        return cls.calculate_base_weight(length_m, width_mm, thickness_mm, density)

    @classmethod
    def reverse_length(cls, material: str, total_weight_kg: float, width_mm: float, thickness_mm: float) -> float:
        """
        Calculate theoretical length from total weight.
        length_m = total_weight_kg * 1000 / (width_mm * thickness_mm * density)
        Raises ValueError if width_mm <= 0, thickness_mm <= 0, or density <= 0.
        """
        density = cls.get_density(material)
        if width_mm <= 0 or thickness_mm <= 0 or density <= 0:
            raise ValueError("width, thickness, and density must be positive")
        return (total_weight_kg * 1000.0) / (width_mm * thickness_mm * density)

    @classmethod
    def validate_coil_weights(cls, weights: List[float], min_weight: float = 0.1) -> Tuple[bool, str]:
        """Validate all coil weights are positive and reasonable."""
        if not weights:
            return False, "No coil weights provided"

        for i, w in enumerate(weights):
            if w is None or w <= 0:
                return False, f"Coil {i+1} weight must be positive"
            if w < min_weight:
                return False, f"Coil {i+1} weight ({w} kg) is below minimum ({min_weight} kg)"
            if w > 100000:
                return False, f"Coil {i+1} weight ({w} kg) exceeds maximum (100,000 kg)"

        return True, "OK"

    @classmethod
    def compute_strip_weights(cls, material: str, theoretical_length_m: float,
                               strip_widths_mm: List[float], thickness_mm: float) -> List[float]:
        """
        Compute weight per strip for each strip size.
        Returns list of weights per strip (kg) corresponding to strip_widths_mm.
        """
        density = cls.get_density(material)
        return [cls.calculate_base_weight(theoretical_length_m, w, thickness_mm, density)
                for w in strip_widths_mm]

    @classmethod
    def compute_scrap_weight(cls, material: str, theoretical_length_m: float,
                              scrap_width_mm: float, thickness_mm: float) -> float:
        """Compute scrap weight for given scrap width."""
        density = cls.get_density(material)
        return cls.calculate_base_weight(theoretical_length_m, scrap_width_mm, thickness_mm, density)

    @classmethod
    def compute_coil_weights(cls, material: str, theoretical_length_m: float,
                              strip_widths_mm: List[float], quantities: List[int],
                              scrap_width_mm: float, thickness_mm: float,
                              num_coils: int) -> Dict[str, float]:
        """
        Compute all weights for a job order.

        Returns dict with:
        - weight_per_strip: list of weight per strip (kg) for each size
        - total_weight_per_strip: list of total weight (kg) for each size (qty * num_coils)
        - scrap_weight_per_coil: scrap weight per coil (kg)
        - scrap_weight_total: total scrap weight (kg) for all coils
        - total_strips_weight: sum of all strips weight
        - grand_total: total_strips_weight + scrap_weight_total
        """
        density = cls.get_density(material)

        # Weight per strip for each size
        weight_per_strip = []
        total_weight_per_strip = []
        for w, q in zip(strip_widths_mm, quantities):
            wps = cls.calculate_base_weight(theoretical_length_m, w, thickness_mm, density)
            weight_per_strip.append(wps)
            total_weight_per_strip.append(wps * q * num_coils)

        # Scrap weights
        scrap_per_coil = cls.calculate_base_weight(theoretical_length_m, scrap_width_mm, thickness_mm, density)
        scrap_total = scrap_per_coil * num_coils

        total_strips = sum(total_weight_per_strip)

        return {
            'weight_per_strip': weight_per_strip,
            'total_weight_per_strip': total_weight_per_strip,
            'scrap_weight_per_coil': scrap_per_coil,
            'scrap_weight_total': scrap_total,
            'total_strips_weight': total_strips,
            'grand_total': total_strips + scrap_total,
        }


def theoretical_length(total_weight_kg: float, width_mm: float, thickness_mm: float, material: str) -> float:
    """Convenience function for backward compatibility."""
    return CoilWeightCalculator.reverse_length(material, total_weight_kg, width_mm, thickness_mm)


def validate_coil_weights(weights: List[float], min_weight: float = 0.1) -> Tuple[bool, str]:
    """Convenience function for backward compatibility."""
    return CoilWeightCalculator.validate_coil_weights(weights, min_weight)


# JobOrder and Strip dataclasses for Phase B3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Strip:
    """Represents a single strip in the job order."""
    size_mm: float
    quantity_per_coil: int
    thickness_mm: float
    material: str
    theoretical_length_m: float
    weight_per_strip_kg: float = field(init=False)
    total_weight_kg: float = field(init=False)

    def __post_init__(self):
        self.weight_per_strip_kg = CoilWeightCalculator.total_weight(
            self.material, self.theoretical_length_m, self.size_mm, self.thickness_mm
        )
        self.total_weight_kg = self.weight_per_strip_kg * self.quantity_per_coil


@dataclass
class JobOrder:
    """Complete job order with all parameters and computed strips."""
    job_number: str
    phase: Literal["Draft", "Active", "Completed"]
    material: str
    width_mm: float
    thickness_mm: float
    coil_count: int
    coil_weights_kg: List[float]
    total_weight_kg: float
    theoretical_length_m: float
    created_at: datetime
    strips: List[Strip] = field(default_factory=list)
    consignment: str = ""

    def compute_strips(self, strip_widths: List[float], quantities: List[int], scrap_mm: float):
        """Compute all strips from the cutting plan."""
        self.strips = []
        for size, qty in zip(strip_widths, quantities):
            self.strips.append(Strip(
                size_mm=size,
                quantity_per_coil=qty,
                thickness_mm=self.thickness_mm,
                material=self.material,
                theoretical_length_m=self.theoretical_length_m
            ))
        # Add scrap as a strip if present
        if scrap_mm > 0:
            self.strips.append(Strip(
                size_mm=scrap_mm,
                quantity_per_coil=0,
                thickness_mm=self.thickness_mm,
                material=self.material,
                theoretical_length_m=self.theoretical_length_m
            ))