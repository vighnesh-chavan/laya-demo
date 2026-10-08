# Laya

Open-source demo of a "typed decision" API — answers `bool` / `enum` / `number` questions
instantly instead of generating text. Includes two toy games (a real Doom scenario and a
custom pygame shooting range) where Laya drives the gameplay decisions.

See [HOW_LAYA_WORKS.md](HOW_LAYA_WORKS.md) for how the decision logic actually works, and
[JEV_VS_LAYA.md](JEV_VS_LAYA.md) for the Jev vs Laya comparison.

## Setup

```bash
cd <repo>
uv sync
```

## Backend: heuristic vs laya-mlx

By default this API runs on a hand-written heuristic — no model, sub-millisecond responses (see
[HOW_LAYA_WORKS.md](HOW_LAYA_WORKS.md)). You can switch to the actual open-weight Laya model
(from Convai Innovations, via `laya-mlx` running natively on Apple Silicon) using a `.env` file:

```bash
cp .env.example .env
```

- `LAYA_BACKEND` — the on/off switch: `heuristic` = our own hand-written word-matching engine (no model at all), `laya-mlx` = the actual downloaded Laya model.
- `LAYA_MODEL` — which Hugging Face repo to load the model from (only used when `LAYA_BACKEND=laya-mlx`). Defaults to `aac6fef/laya-typed-decisions-mlx` (421M, tuned for typed-decision workflows) — of the three available `laya-mlx` checkpoints, this one discriminated best in our own testing (see `LAYA_MLX_VS_HEURISTIC.md`). Others can be swapped in by changing this value — no code changes needed — but expect similar accuracy limitations; see that report for details.

To use simulation only (no model, nothing downloaded): leave `LAYA_BACKEND=heuristic`, or don't create a `.env` file at all — that's the default, and the laya-mlx code path is never imported or loaded in that case.

**Download/caching:** the first request after switching to `LAYA_BACKEND=laya-mlx` triggers a one-time
download of the model weights, cached locally by Hugging Face Hub (typically `~/.cache/huggingface/`).
Every request after that first load reuses the cache — no re-download unless the cache is cleared.

**Latency trade-off:** laya-mlx is genuinely slower than the heuristic — expect roughly
200–450ms per call on CPU (faster on Apple Silicon GPU via MLX, but still far from the heuristic's
sub-millisecond responses). The FastAPI `/decide` contract (request/response shape) is identical
either way, so nothing downstream changes — but if you run the games
([shooting_range.py](shooting_range.py) / [play_doom.py](play_doom.py)) against laya-mlx,
expect visibly laggier decisions, since they call `/decide` every 2–6 frames.

## Running

### 1. Start the API (always required first)

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs

### 2a. Play the pygame shooting range

You move the monster, Laya aims and shoots.

```bash
uv run python shooting_range.py
```

- Pick a difficulty at launch: `1` easy, `2` medium, `3` high, `4` xhigh (controls aim speed)
- Move the monster with the arrow keys (up/down/left/right)

### 2b. Or run the real Doom scenario

Laya both aims and moves — fully autonomous, no player input.

```bash
uv run python play_doom.py
```

## Stopping

```bash
pkill -f "shooting_range.py"
pkill -f "play_doom.py"
pkill -f "uvicorn app.main:app"
```

## Example API payloads

The API is running at `http://127.0.0.1:8000` (or wherever you started uvicorn). All examples
below are `POST /decide`.

### bool — clear positive
```json
{ "question": "Confirm this account is safe and valid", "type": "bool" }
```
→ `{"answer": true, "type": "bool", "confidence": 0.95, "latency_ms": 0.18}`

### bool — clear negative
```json
{ "question": "This looks unsafe, please reject and deny it", "type": "bool" }
```
→ `{"answer": false, "type": "bool", "confidence": 0.95, "latency_ms": 0.02}`

### bool — no signal words (defaults to true, low confidence)
```json
{ "question": "What do you think about this order?", "type": "bool" }
```
→ `{"answer": true, "type": "bool", "confidence": 0.5, "latency_ms": 0.01}`

### enum — support ticket routing
```json
{
  "question": "Customer wants a refund for a late delivery",
  "type": "enum",
  "options": [
    { "label": "refund", "description": "money back for a delivery issue" },
    { "label": "bug_report", "description": "software defect or crash" },
    { "label": "spam" }
  ]
}
```
→ `{"answer": "refund", "type": "enum", "confidence": 0.696, "latency_ms": 0.03}`

### enum — no word overlap at all (falls back to the first option, low confidence)
```json
{
  "question": "asdf qwerty banana",
  "type": "enum",
  "options": [
    { "label": "refund", "description": "money back for a delivery issue" },
    { "label": "bug_report", "description": "software defect or crash" },
    { "label": "spam" }
  ]
}
```
→ `{"answer": "refund", "type": "enum", "confidence": 0.5, "latency_ms": 0.02}`

### number — value embedded in the text
```json
{ "question": "On a scale of 1 to 5, I would rate this a 4", "type": "number", "min_value": 1, "max_value": 5 }
```
→ `{"answer": 4.0, "type": "number", "confidence": 0.9, "latency_ms": 0.01}`

### number — out-of-range value gets clamped
```json
{ "question": "I would give this a 20", "type": "number", "min_value": 0, "max_value": 10 }
```
→ `{"answer": 10.0, "type": "number", "confidence": 0.9, "latency_ms": 0.01}` (20 clamped down to max=10)

### number — no digits, falls back to the midpoint
```json
{ "question": "How risky does this look?", "type": "number", "min_value": 0, "max_value": 100 }
```
→ `{"answer": 50.0, "type": "number", "confidence": 0.5, "latency_ms": 0.01}`

### health check
```bash
curl -s http://127.0.0.1:8000/health
```
→ `{"status": "ok"}`
