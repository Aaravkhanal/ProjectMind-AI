# ProjectMind AI — VS Code Extension

**The AI engineering platform that already knows what tools you have.**

ProjectMind AI automatically discovers your AI environment, learns from your codebase over time, and brings multi-agent code review, intelligent task routing, cost tracking, and autonomous code editing directly into VS Code.

---

## What it does

When you open a project with ProjectMind:

1. **Scans your environment** — detects your API keys, local Ollama models, MCP servers, and other AI tools automatically. No manual configuration.
2. **Builds a capability matrix** — decides which model is best for coding, security review, documentation, reasoning, etc. based on what you actually have.
3. **Shows a live sidebar** — Brain, Git Intelligence, Cost tracking, and Execution Plans update as you work.
4. **Runs multi-agent reviews** — 3 specialized agents (Architect, Security, Quality) review code in parallel and synthesize a single verdict.

---

## Features

### Sidebar panels (Activity Bar)

| Panel | What it shows |
|-------|---------------|
| **Repository Brain** | Which files are hotspots, tech debt by category, contributor quality scores |
| **Git Intelligence** | Commit type breakdown (feat/fix/refactor/docs), file churn, recent PR risk scores |
| **Cost & Budget** | Live spend tracking, monthly forecast, budget alerts, model tier breakdown |
| **Execution Plans** | AI-generated multi-step plans waiting for your approval |

### Commands

Open with `Cmd+Shift+P` and type "ProjectMind":

| Command | Description |
|---------|-------------|
| **Discover AI Environment** | Scans your machine and shows which models, providers, and agents were detected. Builds an intelligent routing table automatically. |
| **Import Detected Providers** | One-click import of all detected API keys into the encrypted provider store |
| **Multi-Agent Review** | Runs Architect + Security + Quality agents in parallel on any diff |
| **Generate Agent Prompt** | Generates a context-enriched prompt for any task using your project's full context |
| **Score PR Risk** | 6-factor risk assessment on a diff: size, file types, test coverage, security, complexity, history |
| **Approve Plan** | Review and approve AI-generated execution plans step by step |
| **Set Monthly Budget** | Configure a spend limit — the platform automatically downgrades models to stay within budget |

---

## Getting started

### 1. Install the extension

Search **"ProjectMind AI"** in the VS Code Extensions panel, or install from the command line:

```bash
code --install-extension aaravkhanal.projectmind
```

### 2. Start the backend

The extension connects to the ProjectMind backend running locally. Clone the repo and start it:

```bash
git clone https://github.com/Aaravkhanal/llm-reviewer
cd llm-reviewer
.venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Or with Docker:

```bash
docker compose up
```

### 3. Open a project

Open any project folder in VS Code. Click the **ProjectMind brain icon** in the Activity Bar — the sidebar loads automatically.

### 4. Discover your environment

Press `Cmd+Shift+P` → **ProjectMind: Discover AI Environment**

The extension scans your machine and shows:
- Which editor/IDE you're running
- Which API providers were detected (from environment variables)
- Which local models are running (Ollama, LM Studio, etc.)
- Which MCP servers are configured
- The routing table: which model handles each task type

---

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `projectmind.backendUrl` | `http://localhost:8000` | URL of the ProjectMind backend |
| `projectmind.llmProvider` | `nvidia` | Default LLM provider for reviews |
| `projectmind.reviewBudgetUsd` | `1.0` | Max spend per review in USD |

---

## Requirements

- VS Code 1.85+
- ProjectMind backend running locally (see setup above)
- At least one LLM provider: any API key, or Ollama running locally (free)

---

## Built by Aarav Khanal

[GitHub](https://github.com/Aaravkhanal) · [Marketplace](https://marketplace.visualstudio.com/items?itemName=aaravkhanal.projectmind) · [Backend repo](https://github.com/Aaravkhanal/llm-reviewer)
