from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_ui_implements_required_accessible_states_and_tokens():
    css = (ROOT / "app/static/styles.css").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    for token in ("--background:#fff", "--accent:#1d4ed8", "prefers-reduced-motion"):
        assert token in css
    for marker in ("aria-live", "Knowledge Base", "Upload documents", "source-dialog"):
        assert marker in html
