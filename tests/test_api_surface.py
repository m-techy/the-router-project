from app.main import app


def test_v04_openai_compatible_modality_routes_exist():
    paths = {route.path for route in app.routes}

    assert "/v1/chat/completions" in paths
    assert "/v1/embeddings" in paths
    assert "/v1/audio/transcriptions" in paths
    assert "/v1/models" in paths
    assert "/api/events" in paths
    assert "/api/projects" in paths
    assert "/api/config/export" in paths
    assert "/api/config/import" in paths
    assert "/api/vault/status" in paths
    assert "/api/adapters" in paths
    assert "/api/hosted/readiness" in paths
    assert "/api/doctor" in paths
    assert "/api/routes" in paths
    assert "/v1/images/generations" in paths
    assert "/v1/responses" in paths


def test_router_reports_v08_version():
    assert app.version == "0.8.0"
