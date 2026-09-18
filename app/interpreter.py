"""Gemini interpreter with deterministic fallback (regex) so local tests work without key."""
from __future__ import annotations
import json, os, re

PROMPT = """You interpret campus operator notes into GridWise directives.
Allowed directive_type: solar_reduction, minimum_battery_reserve, no_charge_window, no_discharge_window, max_grid_window, no_op.
Battery capacity: {cap} kWh.
Notes (index: text):
{notes}
Return ONLY a JSON array, one object per note in order:
{{"note_index":i,"applies":bool,"directive_type":str,"structured_adjustment":{{"hours":[...]}} or null,"explanation":str}}
Rules:
- no_op => applies=false, structured_adjustment=null.
- else applies=true. hours: unique ints 0-23 ascending, start-inclusive end-exclusive (1PM-3PM=[13,14]).
- solar_reduction needs factor 0..1 (usable fraction remaining; 80% reduction=0.2).
- minimum_battery_reserve needs minimum_energy_kwh (convert % of capacity to kWh; 0..capacity).
- max_grid_window needs max_grid_kwh (>=0).
- no_charge/no_discharge windows need only hours.
"""

_HOUR_WORDS = {"midnight": 0, "noon": 12}
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def _parse_hour(tok: str, mer: str | None) -> int | None:
    tok = tok.strip().lower()
    if tok in _HOUR_WORDS:
        return _HOUR_WORDS[tok]
    m = re.match(r"(\d{1,2})(?::00)?", tok)
    if m:
        h = int(m.group(1))
        if mer == "pm" and h != 12:
            h += 12
        if mer == "am" and h == 12:
            h = 0
        return h if 0 <= h <= 23 else None
    if tok in _NUM:
        h = _NUM[tok]
        if mer == "pm" and h != 12:
            h += 12
        return h
    return None


def _window(note: str) -> list[int] | None:
    n = note.lower()
    pats = [
        r"(?:from|between)\s+([\w:]+)\s*(am|pm)?\s*(?:until|to|-|and)\s+([\w:]+)\s*(am|pm)?",
        r"(\d{1,2})(?::00)?\s*-\s*(\d{1,2})\s*(pm|am)",
    ]
    m = re.search(pats[0], n)
    if m:
        s = _parse_hour(m.group(1), m.group(2) or m.group(4))
        e = _parse_hour(m.group(3), m.group(4))
        if s is not None and e is not None and e > s:
            return list(range(s, e))
    m = re.search(pats[1], n)
    if m:
        s = _parse_hour(m.group(1), m.group(3))
        e = _parse_hour(m.group(2), m.group(3))
        if s is not None and e is not None and e > s:
            return list(range(s, e))
    return None


def fallback_interpret(note: str, idx: int, cap: float) -> dict:
    n = note.lower()
    hours = _window(note) or []
    # distractor heuristic: no energy keywords
    energy_kw = ["solar", "battery", "charge", "charging", "charger", "discharge",
                 "discharging", "grid", "reserve", "kwh", "import", "feeder",
                 "transformer", "substation", "panel", "pv", "inverter", "charger",
                 "maintenance", "inspection", "outage", "circuit", "relay",
                 "protection", "emergency"]
    if not any(k in n for k in energy_kw):
        return {"note_index": idx, "applies": False, "directive_type": "no_op",
                "structured_adjustment": None, "explanation": "No energy rule; distractor."}
    if "solar" in n or "panel" in n or "pv" in n:
        f = 1.0
        m = re.search(r"(\d+)\s*%.*(reduction|drop|cut)|reduction.*(\d+)\s*%", n)
        pct = None
        if m:
            pct = next((int(g) for g in m.groups() if g and g.isdigit()), None)
        m2 = re.search(r"(?:to|as|about|roughly|leave)\s*(?:about\s*)?(\d+)\s*%", n)
        if pct is not None:
            f = round(1 - pct / 100, 4)
        elif m2:
            f = round(int(m2.group(1)) / 100, 4)
        elif "half" in n:
            f = 0.5
        elif "one-fifth" in n or "one fifth" in n:
            f = 0.2
        return {"note_index": idx, "applies": True, "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": hours, "factor": f},
                "explanation": "Solar reduction (fallback parse)."}
    if "reserve" in n or "keep at least" in n or "remain in the battery" in n or "stored in the battery" in n:
        val = 0.0
        m = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n)
        mp = re.search(r"(\d+(?:\.\d+)?)\s*%", n)
        if m:
            val = float(m.group(1))
        elif mp:
            val = round(float(mp.group(1)) / 100 * cap, 4)
        return {"note_index": idx, "applies": True, "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": hours, "minimum_energy_kwh": val},
                "explanation": "Battery reserve (fallback parse)."}
    if "not exceed" in n or "must stay" in n or "capped" in n or "cap" in n or "limit" in n or "import" in n:
        val = 0.0
        m = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n)
        if m:
            val = float(m.group(1))
        return {"note_index": idx, "applies": True, "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": hours, "max_grid_kwh": val},
                "explanation": "Grid cap (fallback parse)."}
    if "not charge" in n or "charging" in n or "charger" in n or ("charge" in n and ("unavailable" in n or "disabled" in n or "isolated" in n)):
        # disambiguate discharge
        if "discharge" in n:
            return {"note_index": idx, "applies": True, "directive_type": "no_discharge_window",
                    "structured_adjustment": {"hours": hours}, "explanation": "No-discharge (fallback)."}
        return {"note_index": idx, "applies": True, "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": hours}, "explanation": "No-charge (fallback)."}
    if "discharge" in n or "must not discharge" in n:
        return {"note_index": idx, "applies": True, "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": hours}, "explanation": "No-discharge (fallback)."}
    return {"note_index": idx, "applies": False, "directive_type": "no_op",
            "structured_adjustment": None, "explanation": "Unclear; safe no_op."}


def interpret_notes(notes: list[str], cap: float) -> list[dict]:
    key = os.getenv("GOOGLE_API_KEY", "")
    if key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
                generation_config={"response_mime_type": "application/json", "temperature": 0},
            )
            notes_txt = "\n".join(f"{i}: {t}" for i, t in enumerate(notes))
            resp = model.generate_content(
                PROMPT.format(cap=cap, notes=notes_txt),
                request_options={"timeout": 12},
            )
            arr = json.loads(resp.text)
            if isinstance(arr, list) and len(arr) == len(notes):
                return arr
        except Exception:
            pass  # fall through to deterministic fallback
    return [fallback_interpret(t, i, cap) for i, t in enumerate(notes)]
