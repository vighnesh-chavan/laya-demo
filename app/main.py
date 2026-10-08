import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from app import engine, real_engine
from app.schemas import DecisionRequest, DecisionResponse

app = FastAPI(
    title="Laya",
    description="Open-source Jev alternative: instant typed decisions instead of text generation.",
    version="0.1.0",
)

BACKEND = os.getenv("LAYA_BACKEND", "heuristic")
active_engine = real_engine if BACKEND == "laya-mlx" else engine


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/decide", response_model=DecisionResponse)
def decide(request: DecisionRequest) -> DecisionResponse:
    start = time.perf_counter()

    if request.type == "bool":
        answer, confidence = active_engine.decide_bool(request.question)
    elif request.type == "enum":
        answer, confidence = active_engine.decide_enum(request.question, request.options)
    else:
        answer, confidence = active_engine.decide_number(
            request.question, request.min_value, request.max_value
        )

    latency_ms = (time.perf_counter() - start) * 1000
    return DecisionResponse(
        answer=answer,
        type=request.type,
        confidence=confidence,
        latency_ms=round(latency_ms, 3),
    )
