# Dependency Graph: ProjectMind AI

## Python Packages (pyproject.toml)

### Web Framework
```
fastapi ^0.115.0        → HTTP routing, OpenAPI docs
uvicorn[standard] ^0.32.0  → ASGI server (websockets + watchfiles)
python-multipart ^0.0.17   → form data / file uploads
```

### Database
```
sqlmodel ^0.0.22        → SQLAlchemy + Pydantic unified ORM
  └── sqlalchemy        → SQL engine
  └── pydantic          → data validation
```

### AI / LLM Core (NEW: LiteLLM replaces per-provider bindings)
```
litellm ^1.70.0 ★ NEW    → Universal gateway: 100+ providers, OpenAI-compatible
langchain ^0.3.6          → LLM chains, prompt templates
langchain-core ^0.3.0     → Base abstractions
langchain-community ^0.3.5 → Integrations
langchain-openai ^0.3.17  → OpenAI + NVIDIA via OpenAI API
langchain-anthropic ^0.3.10 → Anthropic
langchain-text-splitters ^0.3.8 → RAG chunking
langchain-ollama ^0.3.2   → Local models
langgraph ^1.0.0          → Multi-agent orchestration graphs
```

### BYOK Security (NEW)
```
cryptography ^44.0.0 ★ NEW → Fernet symmetric encryption for API keys
```

### Vector Store
```
chromadb ^0.6.3           → Local vector database
langchain-chroma ^0.2.1   → LangChain ChromaDB integration
```

### Observability (NEW, optional)
```
langfuse ^2.0.0 ★ NEW     → LLM observability (optional extra)
opentelemetry-api ^1.27.0 ★ NEW → Distributed tracing (optional extra)
opentelemetry-sdk ^1.27.0 ★ NEW → SDK (optional extra)
```

### Git Integrations
```
PyGithub ^2.1.1           → GitHub API client
python-gitlab ^5.6.0      → GitLab API client
```

### CLI & Templates
```
click ^8.1.7              → CLI framework
jinja2 ^3.1.4             → Prompt templates
```

### Graph Analysis
```
networkx ^3.4.2           → Dependency graph, PageRank, centrality
```

### MCP Server
```
mcp ^1.0.0                → Model Context Protocol
```

### Infrastructure
```
watchdog ^4.0.0           → File system watcher
python-dotenv ^1.0.1      → .env loading
```

### Optional Extras
```
# pip install projectmind[huggingface]
langchain-huggingface ^0.2.0  → HuggingFace embeddings
hf-xet ^1.1.2                → HF LFS acceleration

# pip install projectmind[observability]  ★ NEW
langfuse ^2.0.0
opentelemetry-api ^1.27.0
opentelemetry-sdk ^1.27.0
```

## Dependency Graph (key relationships)
```
FastAPI
  └── uvicorn (ASGI server)
  └── pydantic (validation)

LiteLLM ★                   # NEW universal gateway
  ├── openai (sdk)
  ├── anthropic (sdk)
  └── httpx (async HTTP)

LangGraph
  └── langchain-core
      ├── langchain
      │   ├── langchain-openai
      │   ├── langchain-anthropic
      │   ├── langchain-ollama
      │   └── langchain-community
      └── langchain-text-splitters

SQLModel
  └── sqlalchemy
  └── pydantic

chromadb
  └── langchain-chroma

cryptography ★               # NEW BYOK encryption
  └── cffi (C bindings)
```

## ★ New dependencies added in this update
| Package | Version | Purpose |
|---------|---------|---------|
| `litellm` | ^1.70.0 | Universal LLM gateway (100+ providers) |
| `cryptography` | ^44.0.0 | Fernet encryption for BYOK API keys |
| `langfuse` | ^2.0.0 | LLM observability (optional) |
| `opentelemetry-api/sdk` | ^1.27.0 | Distributed tracing (optional) |
