# Heuristic vs laya-mlx: Test Report

This compares the two `/decide` backends (`LAYA_BACKEND=heuristic` vs `LAYA_BACKEND=laya-mlx`)
across all three live flows in this repo: the plain `/decide` API, `play_doom.py`, and
`shooting_range.py`. All numbers below are from actual runs against this codebase, not
estimates.

**laya-mlx setup used:** checkpoint `aac6fef/laya-typed-decisions-mlx` (421M, "tuned for typed
workflows"). This is now the default `LAYA_MODEL` — of the three available `laya-mlx`
checkpoints, it was the best-discriminating one we found (see "Checkpoint comparison" below).

## How laya-mlx actually computes an answer

This is a real trained model, not word-counting (contrast with `app/engine.py`, the heuristic —
see [HOW_THE_HEURISTIC_WORKS.md](HOW_THE_HEURISTIC_WORKS.md)). `laya-mlx` loads a small decision
transformer (as little as 322M parameters) that has actually learned to read a text description
of a situation and produce a structured judgment — the same shape as a classifier, but phrased as
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
`engine` based on `LAYA_BACKEND`. Nothing downstream (the games, Swagger docs) has to know or
care which backend answered.

## Results

| Flow | Metric | Heuristic | laya-mlx (`laya-typed-decisions-mlx`) |
|---|---|---|---|
| `/decide` API (bool/enum/number, 6 canned cases) | Accuracy | 6/6 (100%) | 4/6 (67%) |
| `/decide` API | Avg latency | ~1.5ms (steady state) | ~30ms (steady state), 1.5s on first call (model load) |
| `play_doom.py` (`defend_the_center`, `doom_skill=2`) | Shoot accuracy* | 100% (0 wasted shots across 5 trials, 794-928 shots/trial) | ~22% (most "shoot" calls fired with no monster centered) |
| `play_doom.py` | Avg survival | ~1106 ticks (5 trials) | ~375 ticks (3 trials, capped at 400) |
| `shooting_range.py` (5-way enum, grid of 36-121 synthetic offsets) | Decision accuracy | 100% (121/121) | 33% (12/36) |
| `shooting_range.py` | Avg latency/decision | ~1.5ms | ~70ms |

\* *Shoot accuracy = fraction of "shoot" decisions where a live monster was actually centered in
the crosshair at that moment (not shooting at empty air or a dead monster's blood decal).*

laya-mlx's enum mistakes aren't random noise — it has a visible bias: it answers `shoot`
far more often than warranted (even when no monster is present), and in the 5-way shooting-range
test it frequently picked `turn_left` when the correct answer was `turn_right` and vice versa.
The `number` mismatches in the API test are different: they're an adapter limitation, not a model
error — Laya's `score` type only supports ~5 ordinal buckets, so our bool/enum/number ↔
noul/choice/score adapter can only return one of 5 quantized values, not an exact number.

## Checkpoint comparison

We also tested the other two `laya-mlx` checkpoints on the same 4 synthetic Doom states
(no-target / left / right / centered) before picking a default:

| Checkpoint | Size | Correct / 4 | Notes |
|---|---|---|---|
| `laya-multilingual-mlx` (previous default) | 322M | 0/4 | Always answered `shoot` |
| `laya-mlx` (English-only) | 421M | 0/4 | Always answered `shoot` |
| `laya-typed-decisions-mlx` (new default) | 421M | 1/4 | Got "left off-center" right; still wrong on the other 3 |

None of the three checkpoints reliably solves this task — `laya-typed-decisions-mlx` is simply
the least-wrong of the three we could test, which is why it's now the default `LAYA_MODEL`.

## Why the gap

The heuristic is purpose-built for this exact shape of text (hand-written word lists and
overlap scoring tuned against this repo's own option descriptions), so it performs close to
perfectly on them by construction — that's also its biggest weakness (see below). laya-mlx
is a small (322-421M parameter), general-purpose typed-decision model trained on a broad
mix of tasks (support tickets, approvals, scoring); it was never trained on Doom-style spatial
descriptions, so it's operating out-of-distribution here. Its probability margins in our testing
were often slim (e.g. `shoot: 0.55` vs `turn_left: 0.24`) — genuinely uncertain, not confidently
wrong in a useful way.

## Pros and cons

### Heuristic engine (`app/engine.py`)

**Pros**
- Perfect accuracy on every flow tested here, because it's hand-tuned against this exact wording
- Sub-millisecond latency — no model load, no inference, negligible impact on game frame rate
- Zero setup: no downloads, no GPU/Metal dependency, works offline immediately
- Fully deterministic and debuggable — every decision traces to a readable word-list/overlap rule

**Cons**
- Brittle: only works because the option descriptions were hand-written to contain the exact
  words the heuristic looks for. Rephrase a question or option slightly and accuracy can collapse
  (we hit this directly with the stopword bug — see `HOW_THE_HEURISTIC_WORKS.md`)
- Not a trained decision model — there's no generalization to novel phrasing, languages, or domains
  outside what the word lists anticipate
- Doesn't scale as a demo of the "genuine AI typed-decisions" pitch — it's a convincing stand-in,
  not the genuine article

### laya-mlx (`app/real_engine.py`)

**Pros**
- An actual trained model — demonstrates the genuine typed-decision API contract
  (`noul`/`choice`/`score`) and real inference, not string matching
- Apple Silicon-native via MLX/Metal — no PyTorch needed, reasonably fast per call (~30-70ms
  steady state) for a real forward pass
- Generalizes in principle to phrasing/domains the heuristic was never tuned for (support
  tickets, approvals, scoring are what it was actually trained on — Doom was never representative)

**Cons**
- Meaningfully lower accuracy on this repo's specific game-state text — 22-33% decision accuracy
  in the games we tested, vs 100% for the heuristic
- One-time download required (several hundred MB per checkpoint), and a slow first call while
  weights load (we saw up to ~1.5s)
- 20-50x higher per-call latency than the heuristic — noticeably laggier in both games, since
  `/decide` is called every 1-6 frames
- The `number` → `score` adapter is inherently lossy (5 ordinal buckets, not a continuous range)
  regardless of model quality
- None of the three available `laya-mlx` checkpoints handle Doom-style spatial/game-state text
  well — this looks like a genuine out-of-domain gap, not a bug we can adapter our way out of

## Would a dedicated GPU instance (AWS/on-prem) help?

We researched this rather than guessing. Short answer: **it would not fix the accuracy problem,
and for this repo's real-time game loops it likely wouldn't even improve latency** — it mainly
helps a different scenario (high-concurrency production traffic), which isn't what this demo does.

**Published single-question latency benchmarks:**

| Setup | Checkpoint | P50 latency (single question) |
|---|---|---|
| Apple M3 Max (40-core GPU, 128GB unified memory), laya-mlx | 421M English | ~13.4ms |
| Apple M3 Max, laya-mlx | 322M multilingual | ~7.4ms |
| Tesla T4 GPU (cloud), base `laya` (PyTorch) | 421M English | ~39.5ms |
| Tesla T4 GPU (cloud), base `laya` (PyTorch) | 322M multilingual | ~32.8ms |

For a single decision at a time — exactly how `play_doom.py` and `shooting_range.py` call
`/decide` — Apple Silicon via MLX is reported *faster* than a cloud Tesla T4, not slower. A
dedicated GPU box mainly pays off at **batch volume**: the T4 benchmark drops to ~7.2ms/question
at a batch of 10, and the M3 Max figures above report 147-395 questions/sec of sustained
throughput. That's a throughput story for serving many concurrent requests (e.g. a production API
with many simultaneous users), not a latency story for one game loop asking one question at a
time.

**Why our own measured latency (~30-70ms) is higher than the 13.4ms benchmark above:** that
figure was measured on an M3 Max — 40 GPU cores, 128GB unified memory. The machine this repo was
tested on is an **M1 Pro with 16GB** — a much smaller chip (fewer GPU cores, far less memory
bandwidth). That gap is expected and is a hardware-generation difference, not a bug. A newer/
bigger Apple Silicon chip (M3/M4 Max or above) would close most of that latency gap.

**But speed and accuracy are two separate axes — don't conflate them.** The hardware only
explains why calls are slower here than the benchmark; it has **no bearing on the 22-33% decision
accuracy** reported above. `laya-typed-decisions-mlx` wasn't trained on Doom-style spatial
descriptions, so it answers them poorly regardless of what chip runs it — an M3 Max, an H100, or
any future hardware would reproduce the same `shoot`-biased wrong answers, just delivered faster.
Better hardware buys you lower latency; it does not buy you a smarter model.

**Two concrete reasons this wouldn't help our games specifically:**
1. **Network hop.** Right now `real_engine.py` calls `laya-mlx` in-process — zero network latency.
   Moving the model to a separate AWS/on-prem machine means every `/decide` call now pays a
   network round-trip on top of inference time. For games calling `/decide` every 1-6 frames,
   that round-trip (even a few ms on a fast LAN, more over the public internet) stacks directly
   onto the latency budget instead of replacing it.
2. **It doesn't touch accuracy.** The 22-33% decision accuracy we measured is a model/training
   mismatch (Doom-style spatial text is out-of-distribution for laya-mlx), not a speed problem.
   A faster or bigger GPU gets you the same wrong answers, just quicker.

**Where dedicated GPU hosting would genuinely help:** a production deployment serving many
concurrent users/requests through the `/decide` API (not a single local game loop) — there,
batching on a GPU server is a legitimate way to cut per-request cost and latency at scale. That's
a different use case than what this repo currently demonstrates.

Sources:
- [Laya MLX ships 13.4 ms typed decisions on Apple Silicon](https://aiweekly.co/alerts/laya-mlx-ships-134-ms-typed-decisions-on-apple-silicon)
- [Convai ships Laya, a 421M ModernBERT decision model, Apache 2.0](https://aiweekly.co/alerts/convai-ships-laya-a-421m-modernbert-decision-model-apache-20)

## Bottom line

For this repo's actual flows (Doom, shooting range), the heuristic backend is the better choice
today — it's faster and more accurate, because it was built specifically for this text. laya-mlx
is valuable for demonstrating the authentic Laya API contract and genuine model inference, but
treat it as a proof-of-concept here, not a drop-in upgrade: it would need either a
larger/fine-tuned checkpoint or task-specific prompting work to match the heuristic's reliability
on this particular game-state vocabulary. Moving it to a dedicated GPU instance would not change
that conclusion — it's a throughput lever for production-scale concurrent traffic, not a fix for
either per-call latency in a single game loop or the underlying accuracy gap.
