"""Local filesystem storage abstraction.

All methods return absolute Path objects. The interface is designed so that a
future S3-backed implementation can replace this class without changing callers.

Directory layout::

    {root}/manuscripts/{doi_suffix}/source/
    {root}/manuscripts/{doi_suffix}/output/prepare/
    {root}/manuscripts/{doi_suffix}/output/convert/
"""

from pathlib import Path


class Storage:
    def __init__(self, root: Path):
        self.root = root

    def manuscript_dir(self, doi_suffix: str) -> Path:
        return self.root / "manuscripts" / doi_suffix

    def source_dir(self, doi_suffix: str) -> Path:
        return self.manuscript_dir(doi_suffix) / "source"

    def prepare_output_dir(self, doi_suffix: str) -> Path:
        return self.manuscript_dir(doi_suffix) / "output" / "prepare"

    def convert_output_dir(self, doi_suffix: str) -> Path:
        return self.manuscript_dir(doi_suffix) / "output" / "convert"

    def output_zip(self, doi_suffix: str) -> Path | None:
        """Return the path to the output zip if it exists, else None."""
        d = self.convert_output_dir(doi_suffix)
        zips = list(d.glob("*.zip")) if d.exists() else []
        return zips[0] if zips else None

    def ensure_dirs(self, doi_suffix: str) -> None:
        """Create all subdirectories for a manuscript."""
        for d in [
            self.source_dir(doi_suffix),
            self.prepare_output_dir(doi_suffix),
            self.convert_output_dir(doi_suffix),
        ]:
            d.mkdir(parents=True, exist_ok=True)
