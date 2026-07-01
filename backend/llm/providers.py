from __future__ import annotations

import importlib.resources as pkg
import os
from enum import Enum
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


class LLMProvider(Enum):
    OLLAMA    = "ollama"
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    NVIDIA    = "nvidia"
    GEMINI    = "gemini"    # requires GOOGLE_API_KEY + pip install langchain-google-genai
    DEEPSEEK  = "deepseek"  # requires DEEPSEEK_API_KEY (or use NVIDIA provider instead)


class PromptTemplate(Enum):
    CONTEXT      = "context.md"
    RESPONSE     = "response.md"
    DNA_EXTRACT  = "dna_extract.md"
    SMART_PROMPT = "smart_prompt.md"
    COMPRESS     = "compress.md"


PROMPT_PACKAGE = "backend.llm.prompts"

# DeepSeek uses an OpenAI-compatible API
_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class LLM:
    def __init__(
        self,
        model_name: str,
        provider: LLMProvider = LLMProvider.OPENAI,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.3,
    ):
        self.model_name = model_name
        self.model: Optional[BaseChatModel] = None
        self._load(provider, api_key, base_url, temperature)

    def _load(
        self,
        provider: LLMProvider,
        api_key: Optional[str],
        base_url: Optional[str],
        temperature: float,
    ) -> None:
        env_base_url = base_url or os.environ.get("API_URL")

        if provider == LLMProvider.OLLAMA:
            self.model = ChatOllama(
                model=self.model_name,
                base_url=env_base_url,
                temperature=temperature,
            )

        elif provider == LLMProvider.OPENAI:
            key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY", "")
            self.model = ChatOpenAI(
                model=self.model_name,
                base_url=env_base_url or None,
                timeout=None,
                api_key=SecretStr(key),
                temperature=temperature,
            )

        elif provider == LLMProvider.ANTHROPIC:
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self.model = ChatAnthropic(
                model_name=self.model_name,
                api_key=SecretStr(key),
                temperature=temperature,
            )

        elif provider == LLMProvider.NVIDIA:
            key = api_key or os.environ.get("API_KEY", "")
            nvidia_url = env_base_url or os.environ.get(
                "NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1"
            )
            self.model = ChatOpenAI(
                model=self.model_name,
                base_url=nvidia_url,
                api_key=SecretStr(key),
                temperature=temperature,
            )

        elif provider == LLMProvider.GEMINI:
            key = api_key or os.environ.get("GOOGLE_API_KEY", "")
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import]
                self.model = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=SecretStr(key),
                    temperature=temperature,
                )
            except ImportError as e:
                raise ImportError(
                    "Gemini provider requires: pip install langchain-google-genai"
                ) from e

        elif provider == LLMProvider.DEEPSEEK:
            key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
            deepseek_url = env_base_url or _DEEPSEEK_BASE_URL
            self.model = ChatOpenAI(
                model=self.model_name,
                base_url=deepseek_url,
                api_key=SecretStr(key),
                temperature=temperature,
            )

    @staticmethod
    def load_prompt(template: PromptTemplate) -> ChatPromptTemplate:
        with pkg.open_text(PROMPT_PACKAGE, template.value) as f:
            content = f.read()
        return ChatPromptTemplate.from_template(content)

    @staticmethod
    def from_env(model_env: str = "CODE_MODEL", provider_env: str = "openai") -> "LLM":
        model_name   = os.environ.get(model_env, "meta/llama-3.1-8b-instruct")
        raw_provider = os.environ.get("LLM_PROVIDER", provider_env).lower()
        provider     = LLMProvider(raw_provider)
        return LLM(model_name=model_name, provider=provider)

    @staticmethod
    def from_config(config: "ModelConfig") -> "LLM":  # type: ignore[name-defined]
        """Build an LLM directly from a ModelRouter ModelConfig."""
        from backend.llm.catalog import ModelConfig  # local import avoids circular
        return LLM(
            model_name=config.model_id,
            provider=LLMProvider(config.provider),
        )
