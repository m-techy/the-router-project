from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Any

from pydantic import BaseModel, Field

from .state import StateStore


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    daily_request_limit: int | None = Field(default=None, ge=1)
    daily_token_limit: int | None = Field(default=None, ge=1)


def hash_project_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_project_key(store: StateStore, item: ProjectCreate) -> dict[str, Any]:
    project_id = f"proj_{uuid.uuid4().hex[:16]}"
    secret = f"rtr_{secrets.token_urlsafe(32)}"
    prefix = secret[:12]
    store.create_project(
        project_id,
        name=item.name.strip(),
        key_hash=hash_project_key(secret),
        key_prefix=prefix,
        daily_request_limit=item.daily_request_limit,
        daily_token_limit=item.daily_token_limit,
    )
    return {
        "id": project_id,
        "name": item.name.strip(),
        "key": secret,
        "key_prefix": prefix,
        "daily_request_limit": item.daily_request_limit,
        "daily_token_limit": item.daily_token_limit,
    }


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def authenticate_project(
    store: StateStore,
    authorization: str | None,
) -> dict[str, Any] | None:
    token = bearer_token(authorization)
    if not token or token == "local":
        return None

    project = store.get_project_by_hash(hash_project_key(token))
    if not project:
        return None

    # Compare the stored prefix too so malformed rows cannot accidentally authenticate.
    if not hmac.compare_digest(str(project["key_prefix"]), token[:12]):
        return None
    return project


def project_limit_state(
    store: StateStore,
    project: dict[str, Any],
) -> dict[str, Any]:
    usage = store.project_usage_today(str(project["id"]))
    request_limit = project.get("daily_request_limit")
    token_limit = project.get("daily_token_limit")
    return {
        "usage": usage,
        "daily_request_limit": request_limit,
        "daily_token_limit": token_limit,
        "request_limit_exhausted": (
            request_limit is not None and usage["requests"] >= int(request_limit)
        ),
        "token_limit_exhausted": (
            token_limit is not None and usage["tokens"] >= int(token_limit)
        ),
    }
