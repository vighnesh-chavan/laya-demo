# How Laya Works (Plain-English Report)

> **Note:** everything below describes the `heuristic` backend (the default, `LAYA_BACKEND=heuristic`).
> This project can also run against the actual open-weight Laya model via `LAYA_BACKEND=laya-mlx` — see
> the "Backend: heuristic vs laya-mlx" section in [README.md](README.md) for how that works and
> what changes (genuine model inference instead of word-counting, and noticeably higher latency).

## What Laya is, in one line

Laya is a small API that answers **yes/no**, **pick-one-option**, or **give-a-number** questions instantly — without using any AI model. It just counts words.

There is no machine learning, no training, no understanding of meaning. It is a set of simple rules dressed up to look like a smart decision engine.

---

## The three question types

Laya only answers three kinds of questions. You tell it which kind when you call the API.

### 1. Yes/No questions (`bool`)

**How it decides:**
Laya keeps two hardcoded lists of words:

- **Positive list:** yes, good, safe, approve, valid, correct, true, allow, accept, confirm, ok, okay
- **Negative list:** no, not, bad, unsafe, reject, invalid, incorrect, false, deny, never, cancel, refuse

It looks at your question, breaks it into individual words, and counts how many of those words match each list.

- More negative-list words than positive-list words → answer is **False**
- More positive-list words (or a tie) → answer is **True**
- No matching words at all → defaults to **True**, but with the lowest possible confidence

**How confidence is calculated:**
The more matching words it finds, the more "sure" it pretends to be — up to a cap of 3 matches. Zero matches means it's basically guessing (confidence 0.5, a coin flip).

**Example:**
> "Is this invalid and should we deny it?"

Words found: `invalid`, `deny` → both are in the negative list → 2 negative hits, 0 positive hits.
Result: **answer = False**, confidence ≈ 0.82 (fairly confident, because it found 2 matching words)

---

### 2. Pick-one-option questions (`enum`)

**How it decides:**
You give Laya a list of options (e.g. "refund", "complaint", "spam"), each with a short label and optional description.

Laya breaks your question into words, then breaks each option's label+description into words too. For every option, it checks: *"What fraction of this option's own words also showed up in the question?"*

Whichever option has the highest overlap fraction wins.

**How confidence is calculated:**
The higher that overlap fraction, the higher the confidence (up to ~0.99). A option with zero overlapping words still "wins" if all the other options overlap even less — but confidence stays at the floor (0.5).

**Example:**
> Question: "What category is a refund request for a late delivery?"
> Option "refund" (description: "money back for delivery")

The option's own words are: refund, money, back, for, delivery (5 words). Of those, "refund" and "delivery" also appear in the question → 2 out of 5 words matched → this option scores higher than "complaint" or "spam", so it wins.

**The full step-by-step flow:**

```
 1. Request comes in with a question + a list of options
                     │
                     ▼
 2. Break the question into a set of lowercase words
    "What category is a refund request for a late delivery?"
    → {what, category, is, a, refund, request, for, late, delivery}
                     │
                     ▼
 3. For EACH option, break its label + description into words too
    "refund"      + "money back for delivery" → {refund, money, back, for, delivery}
    "complaint"   + "general dissatisfaction"  → {complaint, general, dissatisfaction}
    "spam"        + (no description)           → {spam}
                     │
                     ▼
 4. For each option, count: how many of ITS OWN words also appear
    in the question's word set?
      refund:     {refund, delivery} matched     → 2 / 5 words = 0.40
      complaint:  {} matched                     → 0 / 3 words = 0.00
      spam:       {} matched                     → 0 / 1 words = 0.00
                     │
                     ▼
 5. Sort options by score, highest first
      refund (0.40)  >  complaint (0.00)  =  spam (0.00)
                     │
                     ▼
 6. Pick the top scorer → "refund"
    Turn its score into a confidence: 0.5 + 0.49 × 0.40 = 0.696 ≈ 0.7
                     │
                     ▼
 7. Return { "answer": "refund", "confidence": 0.7 }
```

**Request payload used above:**
```json
{
  "question": "What category is a refund request for a late delivery?",
  "type": "enum",
  "options": [
    { "label": "refund", "description": "money back for delivery" },
    { "label": "complaint", "description": "general dissatisfaction" },
    { "label": "spam" }
  ]
}
```
**Response:**
```json
{
  "answer": "refund",
  "type": "enum",
  "confidence": 0.745,
  "latency_ms": 0.023
}
```
*(This is a bit higher than the hand-calculated 0.696 in the walkthrough above because the walkthrough's word sets above still include filler words like "for". The real tokenizer deliberately strips common filler words — "a", "for", "in", "up", "the", "is", and similar — from *both* the question and the options before comparing, so the "refund" option's own word set actually shrinks to `{refund, money, back, delivery}` (4 words instead of 5), and the match becomes 2/4 = 0.5 instead of 2/5 = 0.4, pushing confidence to 0.745. This stopword filter matters: without it, a sentence like "no target in sight" would accidentally "match" any option description containing the word "in", just because both share a meaningless filler word.)*

**A second example — where the "best" match is still weak:**
```json
{
  "question": "customer is upset about the website",
  "type": "enum",
  "options": [
    { "label": "refund", "description": "money back for delivery" },
    { "label": "complaint", "description": "general dissatisfaction" },
    { "label": "spam" }
  ]
}
```
Response:
```json
{
  "answer": "refund",
  "type": "enum",
  "confidence": 0.5,
  "latency_ms": 0.018
}
```
None of the option words appear in the question at all — every option scores 0.0, so it's a 3-way tie. Laya just picks whichever option happens to come **first in your list** and reports the floor confidence (0.5) to signal "not sure." This is an important limitation: a tie doesn't mean "complaint" is genuinely the best fit — it means Laya found nothing useful to go on.

---

### 3. Give-a-number questions (`number`)

**How it decides:**
Laya just scans your question text for any digits (like "8", "3.5", "100"). If it finds one or more numbers, it takes the **last number mentioned** and clamps it to stay within the `min_value`/`max_value` range you specified.

If no number appears anywhere in the question, it just returns the midpoint of your min/max range as a safe default guess.

**How confidence is calculated:**
- Found an actual number in the text → confidence = 0.9 (high, because it read a real digit)
- No number found, had to guess the midpoint → confidence = 0.5 (a shrug)

**Example:**
> "Rate urgency from 1 to 10 — this seems like an 8" (min=1, max=10)

Numbers found in the text: 1, 10, 8. Last one mentioned = 8. Since 8 is within range, answer = **8.0**, confidence = 0.9.

---

---

## How the actual Laya model works (`LAYA_BACKEND=laya-mlx`)

This project can also run against the actual open-weight Laya model (from Convai Innovations,
via the `laya-mlx` package) instead of the heuristic above. This section explains how that one
decides things, and how we translate between our simple API and its native format.

**It's a real trained model, not word-counting.** `laya-mlx` loads a small decision transformer
(as little as 322M parameters) that has actually learned to read a text description of a
situation and produce a structured judgment — the same shape as a classifier, but phrased as
typed questions it was trained on. No regexes, no hardcoded word lists.

**Its native question types aren't quite `bool`/`enum`/`number` — they're `noul`/`choice`/`score`:**

| Laya's native type | What it returns | What it's for |
|---|---|---|
| `noul` | a single probability, 0–1 | yes/no-style judgments |
| `choice` | one label from a `criteria` dict, plus a confidence | picking one option among several |
| `score` | an index into an ordered list of labeled buckets, plus a confidence | rating something on an ordinal scale |

**How `app/real_engine.py` adapts each of our three question types onto that:**

- **`bool` → `noul`**: we hand the question straight through as a single `noul` question. The model
  returns a 0–1 value; `>= 0.5` becomes `True`. Confidence is just how far that value sits from the
  0.5 fence (e.g. 0.9 → confident `True`; 0.15 → confident `False`).
- **`enum` → `choice`**: our `options` list becomes the model's `criteria` dict (`{label: description}`).
  The model picks one label directly and reports its own confidence for that pick — no word-counting
  involved, it's weighing the option descriptions against the question with learned representations.
- **`number` → `score`**: Laya's native `score` type only understands a small ordered list of labeled
  buckets (e.g. 5 rungs from "very low" to "very high"), not an arbitrary continuous range. So we
  generate 5 evenly-spaced buckets between your `min_value`/`max_value`, ask the model to pick a rung,
  and linearly rescale that rung back into your original range. This is the one place where the
  adapter is lossy — you get back one of 5 buckets' worth of precision, not a free-floating number.

**What stays identical either way:** the `/decide` request/response shape (`answer`, `type`,
`confidence`, `latency_ms`) never changes — `main.py` just points at `real_engine` instead of
`engine` based on `LAYA_BACKEND`. Nothing downstream (the games, Swagger docs, this file's API
examples) has to know or care which backend answered.

**The real trade-off: latency.** The heuristic is sub-millisecond because it's just string
matching. The real model is an actual neural network forward pass — expect roughly 50–450ms per
call (varies with hardware and whether this is the first call after the model's weights finished
loading). See the "Backend: heuristic vs laya-mlx" section in [README.md](README.md) for how to
switch, and the download/caching details.

---

## The honest summary

| Question type | What it actually does | Smart-sounding part | What it really is |
|---|---|---|---|
| `bool` | Counts positive vs negative words | "confidence score" | Word counting with a scoring formula |
| `enum` | Measures word overlap per option | "picks best match" | Fraction math, no understanding |
| `number` | Finds digits with a regex | "extracts the answer" | Regex pattern matching |

**There is no context window, no memory, no reasoning, and no real model.** Every request is judged only by the exact words you put in that single `question` string. Nothing from previous requests carries over, and there's no understanding of grammar, sarcasm, negation subtleties ("not bad" would likely be misread), or anything outside the hardcoded word lists.

## Why this still resembles "Laya" / "Jev"

Real decision models (like the fictional Jev/Laya described in this demo's premise) are trained neural networks that *actually* understand language and output typed answers in milliseconds. This project mimics their **API shape** (typed input → typed output → confidence → latency) to demonstrate the concept and the pattern — but the "brain" behind it here is simple rule-based logic, not a trained model. It's a stand-in you could later swap out for a real classifier, embedding similarity search, or small local model without changing the API at all.
