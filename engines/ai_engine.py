"""AI integration layer — Ollama, LM Studio, vLLM with auto-detection and fallback."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("ai_engine")


# ---------------------------------------------------------------------------
# Provider clients
# ---------------------------------------------------------------------------

class LLMProvider:
    """Base class for LLM API providers."""

    def __init__(self, name: str, base_url: str, default_model: str, timeout: int = 120):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if the provider API is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/", timeout=5)
            self._available = resp.status_code < 500
            return self._available
        except Exception:
            self._available = False
            return False

    def chat(self, messages: list[dict[str, str]], model: str | None = None, **kwargs) -> dict[str, Any]:
        raise NotImplementedError

    def generate(self, prompt: str, model: str | None = None, **kwargs) -> str:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Ollama API client."""

    def __init__(self):
        cfg = cfg_get("ai.ollama", {})
        super().__init__(
            name="ollama",
            base_url=cfg.get("base_url", "http://localhost:11434"),
            default_model=cfg.get("default_model", "llama3.1:8b"),
            timeout=cfg.get("timeout", 120),
        )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            self._available = resp.status_code == 200
            return self._available
        except Exception:
            self._available = False
            return False

    def list_models(self) -> list[str]:
        """List available models in Ollama."""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            log.warning("Cannot list Ollama models: %s", exc)
        return []

    def chat(self, messages: list[dict[str, str]], model: str | None = None, **kwargs) -> dict[str, Any]:
        model = model or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        resp = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data.get("message", {}).get("content", ""),
            "model": model,
            "provider": self.name,
            "total_duration": data.get("total_duration"),
            "eval_count": data.get("eval_count"),
        }

    def generate(self, prompt: str, model: str | None = None, **kwargs) -> str:
        model = model or self.default_model
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            **kwargs,
        }
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


class OpenAICompatibleProvider(LLMProvider):
    """Client for OpenAI-compatible APIs (LM Studio, vLLM)."""

    def __init__(self, name: str, config_key: str):
        cfg = cfg_get(f"ai.{config_key}", {})
        super().__init__(
            name=name,
            base_url=cfg.get("base_url", "http://localhost:1234/v1"),
            default_model=cfg.get("default_model", "auto"),
            timeout=cfg.get("timeout", 120),
        )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5)
            self._available = resp.status_code == 200
            return self._available
        except Exception:
            self._available = False
            return False

    def list_models(self) -> list[str]:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as exc:
            log.warning("Cannot list %s models: %s", self.name, exc)
        return []

    def chat(self, messages: list[dict[str, str]], model: str | None = None, **kwargs) -> dict[str, Any]:
        model = model or self.default_model
        if model == "auto":
            models = self.list_models()
            model = models[0] if models else "default"

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        return {
            "content": content,
            "model": data.get("model", model),
            "provider": self.name,
            "usage": data.get("usage"),
        }

    def generate(self, prompt: str, model: str | None = None, **kwargs) -> str:
        result = self.chat([{"role": "user", "content": prompt}], model=model, **kwargs)
        return result.get("content", "")


# ---------------------------------------------------------------------------
# AI Engine (unified interface with fallback)
# ---------------------------------------------------------------------------

class AIEngine:
    """Unified AI interface with provider auto-detection and fallback chain."""

    def __init__(self):
        self.providers: dict[str, LLMProvider] = {}
        self.priority: list[str] = cfg_get("ai.provider_priority", ["ollama", "lmstudio", "vllm"])
        self.session_id = str(uuid.uuid4())[:8]
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize configured providers."""
        if cfg_get("ai.ollama.enabled", True):
            self.providers["ollama"] = OllamaProvider()
        if cfg_get("ai.lmstudio.enabled", True):
            self.providers["lmstudio"] = OpenAICompatibleProvider("lmstudio", "lmstudio")
        if cfg_get("ai.vllm.enabled", False):
            self.providers["vllm"] = OpenAICompatibleProvider("vllm", "vllm")

    def detect_available(self) -> dict[str, bool]:
        """Check which providers are currently available."""
        status = {}
        for name, provider in self.providers.items():
            status[name] = provider.is_available()
            if status[name]:
                log.info("AI provider available: %s at %s", name, provider.base_url)
            else:
                log.debug("AI provider unavailable: %s", name)
        return status

    def _get_provider(self, preferred: str | None = None) -> LLMProvider:
        """Get the best available provider based on priority."""
        if preferred and preferred in self.providers:
            p = self.providers[preferred]
            if p.is_available():
                return p

        for name in self.priority:
            if name in self.providers and self.providers[name].is_available():
                return self.providers[name]

        raise RuntimeError("No AI provider available. Start Ollama, LM Studio, or vLLM.")

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        provider: str | None = None,
        system_prompt: str | None = None,
        save_to_memory: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """Send a chat request with automatic fallback."""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        p = self._get_provider(provider)
        log.info("Chat request via %s (model=%s)", p.name, model or p.default_model)

        result = p.chat(messages, model=model, **kwargs)

        if save_to_memory:
            self._save_conversation(messages, result)

        return result

    def ask(
        self,
        question: str,
        context: str = "",
        provider: str | None = None,
        **kwargs,
    ) -> str:
        """Simple question → answer interface."""
        system = (
            "You are HyperSpin Toolkit AI Assistant. You help manage a large "
            "arcade ROM collection with 170+ systems, 160+ emulators, and "
            "HyperSpin/RocketLauncher frontend. Be concise and technical."
        )
        if context:
            system += f"\n\nContext:\n{context}"

        messages = [{"role": "user", "content": question}]
        result = self.chat(messages, provider=provider, system_prompt=system, **kwargs)
        return result.get("content", "")

    def analyze_collection(self, audit_summary: dict[str, Any]) -> str:
        """Use AI to analyze collection health and provide recommendations."""
        prompt = f"""Analyze this HyperSpin arcade collection audit summary and provide:
1. Overall health assessment
2. Top 5 issues to fix
3. Recommendations for improvement
4. Notable statistics

Audit Summary:
{json.dumps(audit_summary, indent=2, default=str)}"""

        return self.ask(prompt)

    def identify_rom(self, filename: str, system: str = "") -> str:
        """Use AI to identify a ROM from its filename."""
        ctx = f"System: {system}" if system else ""
        return self.ask(
            f"Identify this ROM file and provide game name, region, version info: {filename}",
            context=ctx
        )

    def troubleshoot(self, issue_description: str, error_log: str = "") -> str:
        """Use AI to troubleshoot an issue."""
        prompt = f"Issue: {issue_description}"
        if error_log:
            prompt += f"\n\nError log:\n{error_log[:2000]}"
        return self.ask(prompt)

    def _save_conversation(self, messages: list[dict[str, str]], result: dict[str, Any]) -> None:
        """Save conversation to AI memory table."""
        try:
            for msg in messages:
                db.insert("ai_memory", {
                    "session_id": self.session_id,
                    "role": msg["role"],
                    "content": msg["content"],
                    "model": result.get("model"),
                    "provider": result.get("provider"),
                })
            db.insert("ai_memory", {
                "session_id": self.session_id,
                "role": "assistant",
                "content": result.get("content", ""),
                "model": result.get("model"),
                "provider": result.get("provider"),
            })
        except Exception as exc:
            log.debug("Failed to save AI memory: %s", exc)


# ---------------------------------------------------------------------------
# Natural language query engine
# ---------------------------------------------------------------------------

class NLQueryEngine:
    """Translates natural language questions about the collection into SQL queries."""

    SCHEMA_CONTEXT = """
Database tables:
- systems: id, name, folder_name, rom_count, media_count, health_score, last_audit
- roms: id, system_id, filename, filepath, size_bytes, extension, sha256, status
- emulators: id, name, folder_name, exe_path, version, is_healthy
- media_assets: id, system_id, game_name, media_type, filepath, size_bytes, status
- backups: id, backup_type, target, backup_path, size_bytes, file_count, status
- update_history: id, program_name, old_version, new_version, status
"""

    def __init__(self, ai: AIEngine):
        self.ai = ai

    def query(self, question: str) -> dict[str, Any]:
        """Translate a natural language question to SQL, execute, and explain results."""
        # Generate SQL
        sql_prompt = f"""{self.SCHEMA_CONTEXT}

Translate this question to a SQLite query. Return ONLY the SQL, no explanation:
Question: {question}"""

        sql = self.ai.ask(sql_prompt).strip()
        # Clean up — remove markdown code blocks if present
        if sql.startswith("```"):
            lines = sql.split("\n")
            sql = "\n".join(lines[1:-1]) if len(lines) > 2 else sql

        # Safety check — only allow SELECT queries
        sql_upper = sql.upper().strip()
        if not sql_upper.startswith("SELECT"):
            return {"error": "Only SELECT queries are allowed", "generated_sql": sql}

        # Execute
        try:
            results = db.execute(sql)
        except Exception as exc:
            return {"error": str(exc), "generated_sql": sql}

        # Explain results
        explain_prompt = f"""Question: {question}
SQL: {sql}
Results ({len(results)} rows): {json.dumps(results[:20], default=str)}

Provide a clear, concise answer to the question based on these results."""

        explanation = self.ai.ask(explain_prompt)

        return {
            "question": question,
            "generated_sql": sql,
            "row_count": len(results),
            "results": results[:100],
            "explanation": explanation,
        }


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_engine: AIEngine | None = None


def get_ai() -> AIEngine:
    """Get or create the singleton AI engine."""
    global _engine
    if _engine is None:
        _engine = AIEngine()
    return _engine


def get_nl_query() -> NLQueryEngine:
    """Get a natural language query engine."""
    return NLQueryEngine(get_ai())
