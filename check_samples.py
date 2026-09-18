"""POST each public sample input to local service and check interpretation + replay."""
import json, sys, urllib.request

BASE = "http://127.0.0.1:8000"
pack = json.load(open("BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"))

def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

fails = 0
for case in pack["cases"]:
    inp, exp = case["input"], case["expected_output"]
    try:
        out = post("/optimize-energy", inp)
    except Exception as e:
        print(f"{case['id']}: REQUEST FAILED {e}"); fails += 1; continue
    # interpretation check vs ground truth
    ok = True
    for e, g in zip(sorted(out["directive_interpretation"], key=lambda x: x["note_index"]),
                    sorted(exp["directive_interpretation"], key=lambda x: x["note_index"])):
        if e["directive_type"] != g["directive_type"] or e["applies"] != g["applies"]:
            ok = False; break
        ea, ga = e["structured_adjustment"], g["structured_adjustment"]
        if (ea is None) != (ga is None):
            ok = False; break
        if ea and (ea.get("hours") != ga.get("hours") or
                   any(abs(ea.get(k, 0) - ga.get(k, 0)) > 0.01 for k in ga if k != "hours")):
            ok = False; break
    # energy replay: balance + solar + battery + neutrality
    eff = {h["hour"]: h["solar_kwh"] for h in inp["hours"]}
    for d in out["directive_interpretation"]:
        if d["directive_type"] == "solar_reduction" and d["applies"]:
            for h in d["structured_adjustment"]["hours"]:
                eff[h] *= d["structured_adjustment"]["factor"]
    E, valid = inp["battery"]["initial_energy_kwh"], True
    plank = {p["hour"]: p for p in out["hourly_plan"]}
    for h in range(24):
        p, dem = plank[h], next(x for x in inp["hours"] if x["hour"] == h)
        if p["solar_used_kwh"] - eff[h] > 0.01 or p["grid_kwh"] < -0.01:
            valid = False
        ch = p["battery_kwh"] if p["battery_action"] == "charge" else 0
        dis = p["battery_kwh"] if p["battery_action"] == "discharge" else 0
        if abs(p["grid_kwh"] + p["solar_used_kwh"] + dis - dem["demand_kwh"] - ch) > 0.01:
            valid = False
        E = E + ch - dis
        if abs(E - p["battery_energy_after_kwh"]) > 0.01:
            valid = False
    if abs(E - inp["battery"]["initial_energy_kwh"]) > 0.01:
        valid = False
    status = "PASS" if (ok and valid) else "FAIL"
    if status == "FAIL":
        fails += 1
    print(f"{case['id']}: interp={'OK' if ok else 'MISMATCH'} replay={'OK' if valid else 'INVALID'} -> {status} cost={out['total_cost_bdt']}")
print("FAILURES:", fails)
sys.exit(1 if fails else 0)
