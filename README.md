# GridWise LLM — BUP CSE Fest 2026 (Preliminary)

LLM-assisted campus energy scheduling: interprets operator notes into structured
directives, validates them deterministically, then LP-optimizes a 24h schedule.

Pipeline: `operator_notes -> Gemini (JSON mode) -> guardrails -> PuLP MILP -> replay-safe schedule`.

## Quickstart (clean environment)

```bash
pip install -r requirements.txt
cp .env.example .env   # then set GOOGLE_API_KEY inside .env
uvicorn app.main:app --port 8000
```

Health:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Optimize (SAMPLE-01 input shape):

```bash
curl -X POST http://127.0.0.1:8000/optimize-energy ^
  -H "Content-Type: application/json" ^
  --data @sample_request.json
```

`sample_request.json` is any `cases[i].input` object from
`BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`.

## Public-sample test

```bash
python check_samples.py
# posts all 10 public cases, checks directive_interpretation vs reference
# semantics and replays energy/battery/neutrality. Expect FAILURES: 0
```

## Configuration

| Var | Required | Default | Meaning |
| --- | --- | --- | --- |
| `GOOGLE_API_KEY` | yes (judging) | — | Gemini API key. Never committed (see `.gitignore`). |
| `GEMINI_MODEL` | no | `gemini-flash-lite-latest` | Alias always resolving to newest Flash-Lite release (stable pinned alt: `gemini-2.5-flash-lite`). Verified Sep-2026 via Google model docs. |
| `PORT` | no | `8000` | Service port (Docker honors `$PORT`). |

## Architecture

* **LLM role (mandatory path):** `app/interpreter.py:interpret_notes` calls Gemini
  with `response_mime_type=application/json`, `temperature=0`, strict prompt
  enumerating the 6 allowed directive types. Its output IS the constraints source
  for the optimizer — not just `plan_summary` text.
* **Deterministic guardrails:** `app/guardrails.py:validate_directive` enforces
  allowed types, `note_index` coverage, unique ascending `hours 0..23`,
  `factor 0..1`, `reserve 0..capacity`, `max_grid >= 0`, and
  `no_op <=> (applies=false, adjustment=null)`. On LLM failure a regex fallback
  (`fallback_interpret`: %/half/fraction parsing, AM/PM window normalization
  with start-inclusive/end-exclusive) is re-validated; else safe `no_op`.
  Pure hard-coded matching is NOT the primary path — Gemini is always tried first
  when a key is present.
* **Optimizer/solver:** `app/optimizer.py:optimize` — PuLP + CBC MILP minimizing
  `sum(grid*tariff)` s.t. effective solar, energy balance, battery bounds/rates,
  `E[23]==E[0]` neutrality, plus all directives. Binary per hour prevents
  degenerate simultaneous charge+discharge.
* **API:** `app/main.py` — `GET /health`, `POST /optimize-energy` (400 on bad
  shape/hours). Totals recomputed from `hourly_plan`.

## Docker fallback

```bash
docker build -t gridwise-llm:1.0 .
docker run --rm -p 8000:8000 -e GOOGLE_API_KEY=$GOOGLE_API_KEY gridwise-llm:1.0
curl http://127.0.0.1:8000/health
```

Image exposes `$PORT`, binds `0.0.0.0`, contains no secrets.

## Dependencies / credits

FastAPI, Uvicorn, Pydantic, PuLP (CBC), `google-generativeai`, python-dotenv.
AI coding assistant used for scaffolding; core guardrail/optimizer logic is
team-owned. Public docs referenced: Google Gemini model list (alias
`gemini-flash-lite-latest`, stable `gemini-2.5-flash-lite`).

## Known limitations

* `google-generativeai` is deprecated upstream (works, warns); migration to
  `google.genai` is future work.
* Gemini outage/quota falls back to regex parser — paraphrase robustness drops
  without the LLM; keep quota headroom during judging.
* Per-request solve is ~0.1–1s via CBC; p95 well under the 5s target locally.
