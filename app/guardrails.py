"""Deterministic guardrails: Section 04 + 08 of Problem Statement."""
from __future__ import annotations

ALLOWED = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}

def _check_hours(hours) -> tuple[bool, str]:
    if not isinstance(hours, list) or not hours:
        return False, "hours must be non-empty list"
    if any(not isinstance(h, int) or h < 0 or h > 23 for h in hours):
        return False, "hours must be ints 0..23"
    if sorted(hours) != hours or len(set(hours)) != len(hours):
        return False, "hours must be unique ascending"
    return True, ""


def validate_directive(dtype: str, adj, battery_cap: float, n_notes: int, note_index: int) -> tuple[bool, str]:
    if dtype not in ALLOWED:
        return False, f"bad directive_type {dtype}"
    if not (0 <= note_index < n_notes):
        return False, "note_index out of range"
    if dtype == "no_op":
        if adj is not None:
            return False, "no_op must have null adjustment"
        return True, ""
    if not isinstance(adj, dict):
        return False, "adjustment must be object"
    ok, msg = _check_hours(adj.get("hours"))
    if not ok:
        return False, msg
    keys = set(adj.keys())
    if dtype == "solar_reduction":
        if keys != {"hours", "factor"}:
            return False, "solar_reduction needs hours+factor"
        f = adj["factor"]
        if not isinstance(f, (int, float)) or not (0 <= f <= 1):
            return False, "factor must be 0..1"
    elif dtype == "minimum_battery_reserve":
        if keys != {"hours", "minimum_energy_kwh"}:
            return False, "reserve needs hours+minimum_energy_kwh"
        v = adj["minimum_energy_kwh"]
        if not isinstance(v, (int, float)) or not (0 <= v <= battery_cap):
            return False, "reserve must be 0..capacity"
    elif dtype in ("no_charge_window", "no_discharge_window"):
        if keys != {"hours"}:
            return False, f"{dtype} needs only hours"
    elif dtype == "max_grid_window":
        if keys != {"hours", "max_grid_kwh"}:
            return False, "max_grid needs hours+max_grid_kwh"
        v = adj["max_grid_kwh"]
        if not isinstance(v, (int, float)) or v < 0:
            return False, "max_grid_kwh must be >=0"
    return True, ""
