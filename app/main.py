from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
load_dotenv()

from app.models import OptimizeRequest
from app.guardrails import validate_directive
from app.interpreter import interpret_notes, fallback_interpret
from app.optimizer import optimize

app = FastAPI(title="GridWise LLM")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy")
def optimize_energy(req: OptimizeRequest):
    n = len(req.operator_notes)
    if any(not t or not t.strip() for t in req.operator_notes):
        return JSONResponse({"error": "operator_notes must be non-empty strings"}, status_code=400)
    hours_sorted = sorted([h.model_dump() for h in req.hours], key=lambda x: x["hour"])
    if [h["hour"] for h in hours_sorted] != list(range(24)):
        return JSONResponse({"error": "hours must be exactly 0..23"}, status_code=400)

    cap = req.battery.capacity_kwh
    raw = interpret_notes(req.operator_notes, cap)

    directives = []
    for i, r in enumerate(raw):
        dtype = r.get("directive_type")
        adj = r.get("structured_adjustment")
        applies = bool(r.get("applies"))
        ok, _ = validate_directive(dtype, adj, cap, n, r.get("note_index", i))
        if not ok or (dtype == "no_op") != (not applies) or (dtype != "no_op" and not applies):
            # SAFE FAILURE: fall back to deterministic parse, else no_op
            fb = fallback_interpret(req.operator_notes[i], i, cap)
            ok2, _ = validate_directive(fb["directive_type"], fb["structured_adjustment"], cap, n, i)
            r = fb if ok2 else {"note_index": i, "applies": False, "directive_type": "no_op",
                                "structured_adjustment": None, "explanation": "Safe fallback no_op."}
            dtype, adj, applies = r["directive_type"], r["structured_adjustment"], r["applies"]
        directives.append({"note_index": i, "applies": applies, "directive_type": dtype,
                           "structured_adjustment": adj, "explanation": str(r.get("explanation", ""))[:300]})

    plan, tg, tc, peak = optimize(hours_sorted, req.battery.model_dump(), directives)
    return {"scenario_id": req.scenario_id, "directive_interpretation": directives,
            "hourly_plan": plan, "total_grid_kwh": tg, "total_cost_bdt": tc,
            "peak_grid_kwh": peak,
            "plan_summary": f"Applied {sum(d['applies'] for d in directives)} directive(s); LP-minimized grid cost with end-of-day neutrality."}
