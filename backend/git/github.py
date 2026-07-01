import os
from typing import Optional

from github import Github, GithubException


_PROJECTMIND_TAG = "<!-- projectmind-review -->"


class GitHubClient:
    def __init__(self, token: str, base_url: Optional[str] = None):
        url = base_url or os.environ.get("GITHUB_BASE_URL", "https://api.github.com")
        if url == "https://api.github.com":
            self._gh = Github(login_or_token=token)
        else:
            # GitHub Enterprise
            self._gh = Github(login_or_token=token, base_url=url)

    def get_diff(self, owner: str, repo: str, pr_number: int) -> str:
        try:
            r = self._gh.get_repo(f"{owner}/{repo}")
            pr = r.get_pull(pr_number)
        except GithubException as e:
            raise RuntimeError(
                f"GitHub API error: {e.status} — {e.data.get('message', e)}"
            ) from e

        parts = []
        for f in pr.get_files():
            patch = f.patch or "(binary or empty)"
            parts.append(f"File: {f.filename}\n{patch}")

        if not parts:
            raise RuntimeError(f"PR #{pr_number} has no file changes.")

        return "\n\n".join(parts)

    def write_comment(
        self, owner: str, repo: str, pr_number: int, comment: str
    ) -> None:
        try:
            r = self._gh.get_repo(f"{owner}/{repo}")
            pr = r.get_pull(pr_number)
        except GithubException as e:
            raise RuntimeError(
                f"GitHub API error fetching PR: {e.status} — {e.data.get('message', e)}"
            ) from e

        body = f"{_PROJECTMIND_TAG}\n{comment}"

        # Update existing ProjectMind comment rather than creating duplicates
        for existing in pr.get_issue_comments():
            if _PROJECTMIND_TAG in existing.body:
                existing.edit(body)
                return

        pr.create_issue_comment(body)

    def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        """Return title + description for context enrichment."""
        r = self._gh.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        return {
            "title": pr.title,
            "description": pr.body or "",
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "changed_files": pr.changed_files,
            "additions": pr.additions,
            "deletions": pr.deletions,
        }
