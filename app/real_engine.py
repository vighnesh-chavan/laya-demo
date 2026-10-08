"""Adapter over the real Laya model (laya-mlx), exposing the same
function signatures as engine.py so main.py can switch backends freely.

Maps our bool/enum/number schema onto Laya's native noul/choice/score
question types.
"""
import os

from app.schemas import EnumOption

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        import laya_mlx

        model = os.getenv("LAYA_MODEL", "aac6fef/laya-typed-decisions-mlx")
        _agent = laya_mlx.load(model)
    return _agent


def decide_bool(question: str) -> tuple[bool, float]:
    agent = _get_agent()
    result = agent.predict(
        question,
        {"decision": {"type": "noul", "instructions": question, "criteria": None}},
    )
    noul_value = result["answers"]["decision"]["noul"]
    answer = noul_value >= 0.5
    confidence = noul_value if answer else 1 - noul_value
    return answer, round(confidence, 3)


def decide_enum(question: str, options: list[EnumOption]) -> tuple[str, float]:
    agent = _get_agent()
    criteria = {opt.label: (opt.description or opt.label) for opt in options}
    result = agent.predict(
        question,
        {"decision": {"type": "choice", "instructions": question, "criteria": criteria}},
    )
    answer_block = result["answers"]["decision"]
    return answer_block["choice"], round(answer_block["confidence"], 3)


def decide_number(question: str, min_value: float, max_value: float) -> tuple[float, float]:
    agent = _get_agent()
    span = max_value - min_value
    labels = ["very low", "low", "medium", "high", "very high"]
    criteria = [f"{label} (around {min_value + span * i / 4:.2f})" for i, label in enumerate(labels)]
    result = agent.predict(
        question,
        {"decision": {"type": "score", "instructions": question, "criteria": criteria}},
    )
    answer_block = result["answers"]["decision"]
    score = answer_block["score"]  # in [0, 4]
    value = min_value + (score / 4) * span
    return round(value, 3), round(answer_block["confidence"], 3)
