import shutil
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires latexmlc installed")

    # Pin a default AuthConfig for the whole test session so individual tests
    # don't have to set EDITOR_CREDENTIALS in their environment. Files that
    # need different values (e.g. test_web_api.py, test_upstream.py) still
    # override via their own autouse fixtures — function-scoped fixtures run
    # after this, so their overrides win.
    try:
        from web.backend.app.config import AuthConfig, set_for_tests
    except ImportError:
        # Web extras not installed (e.g. pure-converter test runs) — nothing
        # reads config in that case.
        return

    set_for_tests(AuthConfig(
        editor_credentials={"editor": "testpass"},
        frontend_url="http://testserver",
        ojs_base_url="https://ojs",
        ojs_journal_path="ccr",
        ojs_admin_token="",
        ojs_doi_prefix="10.5117/",
        session_token_ttl_days=30,
    ))


@pytest.fixture
def xml_file(tmp_path):
    """Write an XML string to a temp file and return the path."""
    def _write(content: str):
        p = tmp_path / "input.xml"
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _write


def pytest_collection_modifyitems(config, items):
    """Skip integration tests if latexmlc is not on PATH."""
    if shutil.which("latexmlc") is None:
        skip = pytest.mark.skip(reason="latexmlc not installed")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)
