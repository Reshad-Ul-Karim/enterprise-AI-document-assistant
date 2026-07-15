"""Frontend wiring. Cheap, and it exists because a one-word mismatch killed the whole UI.

app.js called $("form"); index.html had renamed that element to id="composer". So
`$("form")` returned null, `.addEventListener` threw a TypeError, and init() died BEFORE
attaching the listeners for the tabs, login, logout and new-session. Every one of those
buttons was inert. The demo chips still worked -- they are wired up before the crash -- which
made it look like a single broken tab rather than a dead script.

Nothing server-side caught it: /, /static/app.js and /static/index.html all returned 200 with
the right bytes. Verifying that the markup is SERVED is not verifying that the script RUNS.
These tests close that gap without a browser.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS = (REPO / "static" / "app.js").read_text()
HTML = (REPO / "static" / "index.html").read_text()


def test_every_element_app_js_reaches_for_exists():
    """A single missing id throws inside init() and silently disables everything after it."""
    wanted = set(re.findall(r'\$\("([^"]+)"\)', JS))
    in_html = set(re.findall(r'id="([^"]+)"', HTML))
    built_at_runtime = set(re.findall(r'id="([^"]+)"', JS))  # rendered into innerHTML later

    missing = sorted(wanted - in_html - built_at_runtime)
    assert not missing, (
        f"app.js calls $({missing!r}) but no such id exists in index.html and none is built "
        "at runtime. This throws in init() and kills every listener registered after it."
    )


def test_the_controls_the_user_clicks_are_all_wired():
    """Each of these was dead when init() crashed. Assert both halves exist."""
    for element_id in ("tab-demo", "tab-notebook", "login-form", "logout", "new-session", "composer"):
        assert f'id="{element_id}"' in HTML, f"#{element_id} missing from index.html"
        assert f'$("{element_id}")' in JS, f"#{element_id} never wired up in app.js"


def test_the_logo_is_small_enough_to_ship():
    """The original was 1536x1024 and 2.3 MB -- larger than the entire app -- and would have
    been fetched on every page load of a 512 MB box."""
    logo = REPO / "static" / "logo.png"
    assert logo.exists()
    assert logo.stat().st_size < 120_000, f"logo is {logo.stat().st_size/1024:.0f} KB; crop/resize it"
    assert 'src="/static/logo.png"' in HTML


def test_markdown_is_escaped_before_it_is_parsed():
    """The renderer handles model output that quotes user-uploaded PDFs -- untrusted text.
    Escaping must happen FIRST; applying markdown to raw input is how renderers grow XSS."""
    body = JS[JS.index("function md(src)"):]
    body = body[: body.index("\n}")]
    assert "esc(src)" in body, "md() must escape before applying markdown"
