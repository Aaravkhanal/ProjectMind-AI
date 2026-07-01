# Service Map: ProjectMind AI

## LLM Providers

| Provider | Models | Key Env | Gateway |
|----------|--------|---------|---------|
| NVIDIA NIM | 14 (Llama, Mistral, DeepSeek, Gemma) | `NVIDIA_API_KEY` | LiteLLM |
| OpenAI | GPT-4o, GPT-4o-mini, o3-mini | `OPENAI_API_KEY` | LiteLLM |
| Anthropic | Claude Opus/Sonnet/Haiku | `ANTHROPIC_API_KEY` | LiteLLM |
| Google | Gemini 2.5 Pro/Flash, 1.5 Pro | `GEMINI_API_KEY` | LiteLLM |
| Groq | Llama 3.3-70B, 3.1-8B, Mixtral | `GROQ_API_KEY` | LiteLLM |
| DeepSeek | Chat V3, Reasoner R1 | `DEEPSEEK_API_KEY` | LiteLLM |
| OpenRouter | All models via proxy | `OPENROUTER_API_KEY` | LiteLLM |
| Together AI | Llama, Mixtral, others | `TOGETHER_API_KEY` | LiteLLM |
| Mistral | Large, Small, Codestral | `MISTRAL_API_KEY` | LiteLLM |
| xAI | Grok-3, Grok-3-mini | `XAI_API_KEY` | LiteLLM |
| Fireworks | Llama variants | `FIREWORKS_API_KEY` | LiteLLM |
| HuggingFace | Inference API | `HUGGINGFACE_API_KEY` | LiteLLM |
| Ollama | Any local model | — (no key) | LiteLLM |
| LM Studio | OpenAI-compatible local | — (no key) | LiteLLM |
| vLLM | Self-hosted | — (no key) | LiteLLM |

## Storage Services

| Service | Location | Purpose |
|---------|----------|---------|
| SQLite | `.projectmind/memory.db` | 19 tables: all structured data |
| ChromaDB | `.projectmind/chroma/` | Optional vector embeddings |
| File cache | `.projectmind/*.json` | Health scores, analysis reports, graph |
| Secret key | `.projectmind/secret.key` | Fernet key for BYOK encryption |

## Background Services

| Service | Trigger | Purpose |
|---------|---------|---------|
| Brain Indexer | After every review | Index PR → hotspots, debt, contributors, insights |
| Cost Recorder | After every agent call | Record cost → budget alerts |
| File Watcher | Watchdog (debounced 2s) | Auto-refresh on `.projectmind/` changes |
| Model Profiler | POST /providers/{p}/benchmark | Background benchmark job |

## Integration Surfaces

| Surface | Protocol | Tools |
|---------|----------|-------|
| FastAPI REST | HTTP/JSON | 90+ endpoints |
| MCP Server | stdio | 8 tools (Claude Code, Cursor, Windsurf) |
| GitHub Webhook | HTTPS POST | PR review automation |
| GitLab Webhook | HTTPS POST | MR review automation |
| VSCode Extension | VS Code API | Sidebar + 10 commands |
| GitHub Actions | YAML workflow | CI/CD health gate |

## Observability

| Service | Activation | Data |
|---------|------------|------|
| Langfuse | `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` | Agent traces, token counts, costs, latency |
| OpenTelemetry | `opentelemetry-sdk` installed | Spans (wiring pending) |
| Built-in analytics | Always on | `/cost/summary`, token savings per review |
