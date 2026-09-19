from app.main import app


def test_v04_openai_compatible_modality_routes_exist():
    paths = {route.path for route in app.routes}

    assert "/v1/chat/completions" in paths
    assert "/v1/embeddings" in paths
    assert "/v1/audio/transcriptions" in paths
    assert "/v1/models" in paths


def test_router_reports_v04_version():
    assert app.version == "0.4.0"
