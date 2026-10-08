"""Lightweight decision engine simulating Laya's typed-decision model.

No LLM call: uses keyword-overlap scoring against each candidate option's
label (and optional description) to pick the best-fitting typed answer.
This mirrors Laya's "System One" pitch (instant structured decisions)
without needing an actual trained model.
"""
import re
from typing import Literal

from app.schemas import DecisionRequest, EnumOption

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "of", "up", "off", "is",
    "are", "be", "and", "or", "for", "with", "this", "that", "it", "as",
}


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower())) - _STOPWORDS


def _score_option(question_tokens: set[str], option: EnumOption) -> float:
    option_tokens = _tokenize(option.label)
    if option.description:
        option_tokens |= _tokenize(option.description)
    if not option_tokens:
        return 0.0
    overlap = question_tokens & option_tokens
    return len(overlap) / len(option_tokens)


def decide_enum(question: str, options: list[EnumOption]) -> tuple[str, float]:
    q_tokens = _tokenize(question)
    scored = [(opt.label, _score_option(q_tokens, opt)) for opt in options]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    best_label, best_score = scored[0]
    # normalize into a pseudo-confidence in [0.5, 0.99]
    confidence = 0.5 + min(best_score, 1.0) * 0.49
    return best_label, round(confidence, 3)


def decide_bool(question: str) -> tuple[bool, float]:
    tokens = _tokenize(question)
    negative_hits = tokens & _NEGATIVE_WORDS
    positive_hits = tokens & _POSITIVE_WORDS
    if len(negative_hits) > len(positive_hits):
        return False, round(0.55 + 0.4 * min(len(negative_hits), 3) / 3, 3)
    if len(positive_hits) > 0:
        return True, round(0.55 + 0.4 * min(len(positive_hits), 3) / 3, 3)
    return True, 0.5


_POSITIVE_WORDS = {
    "yes", "good", "safe", "approve", "approved", "valid", "correct", "true",
    "allow", "accept", "confirm", "ok", "okay",
}
_NEGATIVE_WORDS = {
    "no", "not", "bad", "unsafe", "reject", "rejected", "invalid",
    "incorrect", "false", "deny", "denied", "never", "cancel", "refuse",
}


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def decide_number(question: str, min_value: float, max_value: float) -> tuple[float, float]:
    numbers = [float(m) for m in _NUMBER_RE.findall(question)]
    if numbers:
        # last number mentioned tends to be the actual answer (e.g. "... this seems like an 8")
        value = min(max(numbers[-1], min_value), max_value)
        return round(value, 3), 0.9
    midpoint = (min_value + max_value) / 2
    return round(midpoint, 3), 0.5
