import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _id_selectors(js: str) -> set[str]:
    ids = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', js))
    ids.update(
        re.findall(
            r'document\.querySelector\("#([A-Za-z0-9_-]+)"\)',
            js,
        )
    )
    return ids


def test_dashboard_js_id_contract():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    missing = sorted(
        selector
        for selector in _id_selectors(js)
        if f'id="{selector}"' not in html
    )

    assert not missing, f"Dashboard JavaScript references missing HTML ids: {missing}"


def test_dashboard_navigation_targets_existing_views():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    targets = set(re.findall(r'data-view="([A-Za-z0-9_-]+)"', html))
    views = set(re.findall(r'<section id="([A-Za-z0-9_-]+)" class="view', html))

    assert targets
    assert targets <= views


def test_hosted_js_id_contract():
    html = (ROOT / "app" / "static" / "hosted.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "hosted.js").read_text(encoding="utf-8")

    missing = sorted(
        selector
        for selector in _id_selectors(js)
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


def test_taste_layout_has_no_cheap_meta_labels():
    combined = (
        (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        + (ROOT / "app" / "static" / "hosted.html").read_text(encoding="utf-8")
    ).upper()

    assert "SECTION 01" not in combined
    assert "SECTION 02" not in combined
    assert "QUESTION 0" not in combined


def test_public_bento_is_five_intentional_cards():
    html = (ROOT / "app" / "static" / "hosted.html").read_text(encoding="utf-8")
    block = html.split('<div class="system-bento">', 1)[1].split("</div>", 1)[0]
    # Use article class markers rather than visual text so copy can evolve safely.
    assert html.count('class="bento ') == 5



def test_dashboard_never_calls_foreach_on_single_selector_helper():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    bad = re.findall(r'(?<!\$)\$\("[^"]+"\)\.forEach', js)
    assert not bad, f"Use querySelectorAll/$$ for collections, found: {bad}"
