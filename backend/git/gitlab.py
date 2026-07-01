import os
from typing import Optional

import gitlab
from gitlab.exceptions import GitlabAuthenticationError


class GitLabClient:
    def __init__(self, token: str, url: Optional[str] = None):
        base_url = url or os.environ.get("GIT_BASE_URL", "https://gitlab.com")
        self._gl = gitlab.Gitlab(url=base_url, private_token=token)

    def _auth(self):
        try:
            self._gl.auth()
        except GitlabAuthenticationError as e:
            raise RuntimeError(
                "GitLab authentication failed: check that the token has api or read_api scope."
            ) from e

    def get_diff(self, project_id: str | int, merge_request_iid: int) -> str:
        self._auth()
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(merge_request_iid)
        changes = mr.changes()
        parts = []
        for change in changes["changes"]:
            path = change.get("new_path") or change.get("old_path", "unknown")
            parts.append(f"File: {path}\n{change['diff']}")
        return "\n\n".join(parts)

    def write_comment(
        self, project_id: str | int, merge_request_iid: str | int, comment: str
    ):
        self._auth()
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(merge_request_iid)

        existing_note_id: Optional[int] = None
        for discussion in mr.discussions.list():
            for note in discussion.attributes.get("notes", []):
                if "Code Review Documentation" in note.get("body", ""):
                    existing_note_id = note.get("id")
                    break

        if existing_note_id is None:
            mr.notes.create({"body": comment})
        else:
            mr.notes.update(id=existing_note_id, new_data={"body": comment})
