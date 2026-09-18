from typing import Literal, Union
from pydantic import BaseModel, Field

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

class HourInput(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float

class BatteryInput(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float

class OptimizeRequest(BaseModel):
    scenario_id: str
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryInput

class StructuredAdjustment(BaseModel):
    hours: list[int] | None = None
    factor: float | None = None
    minimum_energy_kwh: float | None = None
    max_grid_kwh: float | None = None

    model_config = {"extra": "forbid"}

class DirectiveInterpretation(BaseModel):
    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict | None
    explanation: str

class HourlyPlanEntry(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float

class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
