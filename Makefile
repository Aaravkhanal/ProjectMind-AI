.PHONY: help install dev serve analyze compress init mcp watch ui \
        build-extension publish-cli publish-extension publish-action \
        deploy-railway deploy-fly docker-up docker-down docker-build lint clean

help:
	@echo ""
	@echo "  ProjectMind AI"
	@echo ""
	@echo "  Development"
	@echo "    make install           Install all Python + Node dependencies"
	@echo "    make dev               Start API in dev mode (hot reload)"
	@echo "    make ui                Start Next.js dashboard"
	@echo "    make analyze           Run analysis on current directory"
	@echo ""
	@echo "  Publishing"
	@echo "    make publish-cli       Build + publish CLI to PyPI"
	@echo "    make build-extension   Build VS Code extension (.vsix)"
	@echo "    make publish-extension Publish extension to VS Code Marketplace"
	@echo "    make publish-action    Tag + push GitHub Action release"
	@echo ""
	@echo "  Deployment (GitHub App / SaaS backend)"
	@echo "    make deploy-railway    Deploy API to Railway"
	@echo "    make deploy-fly        Deploy API to Fly.io"
	@echo ""

# ── Development ────────────────────────────────────────────────────────────

install:
	poetry install
	cd vscode-extension && npm install

serve:
	poetry run serve

dev:
	poetry run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

init:
	poetry run projectmind init .

analyze:
	poetry run projectmind analyze .

compress:
	poetry run projectmind compress .

mcp:
	poetry run projectmind-mcp

watch:
	poetry run projectmind watch .

ui:
	cd frontend && npm install && npm run dev

lint:
	poetry run ruff check backend/ cli/ --fix 2>/dev/null || true
	cd vscode-extension && npm run lint 2>/dev/null || true

# ── Docker ────────────────────────────────────────────────────────────────

docker-up:
	docker compose up

docker-down:
	docker compose down

docker-build:
	docker compose build && docker compose up

# ── PyPI ─────────────────────────────────────────────────────────────────

publish-cli: clean
	@echo "→ Building CLI package..."
	poetry build
	@echo "→ Publishing to PyPI (requires PYPI_TOKEN env var)..."
	poetry publish --username __token__ --password "$(PYPI_TOKEN)"
	@echo "✓ Published. Users can now:  pip install projectmind"

# ── VS Code Extension ─────────────────────────────────────────────────────

build-extension:
	cd vscode-extension && npm install && npm run compile
	cd vscode-extension && npx @vscode/vsce package --allow-missing-repository
	@ls vscode-extension/*.vsix
	@echo ""
	@echo "✓ Packaged. Install locally:"
	@echo "  code --install-extension vscode-extension/\$$(ls vscode-extension/*.vsix | head -1)"

publish-extension:
	cd vscode-extension && npm install && npm run compile
	@echo "→ Publishing to VS Code Marketplace (requires VSCE_PAT env var)..."
	cd vscode-extension && npx @vscode/vsce publish --pat "$(VSCE_PAT)"
	@echo "✓ Published. Users can search 'ProjectMind' in the Extensions panel."

# ── GitHub Action ────────────────────────────────────────────────────────

publish-action:
	@test -n "$(VERSION)" || (echo "Usage: make publish-action VERSION=v1.0.0" && exit 1)
	git tag -a "$(VERSION)" -m "ProjectMind Health Gate $(VERSION)"
	git push origin "$(VERSION)"
	@echo "✓ Tag $(VERSION) pushed."
	@echo "  Go to: https://github.com/Aaravkhanal/llm-reviewer/releases"
	@echo "  Create a release from this tag and tick 'Publish this Action to Marketplace'."

# ── Cloud Deployment ─────────────────────────────────────────────────────

deploy-railway:
	@which railway > /dev/null 2>&1 || (echo "Install Railway CLI:  npm i -g @railway/cli" && exit 1)
	railway up --detach
	@echo "✓ Deployed. Set these env vars in Railway dashboard:"
	@echo "  GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET"
	@echo "  LLM_PROVIDER, API_KEY, CODE_MODEL"

deploy-fly:
	@which fly > /dev/null 2>&1 || (echo "Install flyctl:  curl -L https://fly.io/install.sh | sh" && exit 1)
	@test -f fly.toml || fly launch --no-deploy --name projectmind-api
	fly deploy
	@echo "✓ Deployed to Fly.io."

# ── Clean ────────────────────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ *.egg-info
	find . -name "*.pyc" -delete 2>/dev/null
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
