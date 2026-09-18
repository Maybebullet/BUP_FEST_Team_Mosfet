"""LP optimizer: minimize grid cost subject to GridWise + directive constraints."""
from __future__ import annotations
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, PULP_CBC_CMD


def optimize(hours: list[dict], battery: dict, directives: list[dict]):
    n = 24
    demand = [h["demand_kwh"] for h in sorted(hours, key=lambda x: x["hour"])]
    solar = [h["solar_kwh"] for h in sorted(hours, key=lambda x: x["hour"])]
    tariff = [h["tariff_bdt_per_kwh"] for h in sorted(hours, key=lambda x: x["hour"])]

    eff_solar = list(solar)
    no_charge, no_discharge = set(), set()
    reserve = [battery["minimum_energy_kwh"]] * n
    grid_cap = [None] * n

    for d in directives:
        if d["directive_type"] == "no_op" or not d["applies"]:
            continue
        a = d["structured_adjustment"]
        hs = a["hours"]
        t = d["directive_type"]
        if t == "solar_reduction":
            for h in hs:
                eff_solar[h] = solar[h] * a["factor"]
        elif t == "minimum_battery_reserve":
            for h in hs:
                reserve[h] = max(reserve[h], a["minimum_energy_kwh"])
        elif t == "no_charge_window":
            no_charge.update(hs)
        elif t == "no_discharge_window":
            no_discharge.update(hs)
        elif t == "max_grid_window":
            for h in hs:
                grid_cap[h] = a["max_grid_kwh"] if grid_cap[h] is None else min(grid_cap[h], a["max_grid_kwh"])

    prob = LpProblem("gridwise", LpMinimize)
    grid = [LpVariable(f"g_{h}", lowBound=0) for h in range(n)]
    su = [LpVariable(f"s_{h}", lowBound=0) for h in range(n)]
    ch = [LpVariable(f"c_{h}", lowBound=0) for h in range(n)]
    dis = [LpVariable(f"d_{h}", lowBound=0) for h in range(n)]
    E = [LpVariable(f"e_{h}", lowBound=0) for h in range(n)]

    cap = battery["capacity_kwh"]
    e0 = battery["initial_energy_kwh"]
    mc = battery["max_charge_kwh_per_hour"]
    md = battery["max_discharge_kwh_per_hour"]

    prob += lpSum(grid[h] * tariff[h] for h in range(n))
    for h in range(n):
        prob += su[h] <= eff_solar[h]
        prob += grid[h] + su[h] + dis[h] == demand[h] + ch[h]
        # MILP: prevent simultaneous charge+discharge (degenerate LP solutions break replay)
        y = LpVariable(f"y_{h}", cat="Binary")
        prob += ch[h] <= mc * y
        prob += dis[h] <= md * (1 - y)
        if h in no_charge:
            prob += ch[h] == 0
        if h in no_discharge:
            prob += dis[h] == 0
        if grid_cap[h] is not None:
            prob += grid[h] <= grid_cap[h]
        prev = e0 if h == 0 else E[h - 1]
        prob += E[h] == prev + ch[h] - dis[h]
        prob += E[h] >= reserve[h]
        prob += E[h] <= cap
    prob += E[n - 1] == e0  # end-of-day neutrality

    prob.solve(PULP_CBC_CMD(msg=0))
    plan = []
    for h in range(n):
        gv, sv, cv, dv, ev = (v.value() or 0 for v in (grid[h], su[h], ch[h], dis[h], E[h]))
        if cv > 1e-6:
            act, kv = "charge", cv
        elif dv > 1e-6:
            act, kv = "discharge", dv
        else:
            act, kv = "idle", 0.0
        plan.append({
            "hour": h, "grid_kwh": round(gv, 4), "solar_used_kwh": round(sv, 4),
            "battery_action": act, "battery_kwh": round(kv, 4),
            "battery_energy_after_kwh": round(ev, 4),
        })
    total_grid = round(sum(p["grid_kwh"] for p in plan), 4)
    total_cost = round(sum(p["grid_kwh"] * tariff[p["hour"]] for p in plan), 4)
    peak = round(max(p["grid_kwh"] for p in plan), 4)
    return plan, total_grid, total_cost, peak
