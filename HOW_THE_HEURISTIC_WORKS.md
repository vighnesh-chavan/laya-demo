# How the Heuristic Engine Works (Plain-English Report)

> **This file is about `app/engine.py` only** — the hand-written, no-model `heuristic` backend
> (`LAYA_BACKEND=heuristic`, the default). It is **not** the real Laya model. For how the actual
> open-weight Laya model (`LAYA_BACKEND=laya-mlx`) decides things, see
> [LAYA_MLX_VS_HEURISTIC.md](LAYA_MLX_VS_HEURISTIC.md). For how to switch between the two, see
> the "Backend: heuristic vs laya-mlx" section in [README.md](README.md).

## What the heuristic is, in one line

It's a small piece of hand-written Python that answers **yes/no**, **pick-one-option**, or **give-a-number** questions instantly — without using any AI model. It just counts words.

There is no machine learning, no training, no understanding of meaning. It is a set of simple rules dressed up to look like a smart decision engine.

---

## The three question types

The heuristic only answers three kinds of questions. You tell it which kind when you call the API.

### 1. Yes/No questions (`bool`)

**How it decides:**
It keeps two hardcoded lists of words:

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
You give it a list of options (e.g. "refund", "complaint", "spam"), each with a short label and optional description.

It breaks your question into words, then breaks each option's label+description into words too. For every option, it checks: *"What fraction of this option's own words also showed up in the question?"*

Whichever option has the highest overlap fraction wins.

**How confidence is calculated:**
The higher that overlap fraction, the higher the confidence (up to ~0.99). An option with zero overlapping words still "wins" if all the other options overlap even less — but confidence stays at the floor (0.5).

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
None of the option words appear in the question at all — every option scores 0.0, so it's a 3-way tie. It just picks whichever option happens to come **first in your list** and reports the floor confidence (0.5) to signal "not sure." This is an important limitation: a tie doesn't mean "complaint" is genuinely the best fit — it means the heuristic found nothing useful to go on.

---

### 3. Give-a-number questions (`number`)

**How it decides:**
It just scans your question text for any digits (like "8", "3.5", "100"). If it finds one or more numbers, it takes the **last number mentioned** and clamps it to stay within the `min_value`/`max_value` range you specified.

If no number appears anywhere in the question, it just returns the midpoint of your min/max range as a safe default guess.

**How confidence is calculated:**
- Found an actual number in the text → confidence = 0.9 (high, because it read a real digit)
- No number found, had to guess the midpoint → confidence = 0.5 (a shrug)

**Example:**
> "Rate urgency from 1 to 10 — this seems like an 8" (min=1, max=10)

Numbers found in the text: 1, 10, 8. Last one mentioned = 8. Since 8 is within range, answer = **8.0**, confidence = 0.9.

---

## The honest summary

| Question type | What it actually does | Smart-sounding part | What it really is |
|---|---|---|---|
| `bool` | Counts positive vs negative words | "confidence score" | Word counting with a scoring formula |
| `enum` | Measures word overlap per option | "picks best match" | Fraction math, no understanding |
| `number` | Finds digits with a regex | "extracts the answer" | Regex pattern matching |

**There is no context window, no memory, no reasoning, and no trained model.** Every request is judged only by the exact words you put in that single `question` string. Nothing from previous requests carries over, and there's no understanding of grammar, sarcasm, negation subtleties ("not bad" would likely be misread), or anything outside the hardcoded word lists.

## Why this still resembles "Laya" / "Jev"

Real decision models — the actual Laya (`LAYA_BACKEND=laya-mlx`) and the fictional Jev referenced in this demo's premise — are trained neural networks that *actually* understand language and output typed answers in milliseconds. This heuristic mimics their **API shape** (typed input → typed output → confidence → latency) to demonstrate the concept and the pattern — but the "brain" behind it here is simple rule-based logic, not a trained model. It's a stand-in that this project can swap out for the real Laya model (or your own classifier/embedding search) without changing the API at all — see [LAYA_MLX_VS_HEURISTIC.md](LAYA_MLX_VS_HEURISTIC.md) for how that swap performs in practice.
