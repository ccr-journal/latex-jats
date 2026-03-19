import shutil
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires latexmlc installed")


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
