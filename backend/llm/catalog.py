"""
Model catalog — every supported model across all providers.

All NVIDIA models use your existing NVIDIA API key and base URL.
Gemini requires GOOGLE_API_KEY (optional).
DeepSeek can be accessed via NVIDIA (no extra key) or directly via DEEPSEEK_API_KEY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskComplexity(str, Enum):
    SIMPLE  = "simple"   # rename, format, comment, typo
    MEDIUM  = "medium"   # bug fix, review, tests, docs
    COMPLEX = "complex"  # architecture, security audit, major refactor


class ModelTier(str, Enum):
    FAST      = "fast"      # lowest latency + cost
    BALANCED  = "balanced"  # good quality / cost ratio
    POWERFUL  = "powerful"  # highest capability
    REASONING = "reasoning" # chain-of-thought, complex logic


@dataclass
class ModelConfig:
    provider: str           # matches LLMProvider enum value
    model_id: str           # exact model identifier sent to API
    display_name: str
    tier: ModelTier
    context_window: int     # tokens
    cost_per_1k_input: float   # USD
    cost_per_1k_output: float  # USD
    strengths: list[str] = field(default_factory=list)
    requires_env: str = ""  # env var needed beyond the default key; "" = uses NVIDIA key


# ── NVIDIA NIM models (all use NVIDIA API key, no extra setup) ────────────────

NVIDIA_MODELS: list[ModelConfig] = [
    # Fast tier
    ModelConfig(
        provider="nvidia",
        model_id="meta/llama-3.1-8b-instruct",
        display_name="Llama 3.1 8B",
        tier=ModelTier.FAST,
        context_window=128_000,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        strengths=["fast", "formatting", "comments", "simple-fixes"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="mistralai/mistral-7b-instruct-v0.3",
        display_name="Mistral 7B",
        tier=ModelTier.FAST,
        context_window=32_000,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        strengths=["fast", "code", "instruction-following"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="google/gemma-2-9b-it",
        display_name="Gemma 2 9B",
        tier=ModelTier.FAST,
        context_window=8_192,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        strengths=["fast", "general", "lightweight"],
    ),

    # Balanced tier
    ModelConfig(
        provider="nvidia",
        model_id="meta/llama-3.1-70b-instruct",
        display_name="Llama 3.1 70B",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.0008,
        strengths=["code-review", "bug-fixing", "testing", "documentation"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="mistralai/mixtral-8x7b-instruct-v0.1",
        display_name="Mixtral 8x7B",
        tier=ModelTier.BALANCED,
        context_window=32_000,
        cost_per_1k_input=0.0006,
        cost_per_1k_output=0.0006,
        strengths=["code", "multilingual", "reasoning"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="deepseek-ai/deepseek-coder-6.7b-instruct",
        display_name="DeepSeek Coder 6.7B",
        tier=ModelTier.BALANCED,
        context_window=16_000,
        cost_per_1k_input=0.0002,
        cost_per_1k_output=0.0002,
        strengths=["code-generation", "refactoring", "debugging", "code-specific"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="nvidia/llama-3.1-nemotron-70b-instruct",
        display_name="Nemotron 70B",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.0008,
        strengths=["instruction-following", "code", "analysis", "nvidia-optimized"],
    ),

    # Powerful tier
    ModelConfig(
        provider="nvidia",
        model_id="meta/llama-3.1-405b-instruct",
        display_name="Llama 3.1 405B",
        tier=ModelTier.POWERFUL,
        context_window=128_000,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
        strengths=["architecture", "complex-analysis", "security-audit", "large-refactors"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="mistralai/mistral-large-2-instruct",
        display_name="Mistral Large 2",
        tier=ModelTier.POWERFUL,
        context_window=128_000,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.009,
        strengths=["reasoning", "code", "architecture", "multilingual"],
    ),

    # Reasoning tier
    ModelConfig(
        provider="nvidia",
        model_id="deepseek-ai/deepseek-r1",
        display_name="DeepSeek R1",
        tier=ModelTier.REASONING,
        context_window=64_000,
        cost_per_1k_input=0.0055,
        cost_per_1k_output=0.0219,
        strengths=["reasoning", "security", "architecture", "complex-logic", "chain-of-thought"],
    ),
    ModelConfig(
        provider="nvidia",
        model_id="deepseek-ai/deepseek-r1-distill-llama-70b",
        display_name="DeepSeek R1 Distill 70B",
        tier=ModelTier.REASONING,
        context_window=64_000,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.004,
        strengths=["reasoning", "code", "fast-reasoning", "cost-effective"],
    ),
]

# ── Google Gemini (requires GOOGLE_API_KEY) ───────────────────────────────────

GEMINI_MODELS: list[ModelConfig] = [
    ModelConfig(
        provider="gemini",
        model_id="gemini-1.5-flash",
        display_name="Gemini 1.5 Flash",
        tier=ModelTier.FAST,
        context_window=1_000_000,
        cost_per_1k_input=0.000075,
        cost_per_1k_output=0.0003,
        strengths=["fast", "long-context", "multimodal"],
        requires_env="GOOGLE_API_KEY",
    ),
    ModelConfig(
        provider="gemini",
        model_id="gemini-1.5-pro",
        display_name="Gemini 1.5 Pro",
        tier=ModelTier.POWERFUL,
        context_window=2_000_000,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
        strengths=["long-context", "reasoning", "architecture", "multimodal"],
        requires_env="GOOGLE_API_KEY",
    ),
    ModelConfig(
        provider="gemini",
        model_id="gemini-2.0-flash-exp",
        display_name="Gemini 2.0 Flash",
        tier=ModelTier.BALANCED,
        context_window=1_000_000,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        strengths=["fast", "reasoning", "code", "experimental"],
        requires_env="GOOGLE_API_KEY",
    ),
]

# ── DeepSeek direct API (requires DEEPSEEK_API_KEY — optional, NVIDIA works too) ──

DEEPSEEK_MODELS: list[ModelConfig] = [
    ModelConfig(
        provider="deepseek",
        model_id="deepseek-chat",
        display_name="DeepSeek Chat V3",
        tier=ModelTier.BALANCED,
        context_window=64_000,
        cost_per_1k_input=0.00027,
        cost_per_1k_output=0.0011,
        strengths=["code", "reasoning", "cost-effective"],
        requires_env="DEEPSEEK_API_KEY",
    ),
    ModelConfig(
        provider="deepseek",
        model_id="deepseek-reasoner",
        display_name="DeepSeek R1 (Direct)",
        tier=ModelTier.REASONING,
        context_window=64_000,
        cost_per_1k_input=0.00055,
        cost_per_1k_output=0.0219,
        strengths=["reasoning", "chain-of-thought", "complex-logic"],
        requires_env="DEEPSEEK_API_KEY",
    ),
]

# ── Anthropic (requires ANTHROPIC_API_KEY) ────────────────────────────────────

ANTHROPIC_MODELS: list[ModelConfig] = [
    ModelConfig(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        tier=ModelTier.FAST,
        context_window=200_000,
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
        strengths=["fast", "code", "formatting", "summaries"],
        requires_env="ANTHROPIC_API_KEY",
    ),
    ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        tier=ModelTier.BALANCED,
        context_window=200_000,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        strengths=["code-review", "architecture", "reasoning", "safety"],
        requires_env="ANTHROPIC_API_KEY",
    ),
    ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-8",
        display_name="Claude Opus 4.8",
        tier=ModelTier.POWERFUL,
        context_window=200_000,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        strengths=["complex-reasoning", "architecture", "security", "research"],
        requires_env="ANTHROPIC_API_KEY",
    ),
]

# ── OpenAI (requires OPENAI_API_KEY) ─────────────────────────────────────────

OPENAI_MODELS: list[ModelConfig] = [
    ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        tier=ModelTier.FAST,
        context_window=128_000,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        strengths=["fast", "formatting", "simple-review", "cost-effective"],
        requires_env="OPENAI_API_KEY",
    ),
    ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
        strengths=["code-review", "architecture", "multimodal"],
        requires_env="OPENAI_API_KEY",
    ),
    ModelConfig(
        provider="openai",
        model_id="o3-mini",
        display_name="o3-mini",
        tier=ModelTier.REASONING,
        context_window=200_000,
        cost_per_1k_input=0.0011,
        cost_per_1k_output=0.0044,
        strengths=["reasoning", "code", "math", "complex-logic"],
        requires_env="OPENAI_API_KEY",
    ),
]

# ── Master catalog ─────────────────────────────────────────────────────────────

ALL_MODELS: list[ModelConfig] = (
    NVIDIA_MODELS + GEMINI_MODELS + DEEPSEEK_MODELS + ANTHROPIC_MODELS + OPENAI_MODELS
)

MODEL_BY_ID: dict[str, ModelConfig] = {m.model_id: m for m in ALL_MODELS}
