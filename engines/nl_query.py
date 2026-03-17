"""M17 — Natural Language Query engine wrapper.

Provides a standalone interface for natural-language queries about the HyperSpin
collection, combining the AI engine's NLQueryEngine with LLM detector model
recommendations. Designed for CLI, MCP, and dashboard consumption.
"""
from __future__ import annotations

from typing import Any, Optional

from core.logger import get_logger, audit

log = get_logger("nl_query")


def nl_query(question: str, provider: str | None = None) -> dict[str, Any]:
    """Translate a natural-language question into SQL, execute, and explain.

    Args:
        question: Free-form English question about the collection.
        provider: Optional preferred LLM provider ('ollama', 'lmstudio').

    Returns:
        Dict with question, generated_sql, row_count, results, explanation.
    """
    from engines.ai_engine import get_ai, NLQueryEngine

    try:
        ai = get_ai()
        nlq = NLQueryEngine(ai)
        result = nlq.query(question)
        audit("nl_query", question[:120], {
            "sql": result.get("generated_sql", "")[:200],
            "rows": result.get("row_count", 0),
        })
        return result
    except RuntimeError as exc:
        # No AI provider available
        return {"error": str(exc), "question": question}
    except Exception as exc:
        log.error("NL query failed: %s", exc)
        return {"error": str(exc), "question": question}


def recommend_model_for_task(task: str = "agentic", provider: str = "any") -> dict[str, Any]:
    """Recommend the best local LLM model for a given task.

    Args:
        task: One of 'agentic', 'coding', 'reasoning', 'vision', 'fast', 'general'.
        provider: 'lmstudio', 'ollama', or 'any'.

    Returns:
        Dict with recommended model info or error.
    """
    from engines.llm_detector import recommend_model, scan_lmstudio_models, scan_ollama_models

    try:
        lms = scan_lmstudio_models()
        ollama = scan_ollama_models()
        best = recommend_model(task, provider, lms, ollama)

        if best is None:
            return {"error": "No suitable model found", "task": task, "provider": provider}

        return {
            "task": task,
            "provider": best.provider,
            "model_id": best.api_model_id,
            "name": best.name,
            "family": best.family,
            "size_gb": best.size_gb,
            "quant": best.quant,
            "fits_vram": best.fits_vram,
            "context_native": best.context_window,
            "context_max": best.context_window_max,
            "tags": best.tags,
        }
    except Exception as exc:
        log.error("Model recommendation failed: %s", exc)
        return {"error": str(exc), "task": task}


def full_ai_report() -> dict[str, Any]:
    """Generate a comprehensive AI/LLM status report.

    Returns model inventory, provider status, and per-task recommendations.
    """
    from engines.llm_detector import full_model_report

    try:
        return full_model_report()
    except Exception as exc:
        log.error("AI report failed: %s", exc)
        return {"error": str(exc)}
