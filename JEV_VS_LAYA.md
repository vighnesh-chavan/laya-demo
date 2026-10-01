# Jev vs Laya

| | **Jev** (TypeSafe AI) | **Laya** (this project) |
|---|---|---|
| License | Closed, commercial API | Apache 2.0, open source |
| Cost | Pay-per-token — $0.042 / 1M input tokens (output unmetered) | $0 — free, self-hosted |
| Deployment | Cloud API only, vendor-hosted | Runs anywhere: laptop, on-prem, private cloud |
| Data privacy | Requests leave your infra to TypeSafe's servers | Fully local — no data ever leaves your machine |
| Latency | ~ms-scale, but network round-trip to vendor adds overhead | Sub-millisecond in-process decisions (no network hop) |
| Customization | Fixed model, no fine-tuning/inspection | Fully hackable — swap in your own scoring/embedding logic |
| Vendor lock-in | Yes — tied to TypeSafe's pricing & roadmap | None — you own the code and the model |
| Rate limits / quotas | Set by vendor plan | None — limited only by your own hardware |
| Transparency | Black-box decisions | Fully auditable Python logic (`app/engine.py`) |
| Language support | 100+ languages (claimed) | Depends on your tokenizer/scoring choice; easy to extend |
| Scaling cost | Cost grows linearly with usage/tokens | Free to scale horizontally — just run more instances |

## Why Laya wins for most use cases

- **No metering anxiety** — typed decisions (bool/enum/number) happen constantly in production pipelines (routing, moderation, triage); paying per token for these adds up fast at scale. Laya has no per-call cost.
- **Data never leaves your infra** — for regulated or sensitive workloads, sending every decision request to a third-party API is a compliance risk. Laya runs entirely in your own FastAPI service.
- **No blackbox risk** — Jev's decision logic is proprietary; Laya's is plain, readable, and modifiable code, so you can audit *why* it decided what it decided.
- **No vendor dependency** — if TypeSafe changes pricing, deprecates the API, or has an outage, dependent systems break. Laya has no external dependency once deployed.
- **Instant, network-free latency** — Laya's decisions are computed in-process, avoiding the network round-trip inherent to any hosted API, including Jev.

## Where Jev may still have an edge

- Backed by an actual trained "System One" model — likely higher raw accuracy on ambiguous natural-language decisions than Laya's keyword-overlap heuristic engine used in this demo.
- Managed infrastructure — no need to host, scale, or maintain servers yourself.

## Bottom line

Jev trades cost, data control, and transparency for a managed, possibly more accurate model. Laya trades a small amount of out-of-the-box accuracy (in this demo implementation) for zero cost, full data ownership, and complete control over the decision logic.
