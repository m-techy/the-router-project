from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ROUTE_PROFILE_SETTING = "route_profiles"
ROUTE_PROFILE_PREFIX = "route/"
BASE_ROUTES = {
    "free/auto",
    "free/fast",
    "free/smart",
    "free/code",
    "free/reasoning",
    "free/vision",
    "free/long",
}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class RouteProfile(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=80)
    base_route: Literal[
        "free/auto",
        "free/fast",
        "free/smart",
        "free/code",
        "free/reasoning",
        "free/vision",
        "free/long",
    ] = "free/auto"
    providers_allow: list[str] = Field(default_factory=list)
    providers_deny: list[str] = Field(default_factory=list)
    min_context: int | None = Field(default=None, ge=1)
    max_fallbacks: int = Field(default=8, ge=1, le=8)
    allow_promo: bool = False
    allow_trial: bool = False
    enabled: bool = True

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SLUG.fullmatch(value):
            raise ValueError(
                "slug must be 1-32 lowercase letters, numbers, or hyphens"
            )
        return value

    @field_validator("providers_allow", "providers_deny")
    @classmethod
    def dedupe_providers(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})


def load_route_profiles(store: Any) -> dict[str, RouteProfile]:
    raw = store.get_setting(ROUTE_PROFILE_SETTING, {})
    if not isinstance(raw, dict):
        return {}

    profiles: dict[str, RouteProfile] = {}
    for slug, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            profile = RouteProfile.model_validate({"slug": slug, **value})
        except ValueError:
            continue
        profiles[profile.slug] = profile
    return profiles


def save_route_profile(store: Any, profile: RouteProfile) -> None:
    profiles = load_route_profiles(store)
    profiles[profile.slug] = profile
    store.set_setting(
        ROUTE_PROFILE_SETTING,
        {
            slug: item.model_dump(exclude={"slug"})
            for slug, item in sorted(profiles.items())
        },
    )


def delete_route_profile(store: Any, slug: str) -> bool:
    profiles = load_route_profiles(store)
    if slug not in profiles:
        return False
    del profiles[slug]
    store.set_setting(
        ROUTE_PROFILE_SETTING,
        {
            key: item.model_dump(exclude={"slug"})
            for key, item in sorted(profiles.items())
        },
    )
    return True


def route_model_id(slug: str) -> str:
    return f"{ROUTE_PROFILE_PREFIX}{slug}"
