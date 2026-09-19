import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _direct_id_selectors(js: str) -> set[str]:
    return set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', js))


def test_dashboard_js_id_contract():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    missing = sorted(
        selector
        for selector in _direct_id_selectors(js)
        if f'id="{selector}"' not in html
    )

    assert not missing, f"Dashboard JavaScript references missing HTML ids: {missing}"


def test_hosted_js_id_contract():
    html = (ROOT / "app" / "static" / "hosted.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "hosted.js").read_text(encoding="utf-8")

    missing = sorted(
        selector
        for selector in _direct_id_selectors(js)
        if f'id="{selector}"' not in html
    )

    assert not missing, f"Hosted JavaScript references missing HTML ids: {missing}"


def test_dashboard_loads_functional_script_before_optional_motion():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert html.index('/static/app.js') < html.index('gsap.min.js')
    assert '/static/motion.js' in html


def test_hosted_page_loads_controls_before_optional_motion():
    html = (ROOT / "app" / "static" / "hosted.html").read_text(encoding="utf-8")
    assert html.index('/static/hosted.js') < html.index('gsap.min.js')
    assert '/static/motion.js' in html
