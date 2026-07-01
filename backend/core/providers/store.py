"""
ProviderStore — encrypted BYOK API key management.

Uses Fernet symmetric encryption. The encryption key is derived from a
project-specific secret stored in .projectmind/secret.key (never committed).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.providers.schema import ModelProfile, ProviderKey, PROVIDER_METADATA


def _fernet():
    from cryptography.fernet import Fernet
    secret_path = Path(os.environ.get("SECRET_KEY_PATH", ".projectmind/secret.key"))
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if not secret_path.exists():
        secret_path.write_bytes(Fernet.generate_key())
        secret_path.chmod(0o600)
    return Fernet(secret_path.read_bytes())


class ProviderStore:
    def __init__(self, db_path: str):
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    # ── Key management ─────────────────────────────────────────────────────

    def add_provider(
        self,
        project_path: str,
        provider: str,
        api_key: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> ProviderKey:
        encrypted = None
        if api_key:
            encrypted = _fernet().encrypt(api_key.encode()).decode()

        with Session(self._engine) as session:
            existing = session.exec(
                select(ProviderKey).where(
                    ProviderKey.project_path == project_path,
                    ProviderKey.provider == provider,
                )
            ).first()

            if existing:
                if encrypted:
                    existing.encrypted_key = encrypted
                if base_url_override:
                    existing.base_url_override = base_url_override
                existing.is_active = True
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = ProviderKey(
                project_path=project_path,
                provider=provider,
                encrypted_key=encrypted,
                base_url_override=base_url_override,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_api_key(self, project_path: str, provider: str) -> Optional[str]:
        """Return decrypted API key, or None if not configured."""
        with Session(self._engine) as session:
            record = session.exec(
                select(ProviderKey).where(
                    ProviderKey.project_path == project_path,
                    ProviderKey.provider == provider,
                    ProviderKey.is_active == True,  # noqa: E712
                )
            ).first()

        if not record or not record.encrypted_key:
            # Fall back to environment variable
            meta = PROVIDER_METADATA.get(provider, {})
            env_key = meta.get("key_env")
            return os.environ.get(env_key, "") if env_key else None

        return _fernet().decrypt(record.encrypted_key.encode()).decode()

    def remove_provider(self, project_path: str, provider: str) -> bool:
        with Session(self._engine) as session:
            record = session.exec(
                select(ProviderKey).where(
                    ProviderKey.project_path == project_path,
                    ProviderKey.provider == provider,
                )
            ).first()
            if not record:
                return False
            record.is_active = False
            record.updated_at = datetime.utcnow()
            session.add(record)
            session.commit()
            return True

    def list_providers(self, project_path: str) -> list[dict]:
        with Session(self._engine) as session:
            records = list(session.exec(
                select(ProviderKey).where(
                    ProviderKey.project_path == project_path,
                    ProviderKey.is_active == True,  # noqa: E712
                )
            ))

        # Also include env-configured providers not yet in DB
        configured = {r.provider for r in records}
        env_providers = []
        for prov, meta in PROVIDER_METADATA.items():
            if prov not in configured:
                env_key = meta.get("key_env")
                if env_key and os.environ.get(env_key):
                    env_providers.append(prov)

        result = []
        for r in records:
            meta = PROVIDER_METADATA.get(r.provider, {})
            result.append({
                "provider":      r.provider,
                "label":         meta.get("label", r.provider),
                "has_key":       bool(r.encrypted_key),
                "base_url":      r.base_url_override or meta.get("base_url"),
                "health_status": r.health_status,
                "health_message":r.health_message,
                "last_tested":   r.last_tested_at.isoformat() if r.last_tested_at else None,
                "models":        json.loads(r.available_models_json) if r.available_models_json else meta.get("models", []),
                "source":        "database",
            })

        for prov in env_providers:
            meta = PROVIDER_METADATA.get(prov, {})
            result.append({
                "provider":      prov,
                "label":         meta.get("label", prov),
                "has_key":       True,
                "base_url":      meta.get("base_url"),
                "health_status": "untested",
                "last_tested":   None,
                "models":        meta.get("models", []),
                "source":        "environment",
            })

        return result

    def update_health(
        self,
        project_path: str,
        provider: str,
        status: str,
        message: str = "",
        available_models: Optional[list[str]] = None,
    ) -> None:
        with Session(self._engine) as session:
            record = session.exec(
                select(ProviderKey).where(
                    ProviderKey.project_path == project_path,
                    ProviderKey.provider == provider,
                )
            ).first()
            if not record:
                record = ProviderKey(project_path=project_path, provider=provider)
                session.add(record)

            record.health_status = status
            record.health_message = message
            record.last_tested_at = datetime.utcnow()
            if available_models is not None:
                record.available_models_json = json.dumps(available_models)
            record.updated_at = datetime.utcnow()
            session.add(record)
            session.commit()

    # ── Model profiles ─────────────────────────────────────────────────────

    def save_profile(self, profile: ModelProfile) -> None:
        with Session(self._engine) as session:
            existing = session.exec(
                select(ModelProfile).where(
                    ModelProfile.project_path == profile.project_path,
                    ModelProfile.model_id == profile.model_id,
                )
            ).first()
            if existing:
                for field in ModelProfile.model_fields:
                    if field not in ("id", "created_at"):
                        setattr(existing, field, getattr(profile, field))
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                session.add(profile)
            session.commit()

    def get_best_model_for_task(self, project_path: str, task: str) -> Optional[str]:
        """Return model_id with highest score for given task type."""
        score_field = f"score_{task}"
        with Session(self._engine) as session:
            profiles = list(session.exec(
                select(ModelProfile).where(ModelProfile.project_path == project_path)
            ))

        best = None
        best_score = -1.0
        for p in profiles:
            score = getattr(p, score_field, None)
            if score is not None and score > best_score:
                best_score = score
                best = p.model_id
        return best

    def get_recommendations(self, project_path: str) -> dict:
        """Return task → best/cheapest/fastest model mapping."""
        tasks = ["code_review", "architecture", "security", "documentation",
                 "bug_fix", "testing", "refactor", "reasoning"]
        with Session(self._engine) as session:
            profiles = list(session.exec(
                select(ModelProfile).where(ModelProfile.project_path == project_path)
            ))

        if not profiles:
            return {}

        recommendations: dict[str, dict] = {}
        for task in tasks:
            score_field = f"score_{task}"
            scored = [(p, getattr(p, score_field, None)) for p in profiles if getattr(p, score_field) is not None]
            if not scored:
                continue

            best    = max(scored, key=lambda x: x[1])
            cheapest = min(profiles, key=lambda p: (p.cost_per_1k_input or 999))
            fastest  = min(profiles, key=lambda p: (p.avg_latency_ms or 999999))

            recommendations[task] = {
                "best":     best[0].model_id,
                "cheapest": cheapest.model_id,
                "fastest":  fastest.model_id,
            }

        return recommendations
