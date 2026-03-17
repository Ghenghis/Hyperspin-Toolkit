"""LLM Detector — Auto-detects LM Studio & Ollama models and recommends best for each task.

Scans:
  - C:\\Users\\Admin\\.lmstudio\\models  → all GGUF files (636 GB / 95 models)
  - C:\\Users\\Admin\\.ollama\\models\\manifests → all pulled Ollama models
  - LM Studio API  http://localhost:1234/v1/models  (when server is running)
  - Ollama API     http://localhost:11434/api/tags   (when ollama is running)

RTX 3090 Ti specific: 24 GB VRAM — tier thresholds defined below.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# ── Paths ─────────────────────────────────────────────────────────────
LMSTUDIO_MODELS_DIR = Path(os.environ.get("LMSTUDIO_MODELS", r"C:\Users\Admin\.lmstudio\models"))
OLLAMA_MANIFESTS_DIR = Path(os.environ.get("OLLAMA_MODELS", r"C:\Users\Admin\.ollama\models\manifests"))
LMSTUDIO_API = os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
OLLAMA_API   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")

# ── RTX 3090 Ti VRAM tiers ────────────────────────────────────────────
VRAM_GB = 24          # RTX 3090 Ti
VRAM_TIER_LARGE  = 20  # fits at Q4   (30-35B MoE or 20B dense)
VRAM_TIER_MEDIUM = 14  # fits at Q4   (24-27B)
VRAM_TIER_SMALL  = 10  # fits at Q8   (9-13B)
VRAM_TIER_TINY   = 5   # always fits  (up to 7B Q8)


# ── Task → model capability map ───────────────────────────────────────
# Keys must match task names used in ai_engine.py
TASK_CAPABILITY_PRIORITY = {
    "agentic":    ["devstral", "qwen3.5-35b", "qwen3.5-27b", "qwen3.5-9b", "qwen3", "llama3"],
    "coding":     ["devstral", "deepcoder", "qwen3.5-coder", "qwen3.5", "qwen3", "llama3"],
    "reasoning":  ["qwen3.5-27b-opus", "qwen3.5-9b-opus", "qwen3.5-35b", "deepseek-r1", "openthinker", "qwen3"],
    "vision":     ["glm-4.6v", "qwen3.5-27b", "qwen3.5-9b", "qwen2.5vl", "llava"],
    "fast":       ["qwen3.5-9b", "qwen3", "llama3.1:8b", "ministral"],
    "general":    ["qwen3.5-35b", "qwen3.5-27b", "devstral", "qwen3.5-9b", "llama3.1"],
    "embedding":  ["nomic-embed-text", "qwen3-embedding"],
}


# ── Context window database ───────────────────────────────────────────
# Native training context (tokens). With RoPE scaling LM Studio can push
# further but these are reliable baselines. Key: family string (lowercase).
CONTEXT_WINDOW_MAP: dict[str, int] = {
    "qwen3.5-35b":      131072,   # 128K native; rope-scaled builds → 256K
    "qwen3.5-27b":      131072,   # 128K; Opus distills often 200K capable
    "qwen3.5-9b":       131072,   # 128K native; some builds tagged 200K-256K
    "qwen3.5-4b":       131072,
    "qwen3.5-2b":       131072,
    "qwen3.5":          131072,
    "qwen3":            131072,   # Qwen3 family: 128K standard
    "qwen2.5-coder":    131072,
    "qwen2.5vl":        131072,
    "devstral":          32768,   # Devstral trained at 32K (code-focused)
    "glm-4.6v":         131072,   # GLM-4.6V-Flash: 128K
    "glm":              131072,
    "deepseek-r1":      131072,
    "deepcoder":        131072,
    "llama3.2":         131072,
    "llama3.1":         131072,
    "llama3":            8192,    # base llama3 8K
    "mistral-small":    131072,
    "ministral":         32768,
    "openthinker":       32768,
    "nomic-embed-text":   8192,
    "qwen3-embedding":   32768,
    "llava":             4096,
    "moondream":         2048,
    "minicpm":           8192,
    "unknown":           8192,
}

# Max context achievable with RoPE scaling (LM Studio supports this)
CONTEXT_ROPE_SCALED: dict[str, int] = {
    "qwen3.5-9b":  262144,   # 256K verified with YaRN/rope scaling
    "qwen3.5-27b": 262144,
    "qwen3.5-35b": 262144,
    "qwen3.5":     262144,
    "qwen3":       262144,
    "llama3.1":    131072,
    "llama3.2":    131072,
    "mistral-small": 131072,
    "glm-4.6v":    131072,
}


@dataclass
class ModelInfo:
    name: str            # display name / model ID for API
    path: str            # relative path from models dir (LM Studio) or tag (Ollama)
    provider: str        # "lmstudio" | "ollama"
    size_gb: float       # file size in GB (0.0 if unknown)
    family: str          # detected family: qwen3.5, devstral, glm, llama3, etc.
    quant: str           # Q4_K_M, Q8_0, fp16, etc.
    fits_vram: bool      # can load into RTX 3090 Ti (24 GB)
    is_vision: bool      # has multimodal / vision capability
    is_reasoning: bool   # distilled reasoning / thinking model
    is_coder: bool       # specialised for code
    tags: list[str] = field(default_factory=list)

    @property
    def context_window(self) -> int:
        """Native training context length in tokens."""
        return CONTEXT_WINDOW_MAP.get(self.family, 8192)

    @property
    def context_window_max(self) -> int:
        """Maximum achievable context with RoPE scaling."""
        return CONTEXT_ROPE_SCALED.get(self.family, self.context_window)

    @property
    def context_window_vram_limited(self) -> int:
        """Realistic max context given RTX 3090 Ti VRAM after model load.
        KV-cache at fp16: ~0.25 GB per 16K tokens for 9B, ~0.5 GB per 16K for 27B.
        """
        if self.size_gb <= 0:
            return self.context_window
        vram_for_kv = max(0.5, VRAM_GB - self.size_gb - 1.5)  # 1.5 GB OS overhead
        # Rough estimate: 0.015 GB per 1K tokens for 9B Q8, scales with model size
        kv_gb_per_1k = max(0.008, self.size_gb * 0.001)
        max_tokens = int((vram_for_kv / kv_gb_per_1k) * 1000)
        return min(max_tokens, self.context_window_max)

    @property
    def api_model_id(self) -> str:
        """Model ID to use in API calls."""
        if self.provider == "ollama":
            return self.path   # e.g. "qwen3:14b"
        # LM Studio: path relative to models folder
        return self.path


# ── Helpers ───────────────────────────────────────────────────────────

def _parse_family(name_lower: str) -> str:
    patterns = [
        (r"qwen3\.5-35b",   "qwen3.5-35b"),
        (r"qwen3\.5-27b",   "qwen3.5-27b"),
        (r"qwen3\.5-9b",    "qwen3.5-9b"),
        (r"qwen3\.5-4b",    "qwen3.5-4b"),
        (r"qwen3\.5-2b",    "qwen3.5-2b"),
        (r"qwen3\.5",       "qwen3.5"),
        (r"qwen3-embedding","qwen3-embedding"),
        (r"qwen3",          "qwen3"),
        (r"qwen2\.5-coder", "qwen2.5-coder"),
        (r"qwen2\.5vl",     "qwen2.5vl"),
        (r"qwen2\.5",       "qwen2.5"),
        (r"devstral",       "devstral"),
        (r"glm-4\.6v",      "glm-4.6v"),
        (r"glm",            "glm"),
        (r"deepseek-r1",    "deepseek-r1"),
        (r"deepcoder",      "deepcoder"),
        (r"llama3\.2",      "llama3.2"),
        (r"llama3\.1",      "llama3.1"),
        (r"llama3",         "llama3"),
        (r"mistral-small",  "mistral-small"),
        (r"ministral",      "ministral"),
        (r"openthinker",    "openthinker"),
        (r"nomic-embed",    "nomic-embed-text"),
        (r"llava",          "llava"),
        (r"bakllava",       "llava"),
        (r"moondream",      "moondream"),
        (r"minicpm",        "minicpm"),
    ]
    for pat, family in patterns:
        if re.search(pat, name_lower):
            return family
    return "unknown"


def _parse_quant(name: str) -> str:
    match = re.search(r"(q[0-9]_[0-9k_]+|q[0-9]+|fp16|fp32|bf16|f16|f32|mxfp4|gguf)", name.lower())
    return match.group(1).upper() if match else "GGUF"


def _is_vision(name_lower: str) -> bool:
    return bool(re.search(r"vl|vision|llava|bakllava|moondream|minicpm-v|glm-4\.6v|qwen.*vl|mmproj", name_lower))


def _is_reasoning(name_lower: str) -> bool:
    return bool(re.search(r"r1|opus|reasoning|thinking|think|distill|openthinker", name_lower))


def _is_coder(name_lower: str) -> bool:
    return bool(re.search(r"coder|devstral|deepcoder|code|python", name_lower))


def _fits_vram(size_gb: float) -> bool:
    """Check if model fits in RTX 3090 Ti (24 GB VRAM) with 2 GB OS overhead."""
    return size_gb <= (VRAM_GB - 2) if size_gb > 0 else True


# ── LM Studio Scanner ─────────────────────────────────────────────────

def scan_lmstudio_models() -> list[ModelInfo]:
    """Scan GGUF files under ~/.lmstudio/models — excludes mmproj files."""
    models: list[ModelInfo] = []
    if not LMSTUDIO_MODELS_DIR.exists():
        return models

    for gguf in LMSTUDIO_MODELS_DIR.rglob("*.gguf"):
        # Skip projection files (not loadable standalone)
        if "mmproj" in gguf.name.lower():
            continue
        rel = str(gguf.relative_to(LMSTUDIO_MODELS_DIR)).replace("\\", "/")
        size_gb = round(gguf.stat().st_size / (1024 ** 3), 2)
        name_lower = gguf.name.lower() + "/" + rel.lower()
        models.append(ModelInfo(
            name=gguf.stem,
            path=rel,
            provider="lmstudio",
            size_gb=size_gb,
            family=_parse_family(name_lower),
            quant=_parse_quant(gguf.name),
            fits_vram=_fits_vram(size_gb),
            is_vision=_is_vision(name_lower),
            is_reasoning=_is_reasoning(name_lower),
            is_coder=_is_coder(name_lower),
            tags=_build_tags(name_lower, size_gb),
        ))

    models.sort(key=lambda m: m.size_gb, reverse=True)
    return models


def _build_tags(name_lower: str, size_gb: float) -> list[str]:
    tags = []
    if _is_vision(name_lower):     tags.append("vision")
    if _is_reasoning(name_lower):  tags.append("reasoning")
    if _is_coder(name_lower):      tags.append("coding")
    if "opus" in name_lower:       tags.append("opus4.6-distill")
    if "qwen3.5" in name_lower:    tags.append("qwen3.5")
    if "glm" in name_lower:        tags.append("glm4.6v")
    if size_gb >= VRAM_TIER_LARGE: tags.append("large")
    elif size_gb >= VRAM_TIER_MEDIUM: tags.append("medium")
    elif size_gb > 0:              tags.append("small")
    return tags


# ── Ollama Scanner ────────────────────────────────────────────────────

def scan_ollama_models() -> list[ModelInfo]:
    """Scan Ollama manifest files to list installed models."""
    models: list[ModelInfo] = []
    if not OLLAMA_MANIFESTS_DIR.exists():
        return models

    for manifest_file in OLLAMA_MANIFESTS_DIR.rglob("*"):
        if manifest_file.is_file() and "." not in manifest_file.name:
            # Path: registry.ollama.ai/library/{name}/{tag}
            parts = manifest_file.parts
            try:
                lib_idx = list(parts).index("library")
                model_name = parts[lib_idx + 1]
                tag = parts[lib_idx + 2] if len(parts) > lib_idx + 2 else "latest"
                model_id = f"{model_name}:{tag}"
                name_lower = model_id.lower()
                models.append(ModelInfo(
                    name=model_id,
                    path=model_id,
                    provider="ollama",
                    size_gb=0.0,  # manifest doesn't include size directly
                    family=_parse_family(name_lower),
                    quant=_parse_quant(name_lower),
                    fits_vram=True,  # assume fits — Ollama manages this
                    is_vision=_is_vision(name_lower),
                    is_reasoning=_is_reasoning(name_lower),
                    is_coder=_is_coder(name_lower),
                    tags=_build_tags(name_lower, 0.0),
                ))
            except (ValueError, IndexError):
                continue

    return models


# ── Live API Queries ──────────────────────────────────────────────────

def query_lmstudio_loaded() -> Optional[str]:
    """Return currently-loaded model ID from LM Studio API."""
    if not _HAS_HTTPX:
        return None
    try:
        r = httpx.get(f"{LMSTUDIO_API}/models", timeout=3.0)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return data[0].get("id")
    except Exception:
        pass
    return None


def query_ollama_running() -> list[str]:
    """Return list of currently-running Ollama models."""
    if not _HAS_HTTPX:
        return []
    try:
        r = httpx.get(f"{OLLAMA_API}/api/ps", timeout=3.0)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def is_lmstudio_running() -> bool:
    if not _HAS_HTTPX:
        return False
    try:
        r = httpx.get(f"{LMSTUDIO_API}/models", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def is_ollama_running() -> bool:
    if not _HAS_HTTPX:
        return False
    try:
        r = httpx.get(f"{OLLAMA_API}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


# ── Recommendation Engine ─────────────────────────────────────────────

# Explicit priority list for HyperSpin toolkit agentic tasks
# Ordered: best first. Model path substrings matched case-insensitively.
AGENTIC_PRIORITY_LMS = [
    "Devstral-Small-2-24B-Instruct-2512-Q4_K_M",   # best coder/agent, 13.35 GB
    "Qwen3.5-35B-A3B-Q4_K_M",                       # largest Qwen3.5 MoE, 19.72 GB
    "Qwen3.5-27B-Claude-4.6-Opus",                  # 27B Opus distill
    "Qwen3.5-9B-Claude-4.6",                         # 9B Opus distill
    "Qwen3.5-9B-Q8_0",                               # pure Qwen3.5 9B
    "gpt-oss-20b",                                   # OpenAI OSS 20B
    "mistral-small",                                 # Mistral small
]

VISION_PRIORITY_LMS = [
    "GLM-4.6V-Flash-Q8_0",    # best vision 9.31 GB
    "GLM-4.6V-Flash-Q4_K_M",  # smaller vision
    "Qwen3.5-27B",             # VL capable
    "Qwen3.5-9B",              # VL capable
    "qwen2.5vl",
]

AGENTIC_PRIORITY_OLLAMA = [
    "devstral:latest",
    "qwen3:14b",
    "deepseek-r1:14b",
    "qwen3:8b",
    "llama3.1:8b",
    "mistral-small3.1:latest",
]

VISION_PRIORITY_OLLAMA = [
    "qwen2.5vl:latest",
    "llava:13b",
    "minicpm-v:latest",
    "llava-llama3:latest",
    "moondream:latest",
]


def recommend_model(
    task: str = "agentic",
    provider_preference: str = "lmstudio",
    lms_models: Optional[list[ModelInfo]] = None,
    ollama_models: Optional[list[ModelInfo]] = None,
) -> Optional[ModelInfo]:
    """
    Returns the best ModelInfo for a given task.
    provider_preference: "lmstudio" | "ollama" | "any"
    """
    if lms_models is None:
        lms_models = scan_lmstudio_models()
    if ollama_models is None:
        ollama_models = scan_ollama_models()

    priority_lms    = VISION_PRIORITY_LMS    if task == "vision" else AGENTIC_PRIORITY_LMS
    priority_ollama = VISION_PRIORITY_OLLAMA if task == "vision" else AGENTIC_PRIORITY_OLLAMA

    def _find_in_list(models: list[ModelInfo], priority: list[str]) -> Optional[ModelInfo]:
        for want in priority:
            want_lower = want.lower()
            for m in models:
                if want_lower in m.path.lower() and m.fits_vram:
                    return m
        # Fallback: any fits_vram model with matching tags
        task_tag = "vision" if task == "vision" else ("coding" if task == "coding" else "reasoning")
        for m in models:
            if m.fits_vram and task_tag in m.tags:
                return m
        return models[0] if models else None

    if provider_preference in ("lmstudio", "any") and lms_models:
        result = _find_in_list([m for m in lms_models if m.fits_vram], priority_lms)
        if result:
            return result

    if provider_preference in ("ollama", "any") and ollama_models:
        result = _find_in_list(ollama_models, priority_ollama)
        if result:
            return result

    return None


# ── Full Report ───────────────────────────────────────────────────────

def full_model_report() -> dict:
    """Build a comprehensive report of all models + recommendations."""
    lms_models    = scan_lmstudio_models()
    ollama_models = scan_ollama_models()

    lms_running   = is_lmstudio_running()
    ollama_running = is_ollama_running()
    lms_loaded    = query_lmstudio_loaded() if lms_running else None
    ollama_running_models = query_ollama_running() if ollama_running else []

    # Best per task
    recommendations: dict[str, dict] = {}
    for task in ["agentic", "coding", "reasoning", "vision", "fast", "general"]:
        pref = "lmstudio" if lms_models else "ollama"
        best = recommend_model(task, pref, lms_models, ollama_models)
        if best:
            recommendations[task] = {
                "provider":           best.provider,
                "model_id":           best.api_model_id,
                "size_gb":            best.size_gb,
                "family":             best.family,
                "quant":              best.quant,
                "tags":               best.tags,
                "context_native_k":   best.context_window // 1024,
                "context_max_k":      best.context_window_max // 1024,
                "context_vram_k":     best.context_window_vram_limited // 1024,
                "lmstudio_url":       LMSTUDIO_API if best.provider == "lmstudio" else None,
            }

    # Opus 4.6 distills specifically
    opus_models = [m for m in lms_models if "opus" in " ".join(m.tags) and m.fits_vram]
    qwen35_models = [m for m in lms_models if m.family.startswith("qwen3.5") and m.fits_vram]
    glm_models = [m for m in lms_models if "glm" in m.family and m.fits_vram]

    return {
        "lmstudio": {
            "running":       lms_running,
            "loaded_model":  lms_loaded,
            "api_url":       LMSTUDIO_API,
            "total_models":  len(lms_models),
            "total_gb":      round(sum(m.size_gb for m in lms_models), 1),
            "fits_vram_count": sum(1 for m in lms_models if m.fits_vram),
        },
        "ollama": {
            "running":        ollama_running,
            "running_models": ollama_running_models,
            "api_url":        OLLAMA_API,
            "total_models":   len(ollama_models),
        },
        "highlight_models": {
            "opus4.6_distills": [
                {"model_id": m.api_model_id, "size_gb": m.size_gb, "family": m.family}
                for m in opus_models[:5]
            ],
            "qwen3.5": [
                {"model_id": m.api_model_id, "size_gb": m.size_gb, "quant": m.quant}
                for m in qwen35_models[:5]
            ],
            "glm_vision": [
                {"model_id": m.api_model_id, "size_gb": m.size_gb, "quant": m.quant}
                for m in glm_models[:3]
            ],
        },
        "recommendations": recommendations,
        "rtx3090ti_notes": {
            "vram_gb": VRAM_GB,
            "max_model_gb": VRAM_GB - 2,
            "best_agentic": recommendations.get("agentic", {}).get("model_id"),
            "best_vision":  recommendations.get("vision",  {}).get("model_id"),
            "best_coding":  recommendations.get("coding",  {}).get("model_id"),
        },
    }


# ── Convenience accessors ─────────────────────────────────────────────

def get_best_agentic_model() -> Optional[ModelInfo]:
    """Fast accessor — returns the single best model for agentic toolkit tasks."""
    lms = scan_lmstudio_models()
    return recommend_model("agentic", "lmstudio", lms) or recommend_model("agentic", "ollama")


def get_best_vision_model() -> Optional[ModelInfo]:
    lms = scan_lmstudio_models()
    return recommend_model("vision", "lmstudio", lms) or recommend_model("vision", "ollama")


def get_lmstudio_base_url() -> str:
    return LMSTUDIO_API


def get_ollama_base_url() -> str:
    return OLLAMA_API


if __name__ == "__main__":
    import json as _json
    report = full_model_report()
    print(_json.dumps(report, indent=2, default=str))
