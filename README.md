# Laya

Open-source demo of a "typed decision" API — answers `bool` / `enum` / `number` questions
instantly instead of generating text. Includes two toy games (a real Doom scenario and a
custom pygame shooting range) where Laya drives the gameplay decisions.

See [HOW_LAYA_WORKS.md](HOW_LAYA_WORKS.md) for how the decision logic actually works, and
[JEV_VS_LAYA.md](JEV_VS_LAYA.md) for the Jev vs Laya comparison.

## Setup

```bash
cd /Users/vighnesh/Practice/laya-demo
uv sync
```

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
→ `{"answer": "refund", "type": "enum", "confidence": 0.78, "latency_ms": 0.03}`

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
