"""Tests for the LLM Router Engine (engines/llm_router.py).

Covers:
  - Provider configuration and defaults
  - Health check logic
  - Provider selection by task type
  - Fallback behavior
  - Config save/load round-trip
  - Routing log observability
  - Status and summary output
  - Chat/embed method structure (mocked HTTP)
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engines.llm_router import (
    DEFAULT_PROVIDERS,
    LLMRouter,
    ProviderConfig,
    ProviderStatus,
    RouterConfig,
    RoutingDecision,
    TaskType,
    _http_get,
    _http_post,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_providers():
    """Three providers with different priorities and task preferences."""
    return [
        ProviderConfig(
            name="lmstudio",
            base_url="http://localhost:1234/v1",
            priority=1,
            preferred_tasks=["interactive", "coding", "agent"],
            status=ProviderStatus.AVAILABLE,
            last_check=time.time(),
        ),
        ProviderConfig(
            name="ollama",
            base_url="http://localhost:11434/v1",
            priority=2,
            preferred_tasks=["interactive", "embedding"],
            status=ProviderStatus.AVAILABLE,
            last_check=time.time(),
        ),
        ProviderConfig(
            name="vllm",
            base_url="http://localhost:8000/v1",
            priority=3,
            preferred_tasks=["batch"],
            status=ProviderStatus.AVAILABLE,
            last_check=time.time(),
        ),
    ]


@pytest.fixture
def router(mock_providers):
    """Router with pre-configured mock providers."""
    return LLMRouter(providers=mock_providers)


@pytest.fixture
def router_with_unavailable(mock_providers):
    """Router where lmstudio is unavailable."""
    mock_providers[0].status = ProviderStatus.UNAVAILABLE
    return LLMRouter(providers=mock_providers)


# ---------------------------------------------------------------------------
# Test: Default Configuration
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    def test_default_providers_exist(self):
        assert len(DEFAULT_PROVIDERS) == 3

    def test_default_provider_names(self):
        names = {p.name for p in DEFAULT_PROVIDERS}
        assert names == {"lmstudio", "ollama", "vllm"}

    def test_default_priorities(self):
        for p in DEFAULT_PROVIDERS:
            if p.name == "lmstudio":
                assert p.priority == 1
            elif p.name == "ollama":
                assert p.priority == 2
            elif p.name == "vllm":
                assert p.priority == 3

    def test_default_router_has_three_providers(self):
        # Will use defaults since no config file and no providers arg
        router = LLMRouter()
        assert len(router.config.providers) == 3


# ---------------------------------------------------------------------------
# Test: Provider Selection
# ---------------------------------------------------------------------------

class TestProviderSelection:
    def test_interactive_selects_lmstudio(self, router):
        provider = router.select_provider(TaskType.INTERACTIVE)
        assert provider is not None
        assert provider.name == "lmstudio"

    def test_batch_selects_vllm(self, router):
        provider = router.select_provider(TaskType.BATCH)
        assert provider is not None
        assert provider.name == "vllm"

    def test_embedding_selects_ollama(self, router):
        provider = router.select_provider(TaskType.EMBEDDING)
        assert provider is not None
        assert provider.name == "ollama"

    def test_coding_selects_lmstudio(self, router):
        provider = router.select_provider(TaskType.CODING)
        assert provider is not None
        assert provider.name == "lmstudio"

    def test_agent_selects_lmstudio(self, router):
        provider = router.select_provider(TaskType.AGENT)
        assert provider is not None
        assert provider.name == "lmstudio"

    def test_preferred_provider_override(self, router):
        provider = router.select_provider(TaskType.INTERACTIVE, preferred_provider="vllm")
        assert provider is not None
        assert provider.name == "vllm"

    def test_preferred_unavailable_falls_back(self, router):
        # Make vllm unavailable
        for p in router.config.providers:
            if p.name == "vllm":
                p.status = ProviderStatus.UNAVAILABLE
        provider = router.select_provider(TaskType.INTERACTIVE, preferred_provider="vllm")
        # Should fall back to lmstudio (task match)
        assert provider is not None
        assert provider.name == "lmstudio"

    def test_no_available_returns_none(self, router):
        for p in router.config.providers:
            p.status = ProviderStatus.UNAVAILABLE
        provider = router.select_provider(TaskType.INTERACTIVE)
        assert provider is None


# ---------------------------------------------------------------------------
# Test: Fallback When Primary Unavailable
# ---------------------------------------------------------------------------

class TestFallback:
    def test_fallback_to_ollama_for_interactive(self, router_with_unavailable):
        provider = router_with_unavailable.select_provider(TaskType.INTERACTIVE)
        assert provider is not None
        assert provider.name == "ollama"

    def test_fallback_for_coding(self, router_with_unavailable):
        provider = router_with_unavailable.select_provider(TaskType.CODING)
        # No coding-preferred provider other than lmstudio (unavailable)
        # Falls back to lowest-priority available
        assert provider is not None
        assert provider.name in ("ollama", "vllm")

    def test_all_unavailable_returns_none(self, router):
        for p in router.config.providers:
            p.status = ProviderStatus.UNAVAILABLE
        assert router.select_provider(TaskType.INTERACTIVE) is None


# ---------------------------------------------------------------------------
# Test: Health Checks
# ---------------------------------------------------------------------------

class TestHealthChecks:
    @patch("engines.llm_router._http_get")
    def test_health_check_available(self, mock_get, router):
        mock_get.return_value = {"data": [{"id": "model1"}]}
        p = router.config.providers[0]
        status = router.check_provider_health(p)
        assert status == ProviderStatus.AVAILABLE
        assert p.last_latency_ms >= 0

    @patch("engines.llm_router._http_get")
    def test_health_check_unavailable(self, mock_get, router):
        mock_get.return_value = None
        p = router.config.providers[0]
        status = router.check_provider_health(p)
        assert status == ProviderStatus.UNAVAILABLE

    def test_disabled_provider_always_unavailable(self, router):
        p = router.config.providers[0]
        p.enabled = False
        status = router.check_provider_health(p)
        assert status == ProviderStatus.UNAVAILABLE

    @patch("engines.llm_router._http_get")
    def test_check_all_health(self, mock_get, router):
        mock_get.return_value = {"data": []}
        results = router.check_all_health()
        assert len(results) == 3
        for name, status in results.items():
            assert status == "available"

    def test_should_recheck_unknown(self, router):
        p = router.config.providers[0]
        p.status = ProviderStatus.UNKNOWN
        assert router._should_recheck(p) is True

    def test_should_not_recheck_recent(self, router):
        p = router.config.providers[0]
        p.status = ProviderStatus.AVAILABLE
        p.last_check = time.time()
        assert router._should_recheck(p) is False

    def test_should_recheck_stale(self, router):
        p = router.config.providers[0]
        p.status = ProviderStatus.AVAILABLE
        p.last_check = time.time() - 120  # 2 minutes ago
        router.config.health_check_interval_sec = 60
        assert router._should_recheck(p) is True


# ---------------------------------------------------------------------------
# Test: Chat Method
# ---------------------------------------------------------------------------

class TestChat:
    @patch("engines.llm_router._http_post")
    def test_chat_success(self, mock_post, router):
        mock_post.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}}]
        }
        result = router.chat("Say hello")
        assert result is not None
        assert "choices" in result
        assert result["choices"][0]["message"]["content"] == "Hello!"

    @patch("engines.llm_router._http_post")
    def test_chat_records_routing_decision(self, mock_post, router):
        mock_post.return_value = {"choices": [{"message": {"content": "ok"}}]}
        router.chat("Test", task_type=TaskType.CODING)
        assert len(router.routing_log) == 1
        assert router.routing_log[0].task_type == "coding"
        assert router.routing_log[0].selected_provider == "lmstudio"

    @patch("engines.llm_router._http_post")
    def test_chat_fallback_on_failure(self, mock_post, router):
        # First call fails, second succeeds
        mock_post.side_effect = [None, {"choices": [{"message": {"content": "fallback"}}]}]
        result = router.chat("Test")
        assert result is not None
        assert len(router.routing_log) == 1
        assert router.routing_log[0].fallback_used is True

    @patch("engines.llm_router._http_post")
    def test_chat_all_fail_returns_none(self, mock_post, router):
        mock_post.return_value = None
        result = router.chat("Test")
        assert result is None

    @patch("engines.llm_router._http_post")
    def test_chat_with_custom_messages(self, mock_post, router):
        mock_post.return_value = {"choices": [{"message": {"content": "custom"}}]}
        msgs = [{"role": "user", "content": "Custom message"}]
        result = router.chat("ignored", messages=msgs)
        assert result is not None
        # Verify the payload used the custom messages
        call_args = mock_post.call_args
        payload = call_args[0][1]
        assert payload["messages"] == msgs

    def test_chat_no_providers_available(self, router):
        for p in router.config.providers:
            p.status = ProviderStatus.UNAVAILABLE
        result = router.chat("Test")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Embed Method
# ---------------------------------------------------------------------------

class TestEmbed:
    @patch("engines.llm_router._http_post")
    def test_embed_success(self, mock_post, router):
        mock_post.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        result = router.embed("test text")
        assert result == [0.1, 0.2, 0.3]

    @patch("engines.llm_router._http_post")
    def test_embed_failure(self, mock_post, router):
        mock_post.return_value = None
        result = router.embed("test text")
        assert result is None

    def test_embed_no_providers(self, router):
        for p in router.config.providers:
            p.status = ProviderStatus.UNAVAILABLE
        result = router.embed("test")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Quick Classify
# ---------------------------------------------------------------------------

class TestQuickClassify:
    @patch("engines.llm_router._http_post")
    def test_classify_returns_matching_category(self, mock_post, router):
        mock_post.return_value = {
            "choices": [{"message": {"content": "action"}}]
        }
        result = router.quick_classify("A fast-paced shooting game", ["action", "puzzle", "rpg"])
        assert result == "action"

    @patch("engines.llm_router._http_post")
    def test_classify_fuzzy_match(self, mock_post, router):
        mock_post.return_value = {
            "choices": [{"message": {"content": "It's an RPG game"}}]
        }
        result = router.quick_classify("A fantasy adventure", ["action", "puzzle", "rpg"])
        assert result == "rpg"

    @patch("engines.llm_router._http_post")
    def test_classify_failure_returns_none(self, mock_post, router):
        mock_post.return_value = None
        result = router.quick_classify("Test", ["a", "b"])
        assert result is None


# ---------------------------------------------------------------------------
# Test: Config Persistence
# ---------------------------------------------------------------------------

class TestConfigPersistence:
    def test_save_and_load_roundtrip(self, router, tmp_path):
        config_path = str(tmp_path / "llm_config.json")
        router.config.default_model = "test-model"
        router.save_config(config_path)

        new_router = LLMRouter(config_path=config_path)
        assert new_router.config.default_model == "test-model"
        assert len(new_router.config.providers) == 3
        assert new_router.config.providers[0].name == "lmstudio"

    def test_save_creates_valid_json(self, router, tmp_path):
        config_path = str(tmp_path / "llm_config.json")
        router.save_config(config_path)

        with open(config_path, "r") as f:
            data = json.load(f)
        assert "providers" in data
        assert "fallback_enabled" in data

    def test_load_nonexistent_uses_defaults(self):
        router = LLMRouter(config_path="nonexistent_config.json")
        assert len(router.config.providers) == 3


# ---------------------------------------------------------------------------
# Test: Status & Observability
# ---------------------------------------------------------------------------

class TestStatusObservability:
    @patch("engines.llm_router._http_get")
    def test_status_returns_provider_info(self, mock_get, router):
        mock_get.return_value = {"data": []}
        status = router.status()
        assert "providers" in status
        assert len(status["providers"]) == 3
        assert "default_model" in status
        assert "fallback_enabled" in status

    def test_routing_log_empty_initially(self, router):
        assert len(router.get_routing_log()) == 0

    @patch("engines.llm_router._http_post")
    def test_routing_log_grows(self, mock_post, router):
        mock_post.return_value = {"choices": [{"message": {"content": "ok"}}]}
        router.chat("Test 1")
        router.chat("Test 2")
        log = router.get_routing_log()
        assert len(log) == 2

    @patch("engines.llm_router._http_post")
    def test_routing_log_limit(self, mock_post, router):
        mock_post.return_value = {"choices": [{"message": {"content": "ok"}}]}
        for i in range(10):
            router.chat(f"Test {i}")
        log = router.get_routing_log(limit=5)
        assert len(log) == 5

    def test_summary_string(self, router):
        summary = router.summary()
        assert "LLM Router Status:" in summary
        assert "lmstudio" in summary
        assert "ollama" in summary
        assert "vllm" in summary


# ---------------------------------------------------------------------------
# Test: Model Listing
# ---------------------------------------------------------------------------

class TestModelListing:
    @patch("engines.llm_router._http_get")
    def test_list_models_success(self, mock_get, router):
        mock_get.return_value = {
            "data": [{"id": "model-a"}, {"id": "model-b"}]
        }
        models = router.list_models("lmstudio")
        assert "lmstudio" in models
        assert models["lmstudio"] == ["model-a", "model-b"]

    @patch("engines.llm_router._http_get")
    def test_list_models_failure(self, mock_get, router):
        mock_get.return_value = None
        models = router.list_models("lmstudio")
        assert models["lmstudio"] == []

    def test_list_models_unavailable_provider(self, router):
        router.config.providers[0].status = ProviderStatus.UNAVAILABLE
        models = router.list_models("lmstudio")
        assert models["lmstudio"] == []


# ---------------------------------------------------------------------------
# Test: TaskType Enum
# ---------------------------------------------------------------------------

class TestTaskType:
    def test_task_types_are_strings(self):
        assert TaskType.INTERACTIVE == "interactive"
        assert TaskType.BATCH == "batch"
        assert TaskType.EMBEDDING == "embedding"
        assert TaskType.CODING == "coding"
        assert TaskType.AGENT == "agent"

    def test_task_type_in_preferred(self):
        p = ProviderConfig(name="test", base_url="http://test",
                           preferred_tasks=["interactive", "batch"])
        assert "interactive" in p.preferred_tasks
        assert "embedding" not in p.preferred_tasks
