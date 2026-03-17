"""LLM Router Engine — Auto-select between LM Studio, Ollama, and VLLM backends.

Provides a unified OpenAI-compatible interface that automatically routes requests
to the best available local LLM backend based on task type, availability, and
configured priority.

Priority chain (configurable):
  1. LM Studio  — default for interactive/single queries (localhost:1234)
  2. Ollama     — fallback, good for embeddings and lightweight tasks (localhost:11434)
  3. VLLM       — high-throughput batch inference (localhost:8000)

Usage:
  from engines.llm_router import LLMRouter
  router = LLMRouter()
  response = router.chat("Describe the MAME emulator in one sentence.")
  response = router.chat("Classify this ROM", task_type="batch")
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("llm_router")


# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    """Task categories that influence backend selection."""
    INTERACTIVE = "interactive"   # Single user query, low latency preferred
    BATCH = "batch"               # Bulk classification/analysis, throughput preferred
    EMBEDDING = "embedding"       # Text embedding generation
    CODING = "coding"             # Code generation / analysis
    AGENT = "agent"               # Agent tool-use / function calling


class ProviderStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    base_url: str
    api_key: str = "not-needed"
    priority: int = 0            # Lower = higher priority
    enabled: bool = True
    timeout_sec: int = 30
    max_retries: int = 2
    preferred_tasks: List[str] = field(default_factory=list)
    models_dir: str = ""
    health_endpoint: str = "/v1/models"
    status: str = ProviderStatus.UNKNOWN
    last_check: float = 0.0
    last_latency_ms: float = 0.0


@dataclass
class RouterConfig:
    """Full router configuration."""
    providers: List[ProviderConfig] = field(default_factory=list)
    default_model: str = ""
    fallback_enabled: bool = True
    health_check_interval_sec: int = 60
    log_routing_decisions: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoutingDecision:
    """Record of a routing decision for observability."""
    timestamp: str = ""
    task_type: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    reason: str = ""
    fallback_used: bool = False
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Default configurations
# ---------------------------------------------------------------------------

DEFAULT_PROVIDERS = [
    ProviderConfig(
        name="lmstudio",
        base_url="http://localhost:1234/v1",
        priority=1,
        preferred_tasks=["interactive", "coding", "agent"],
        models_dir=r"C:\Users\Admin\.lmstudio\models",
        health_endpoint="/v1/models",
    ),
    ProviderConfig(
        name="ollama",
        base_url="http://localhost:11434/v1",
        priority=2,
        preferred_tasks=["interactive", "embedding"],
        models_dir=r"C:\Users\Admin\.ollama\models",
        health_endpoint="/v1/models",
    ),
    ProviderConfig(
        name="vllm",
        base_url="http://localhost:8000/v1",
        priority=3,
        preferred_tasks=["batch"],
        health_endpoint="/v1/models",
    ),
]


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no requests dependency)
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 5) -> Optional[dict]:
    """Simple GET request returning parsed JSON or None."""
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _http_post(url: str, payload: dict, api_key: str = "not-needed",
               timeout: int = 60) -> Optional[dict]:
    """Simple POST request returning parsed JSON or None."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"POST {url} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main Router
# ---------------------------------------------------------------------------

class LLMRouter:
    """Intelligent LLM backend router with health checks and fallback."""

    def __init__(self, config_path: Optional[str] = None,
                 providers: Optional[List[ProviderConfig]] = None):
        self.config = RouterConfig()
        self.routing_log: List[RoutingDecision] = []

        if config_path and Path(config_path).exists():
            self._load_config(config_path)
        elif providers:
            self.config.providers = providers
        else:
            self.config.providers = [ProviderConfig(**asdict(p)) for p in DEFAULT_PROVIDERS]

    # ----- Config persistence -----

    def _load_config(self, path: str):
        """Load router config from YAML or JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.config.default_model = raw.get("default_model", "")
            self.config.fallback_enabled = raw.get("fallback_enabled", True)
            self.config.health_check_interval_sec = raw.get("health_check_interval_sec", 60)
            self.config.log_routing_decisions = raw.get("log_routing_decisions", True)
            self.config.providers = []
            for p in raw.get("providers", []):
                self.config.providers.append(ProviderConfig(**p))
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            self.config.providers = [ProviderConfig(**asdict(p)) for p in DEFAULT_PROVIDERS]

    def save_config(self, path: str):
        """Save current config to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2)
        logger.info(f"Config saved to {path}")

    # ----- Health checks -----

    def check_provider_health(self, provider: ProviderConfig) -> ProviderStatus:
        """Check if a provider is available by hitting its health endpoint."""
        if not provider.enabled:
            provider.status = ProviderStatus.UNAVAILABLE
            return ProviderStatus.UNAVAILABLE

        url = provider.base_url.rstrip("/") + provider.health_endpoint
        start = time.time()
        result = _http_get(url, timeout=min(provider.timeout_sec, 10))
        elapsed_ms = (time.time() - start) * 1000

        provider.last_check = time.time()
        provider.last_latency_ms = round(elapsed_ms, 1)

        if result is not None:
            provider.status = ProviderStatus.AVAILABLE
            logger.debug(f"{provider.name}: available ({elapsed_ms:.0f}ms)")
            return ProviderStatus.AVAILABLE
        else:
            provider.status = ProviderStatus.UNAVAILABLE
            logger.debug(f"{provider.name}: unavailable")
            return ProviderStatus.UNAVAILABLE

    def check_all_health(self) -> Dict[str, str]:
        """Check health of all providers. Returns {name: status}."""
        results = {}
        for p in self.config.providers:
            status = self.check_provider_health(p)
            results[p.name] = status.value
        return results

    def _should_recheck(self, provider: ProviderConfig) -> bool:
        """Determine if a provider health needs rechecking."""
        if provider.status == ProviderStatus.UNKNOWN:
            return True
        elapsed = time.time() - provider.last_check
        return elapsed > self.config.health_check_interval_sec

    # ----- Model listing -----

    def list_models(self, provider_name: Optional[str] = None) -> Dict[str, List[str]]:
        """List available models from providers."""
        results = {}
        targets = self.config.providers
        if provider_name:
            targets = [p for p in targets if p.name == provider_name]

        for p in targets:
            if p.status == ProviderStatus.UNAVAILABLE:
                results[p.name] = []
                continue
            url = p.base_url.rstrip("/") + "/v1/models"
            data = _http_get(url, timeout=10)
            if data and "data" in data:
                models = [m.get("id", "unknown") for m in data["data"]]
                results[p.name] = models
            else:
                results[p.name] = []
        return results

    # ----- Routing logic -----

    def select_provider(self, task_type: str = TaskType.INTERACTIVE,
                        preferred_provider: Optional[str] = None) -> Optional[ProviderConfig]:
        """Select the best available provider for a given task type.

        Selection order:
          1. Explicit preferred_provider (if available)
          2. Provider whose preferred_tasks includes task_type (lowest priority number)
          3. Any available provider (lowest priority number)
        """
        # Refresh stale health checks
        for p in self.config.providers:
            if self._should_recheck(p):
                self.check_provider_health(p)

        available = [p for p in self.config.providers
                     if p.enabled and p.status == ProviderStatus.AVAILABLE]

        if not available:
            logger.warning("No LLM providers available")
            return None

        # 1. Explicit preference
        if preferred_provider:
            match = [p for p in available if p.name == preferred_provider]
            if match:
                return match[0]

        # 2. Task-matched provider
        task_matched = [p for p in available if task_type in p.preferred_tasks]
        if task_matched:
            task_matched.sort(key=lambda p: p.priority)
            return task_matched[0]

        # 3. Fallback to any available, sorted by priority
        available.sort(key=lambda p: p.priority)
        return available[0]

    def _log_decision(self, decision: RoutingDecision):
        """Log a routing decision for observability."""
        self.routing_log.append(decision)
        if self.config.log_routing_decisions:
            logger.info(
                f"Routed [{decision.task_type}] → {decision.selected_provider}"
                f" (model={decision.selected_model}, reason={decision.reason},"
                f" fallback={decision.fallback_used}, {decision.latency_ms}ms)"
            )

    # ----- Chat completions -----

    def chat(self, prompt: str, model: Optional[str] = None,
             task_type: str = TaskType.INTERACTIVE,
             preferred_provider: Optional[str] = None,
             system_prompt: str = "You are a helpful assistant.",
             temperature: float = 0.7,
             max_tokens: int = 2048,
             messages: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
        """Send a chat completion request to the best available provider.

        Args:
            prompt: User message (ignored if messages is provided).
            model: Specific model ID. If None, uses provider default or first available.
            task_type: Task category for routing.
            preferred_provider: Force a specific provider if available.
            system_prompt: System message for context.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.
            messages: Full message list (overrides prompt/system_prompt).

        Returns:
            Parsed API response dict, or None on failure.
        """
        provider = self.select_provider(task_type, preferred_provider)
        fallback_used = False

        if provider is None:
            return None

        # Build messages
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

        # Resolve model
        if not model:
            model = self.config.default_model or ""

        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if model:
            payload["model"] = model

        # Attempt request with fallback
        start = time.time()
        url = provider.base_url.rstrip("/") + "/chat/completions"
        result = _http_post(url, payload, api_key=provider.api_key,
                            timeout=provider.timeout_sec)

        if result is None and self.config.fallback_enabled:
            # Try next available provider
            others = [p for p in self.config.providers
                      if p.name != provider.name and p.enabled
                      and p.status == ProviderStatus.AVAILABLE]
            others.sort(key=lambda p: p.priority)
            for fallback in others:
                url = fallback.base_url.rstrip("/") + "/chat/completions"
                result = _http_post(url, payload, api_key=fallback.api_key,
                                    timeout=fallback.timeout_sec)
                if result is not None:
                    provider = fallback
                    fallback_used = True
                    break

        elapsed_ms = round((time.time() - start) * 1000, 1)

        # Log decision
        decision = RoutingDecision(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task_type=task_type,
            selected_provider=provider.name,
            selected_model=model or "(default)",
            reason="task_match" if not fallback_used else "fallback",
            fallback_used=fallback_used,
            latency_ms=elapsed_ms,
        )
        self._log_decision(decision)

        return result

    # ----- Embeddings -----

    def embed(self, text: str, model: Optional[str] = None,
              preferred_provider: Optional[str] = None) -> Optional[List[float]]:
        """Generate embeddings using the best available provider.

        Returns the embedding vector or None on failure.
        """
        provider = self.select_provider(TaskType.EMBEDDING, preferred_provider)
        if provider is None:
            return None

        payload = {
            "input": text,
        }
        if model:
            payload["model"] = model

        url = provider.base_url.rstrip("/") + "/embeddings"
        result = _http_post(url, payload, api_key=provider.api_key,
                            timeout=provider.timeout_sec)

        if result and "data" in result and len(result["data"]) > 0:
            return result["data"][0].get("embedding")
        return None

    # ----- Convenience -----

    def quick_classify(self, text: str, categories: List[str],
                       model: Optional[str] = None) -> Optional[str]:
        """Classify text into one of the given categories using the LLM."""
        cats = ", ".join(categories)
        prompt = (
            f"Classify the following text into exactly one of these categories: {cats}\n\n"
            f"Text: {text}\n\n"
            f"Respond with ONLY the category name, nothing else."
        )
        result = self.chat(prompt, model=model, task_type=TaskType.BATCH,
                           temperature=0.1, max_tokens=50)
        if result and "choices" in result:
            content = result["choices"][0].get("message", {}).get("content", "").strip()
            # Fuzzy match to closest category
            content_lower = content.lower()
            for cat in categories:
                if cat.lower() in content_lower:
                    return cat
            return content
        return None

    # ----- Status & Observability -----

    def status(self) -> dict:
        """Get current router status overview."""
        self.check_all_health()
        return {
            "providers": [
                {
                    "name": p.name,
                    "base_url": p.base_url,
                    "enabled": p.enabled,
                    "status": p.status,
                    "priority": p.priority,
                    "preferred_tasks": p.preferred_tasks,
                    "latency_ms": p.last_latency_ms,
                }
                for p in self.config.providers
            ],
            "default_model": self.config.default_model,
            "fallback_enabled": self.config.fallback_enabled,
            "routing_log_size": len(self.routing_log),
        }

    def get_routing_log(self, limit: int = 50) -> List[dict]:
        """Return recent routing decisions."""
        return [asdict(d) for d in self.routing_log[-limit:]]

    def summary(self) -> str:
        """Human-readable status summary."""
        lines = ["LLM Router Status:"]
        for p in self.config.providers:
            if self._should_recheck(p):
                self.check_provider_health(p)
            icon = "✅" if p.status == ProviderStatus.AVAILABLE else "❌"
            lines.append(
                f"  {icon} {p.name} (priority={p.priority}, "
                f"tasks={p.preferred_tasks}, {p.last_latency_ms}ms)"
            )
        lines.append(f"  Fallback: {'enabled' if self.config.fallback_enabled else 'disabled'}")
        lines.append(f"  Routing log entries: {len(self.routing_log)}")
        return "\n".join(lines)
