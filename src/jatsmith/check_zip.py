#!/usr/bin/env python3
"""Verify publisher-ready zip files before submission.

Checks:
1. Zip contains a folder <ID>/ with <ID>.pdf and <ID>.xml
2. The XML passes JATS Publishing 1.2 RelaxNG validation (via jing)
3. All images referenced in the XML are named <ID>* and present in the zip
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

JATS_RNG = (
    Path(__file__).parent.parent
    / "schema"
    / "jats-publishing-1.2-rng"
    / "JATS-journalpublishing1-mathml3.rng"
)

XLINK = "http://www.w3.org/1999/xlink"


def check_zip(zip_path: Path) -> list[str]:
    """Check a single zip file. Returns a list of error strings (empty = OK)."""
    errors: list[str] = []
    article_id = zip_path.stem

    if not zip_path.exists():
        return [f"File not found: {zip_path}"]

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        return [f"Not a valid zip file: {zip_path}"]

    names = zf.namelist()

    # --- Check 1: folder structure ---
    expected_pdf = f"{article_id}/{article_id}.pdf"
    expected_xml = f"{article_id}/{article_id}.xml"

    if expected_pdf not in names:
        errors.append(f"Missing {expected_pdf}")
    if expected_xml not in names:
        errors.append(f"Missing {expected_xml}")

    if expected_xml not in names:
        return errors  # can't do further checks without XML

    # --- Check 2: JATS RNG validation ---
    with tempfile.TemporaryDirectory() as tmpdir:
        zf.extractall(tmpdir)
        xml_path = Path(tmpdir) / expected_xml

        if not shutil.which("jing"):
            errors.append("jing not installed — cannot validate JATS schema")
        else:
            result = subprocess.run(
                ["jing", str(JATS_RNG), str(xml_path)],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines() + result.stderr.splitlines():
                if "error:" in line:
                    errors.append(f"Validation: {line}")

        # --- Check 3: image references ---
        tree = etree.parse(str(xml_path))
        image_refs: set[str] = set()
        for tag in ("graphic", "inline-graphic"):
            for el in tree.iter(tag):
                href = el.get(f"{{{XLINK}}}href")
                if href:
                    image_refs.add(href)

        zip_files = {Path(n).name for n in names}

        for ref in sorted(image_refs):
            if not ref.startswith(article_id):
                errors.append(f"Image '{ref}' does not match {article_id}* naming")
            if ref not in zip_files:
                errors.append(f"Image '{ref}' referenced in XML but missing from zip")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Verify publisher-ready zip files before submission."
    )
    parser.add_argument("zips", nargs="+", type=Path, help="Zip file(s) to check")
    args = parser.parse_args()

    all_ok = True
    for zip_path in args.zips:
        print(f"Checking {zip_path.name} ...")
        errors = check_zip(zip_path)
        if errors:
            all_ok = False
            for err in errors:
                print(f"  FAIL: {err}")
        else:
            print(f"  OK")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
