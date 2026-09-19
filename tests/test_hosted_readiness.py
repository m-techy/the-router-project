import pytest
from fastapi import HTTPException

import app.main as main


class FakeStore:
    def __init__(self, *, serverless_safe=True, vault=True, projects=1):
        self.backend_name = "postgres" if serverless_safe else "sqlite"
        self.durable = True
        self.serverless_safe = serverless_safe
        self._vault = vault
        self._projects = [{"id": "p"} for _ in range(projects)]

    def vault_status(self):
        return {
            "enabled": self._vault,
            "stored_secrets": 0,
            "encrypted_secrets": 0,
        }

    def list_projects(self):
        return list(self._projects)


def configure_hosted(monkeypatch, store):
    monkeypatch.setattr(main, "IS_VERCEL", True)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setenv("ROUTER_ADMIN_KEY", "admin")
    monkeypatch.setenv("ROUTER_REQUIRE_PROJECT_KEYS", "true")
    monkeypatch.setenv("ROUTER_ENABLE_HOSTED_API", "true")


def test_hosted_routing_requires_every_security_gate(monkeypatch):
    configure_hosted(monkeypatch, FakeStore())
    assert main.hosted_control_plane_ready() is True
    assert main.hosted_routing_ready() is True

    monkeypatch.delenv("ROUTER_ADMIN_KEY")
    assert main.hosted_control_plane_ready() is False
    assert main.hosted_routing_ready() is False

    monkeypatch.setenv("ROUTER_ADMIN_KEY", "admin")
    monkeypatch.setattr(main, "store", FakeStore(vault=False))
    assert main.hosted_routing_ready() is False

    monkeypatch.setattr(main, "store", FakeStore(serverless_safe=False))
    assert main.hosted_routing_ready() is False

    monkeypatch.setattr(main, "store", FakeStore(projects=0))
    assert main.hosted_routing_ready() is False

    monkeypatch.setattr(main, "store", FakeStore())
    monkeypatch.setenv("ROUTER_REQUIRE_PROJECT_KEYS", "false")
    assert main.hosted_routing_ready() is False

    monkeypatch.setenv("ROUTER_REQUIRE_PROJECT_KEYS", "true")
    monkeypatch.setenv("ROUTER_ENABLE_HOSTED_API", "false")
    assert main.hosted_routing_ready() is False


def test_hosted_admin_fails_closed_without_admin_key(monkeypatch):
    monkeypatch.setattr(main, "IS_VERCEL", True)
    monkeypatch.delenv("ROUTER_ADMIN_KEY", raising=False)

    with pytest.raises(HTTPException) as exc:
        main.require_admin(None)

    assert exc.value.status_code == 503


def test_hosted_routing_guard_rejects_unready_runtime(monkeypatch):
    configure_hosted(monkeypatch, FakeStore(projects=0))

    with pytest.raises(HTTPException) as exc:
        main.require_routing_runtime()

    assert exc.value.status_code == 503
    assert "fail-closed" in exc.value.detail


def test_local_routing_remains_enabled_without_hosted_flags(monkeypatch):
    monkeypatch.setattr(main, "IS_VERCEL", False)
    monkeypatch.delenv("ROUTER_ENABLE_HOSTED_API", raising=False)
    monkeypatch.delenv("ROUTER_REQUIRE_PROJECT_KEYS", raising=False)

    main.require_routing_runtime()
