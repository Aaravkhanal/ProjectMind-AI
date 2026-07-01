"""
GitHub App webhook handler.

When users install the ProjectMind GitHub App on their repos, GitHub sends
webhook events here. We:
  1. Verify the webhook signature (GITHUB_WEBHOOK_SECRET)
  2. On pull_request (opened/synchronize): clone the repo, analyze it, post a review
  3. On push to default branch: update the health snapshot

Required env vars:
  GITHUB_APP_ID          — from your GitHub App settings
  GITHUB_APP_PRIVATE_KEY — PEM contents (or path) of the app's private key
  GITHUB_WEBHOOK_SECRET  — webhook secret set in GitHub App settings
  CODE_MODEL / LLM_PROVIDER / API_KEY — for the review LLM

This endpoint is PUBLIC — it only accepts calls from GitHub (verified by HMAC).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github-app", tags=["github-app"])

_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# Webhook entry point
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    body = await request.body()

    # ── Verify signature ──────────────────────────────────────────────────
    if _WEBHOOK_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")
        expected = "sha256=" + hmac.new(
            _WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = x_github_event or "unknown"
    action = payload.get("action", "")
    logger.info("GitHub App webhook: event=%s action=%s", event, action)

    # ── Route events ──────────────────────────────────────────────────────
    if event == "pull_request" and action in ("opened", "synchronize", "reopened"):
        background_tasks.add_task(_handle_pr_review, payload)
        return JSONResponse({"status": "accepted", "event": "pr_review_queued"})

    if event == "push" and payload.get("ref", "").startswith("refs/heads/"):
        background_tasks.add_task(_handle_push_analysis, payload)
        return JSONResponse({"status": "accepted", "event": "push_analysis_queued"})

    if event == "ping":
        return JSONResponse({"status": "ok", "message": "ProjectMind webhook active"})

    return JSONResponse({"status": "ignored", "event": event, "action": action})


# ---------------------------------------------------------------------------
# PR review handler
# ---------------------------------------------------------------------------

def _handle_pr_review(payload: dict) -> None:
    pr     = payload.get("pull_request", {})
    repo   = payload.get("repository", {})
    owner  = repo.get("owner", {}).get("login", "")
    name   = repo.get("name", "")
    pr_num = pr.get("number")
    clone_url = repo.get("clone_url", "")
    head_sha  = pr.get("head", {}).get("sha", "")
    base_ref  = pr.get("base", {}).get("ref", "main")
    head_ref  = pr.get("head", {}).get("ref", "")

    if not all([owner, name, pr_num, clone_url]):
        logger.error("Incomplete PR payload — skipping")
        return

    logger.info("Starting PR review: %s/%s#%d", owner, name, pr_num)
    token = _get_installation_token(payload)
    if not token:
        logger.error("Could not obtain installation token")
        return

    tmpdir = tempfile.mkdtemp(prefix="projectmind-")
    try:
        # Clone the head branch
        auth_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
        subprocess.run(
            ["git", "clone", "--depth=50", "--branch", head_ref, auth_url, tmpdir],
            check=True, capture_output=True, timeout=120,
        )

        # Get the diff against base
        diff = _get_pr_diff(owner, name, pr_num, token)

        # Run multi-agent review on the diff
        review_comment = _run_review(diff, tmpdir)

        # Post comment to PR
        _post_pr_comment(owner, name, pr_num, token, review_comment)

        # Run health analysis and post health summary
        health_comment = _run_health_analysis(tmpdir, owner, name, pr_num)
        if health_comment:
            _post_pr_comment(owner, name, pr_num, token, health_comment, tag="<!-- projectmind-health -->")

        logger.info("PR review complete: %s/%s#%d", owner, name, pr_num)

    except subprocess.CalledProcessError as e:
        logger.error("Clone/git failed: %s", e.stderr)
    except Exception as e:
        logger.exception("PR review failed: %s", e)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _handle_push_analysis(payload: dict) -> None:
    repo      = payload.get("repository", {})
    owner     = repo.get("owner", {}).get("login", "")
    name      = repo.get("name", "")
    clone_url = repo.get("clone_url", "")
    ref       = payload.get("ref", "").replace("refs/heads/", "")

    if not all([owner, name, clone_url]):
        return

    logger.info("Push analysis: %s/%s @ %s", owner, name, ref)
    token = _get_installation_token(payload)
    if not token:
        return

    tmpdir = tempfile.mkdtemp(prefix="projectmind-push-")
    try:
        auth_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
        subprocess.run(
            ["git", "clone", "--depth=10", "--branch", ref, auth_url, tmpdir],
            check=True, capture_output=True, timeout=120,
        )
        _run_health_analysis(tmpdir, owner, name, pr_num=None)
    except Exception as e:
        logger.exception("Push analysis failed: %s", e)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Core analysis helpers
# ---------------------------------------------------------------------------

def _run_review(diff: str, project_dir: str) -> str:
    """Run multi-agent review on a diff, return formatted markdown."""
    if not diff:
        return "<!-- projectmind-review -->\n_No diff available for review._"

    llm_provider = os.environ.get("LLM_PROVIDER", "openai")
    api_key = os.environ.get("API_KEY", "")
    model = os.environ.get("CODE_MODEL", "gpt-4o-mini")

    try:
        from backend.agents.graph import run_review
        result = run_review(
            diff=diff,
            llm_provider=llm_provider,
            api_key=api_key,
            model_name=model,
        )
        body = result.get("final_review", "")
        return f"<!-- projectmind-review -->\n{body}"
    except Exception as e:
        logger.error("Multi-agent review failed: %s", e)
        return f"<!-- projectmind-review -->\n_Review failed: {e}_"


def _run_health_analysis(
    project_dir: str,
    owner: str,
    name: str,
    pr_num: Optional[int],
) -> Optional[str]:
    """Run health analysis on the cloned repo, return a PR comment or None."""
    try:
        from backend.core.analyzer.ast_parser import ProjectParser
        from backend.core.analyzer.dependency import DependencyAnalyzer
        from backend.core.analyzer.duplicates import DuplicateAnalyzer
        from backend.core.analyzer.dead_code import DeadCodeAnalyzer
        from backend.core.analyzer.security import SecurityScanner
        from backend.core.analyzer.reporter import Reporter

        parser = ProjectParser(project_dir)
        analyses = parser.parse()
        if not analyses:
            return None

        dep    = DependencyAnalyzer(analyses).analyze()
        dup    = DuplicateAnalyzer(analyses).analyze()
        dead   = DeadCodeAnalyzer(analyses, dep).analyze()
        sec    = SecurityScanner(project_dir).scan()
        rep    = Reporter(project_dir, "python", analyses, dep, dup, dead, sec)
        report = rep.build()
        health = report.health

        from backend.ci.gate import format_pr_comment, GateResult
        gate = GateResult(
            passed=health.overall >= 6.0 and health.security >= 7.0,
            violations=[],
            health={
                "overall":         health.overall,
                "architecture":    health.architecture,
                "security":        health.security,
                "maintainability": health.maintainability,
                "code_quality":    health.code_quality,
                "breakdown":       health.breakdown,
            },
        )
        if health.overall < 6.0:
            gate.violations.append(f"Overall score {health.overall:.1f} < 6.0 (threshold)")
        if health.security < 7.0:
            gate.violations.append(f"Security score {health.security:.1f} < 7.0 (threshold)")

        return format_pr_comment(gate, f"{owner}/{name}")
    except Exception as e:
        logger.warning("Health analysis skipped: %s", e)
        return None


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def _get_installation_token(payload: dict) -> Optional[str]:
    """Exchange GitHub App credentials for a short-lived installation token."""
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        # Fall back to a plain GITHUB_TOKEN if set (for simpler setups)
        return os.environ.get("GITHUB_TOKEN") or None

    app_id   = os.environ.get("GITHUB_APP_ID", "")
    pem_val  = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
    if not app_id or not pem_val:
        return os.environ.get("GITHUB_TOKEN") or None

    try:
        import time, jwt as _jwt  # type: ignore[import]
        pem = pem_val if pem_val.startswith("-----") else Path(pem_val).read_text()
        now = int(time.time())
        payload_jwt = {"iat": now - 60, "exp": now + 600, "iss": app_id}
        app_token = _jwt.encode(payload_jwt, pem, algorithm="RS256")

        import urllib.request, json as _json
        req = urllib.request.Request(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            data=b"{}",
            headers={
                "Authorization": f"Bearer {app_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read()).get("token")
    except ImportError:
        logger.warning("PyJWT not installed — falling back to GITHUB_TOKEN")
        return os.environ.get("GITHUB_TOKEN") or None
    except Exception as e:
        logger.error("Failed to get installation token: %s", e)
        return os.environ.get("GITHUB_TOKEN") or None


def _get_pr_diff(owner: str, repo: str, pr_num: int, token: str) -> str:
    try:
        from backend.git.github import GitHubClient
        return GitHubClient(token=token).get_diff(owner, repo, pr_num)
    except Exception as e:
        logger.warning("Could not fetch diff: %s", e)
        return ""


def _post_pr_comment(
    owner: str, repo: str, pr_num: int, token: str,
    body: str, tag: str = "<!-- projectmind-review -->",
) -> None:
    try:
        from backend.git.github import GitHubClient
        client = GitHubClient(token=token)
        # Inject the tag so the client's idempotent logic finds and updates it
        if tag not in body:
            body = f"{tag}\n{body}"
        client.write_comment(owner, repo, pr_num, body.replace(tag, "").strip())
    except Exception as e:
        logger.error("Failed to post PR comment: %s", e)
