import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from jatsmith.convert import _flatten_raster_alpha

XLINK = "http://www.w3.org/1999/xlink"


def _write_jats(tmp_path: Path, href: str) -> Path:
    xml_path = tmp_path / "article.xml"
    xml_path.write_text(
        f'<article xmlns:xlink="{XLINK}">'
        f'<body><fig><graphic xlink:href="{href}"/></fig></body>'
        f"</article>",
        encoding="utf-8",
    )
    return xml_path


def _semi_transparent_rgba(size=(4, 4), rgb=(10, 20, 30), alpha=64) -> Image.Image:
    return Image.new("RGBA", size, (*rgb, alpha))


def test_flattens_rgba_png_onto_white(tmp_path):
    png = tmp_path / "fig.png"
    _semi_transparent_rgba(alpha=64).save(png, format="PNG")
    xml_path = _write_jats(tmp_path, "fig.png")

    _flatten_raster_alpha(str(xml_path))

    with Image.open(png) as out:
        assert out.mode == "RGB"
        r, g, b = out.getpixel((0, 0))
        # alpha=64/255 over white (255): channel ≈ src*a + 255*(1-a)
        # for rgb=(10,20,30), a=64/255: roughly (194, 197, 201) — much lighter than src
        assert r > 150 and g > 150 and b > 150


def test_fully_opaque_png_left_unchanged(tmp_path):
    png = tmp_path / "fig.png"
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(png, format="PNG")
    xml_path = _write_jats(tmp_path, "fig.png")
    mtime_before = png.stat().st_mtime_ns

    _flatten_raster_alpha(str(xml_path))

    assert png.stat().st_mtime_ns == mtime_before


def test_rgb_png_without_alpha_untouched(tmp_path):
    png = tmp_path / "fig.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(png, format="PNG")
    xml_path = _write_jats(tmp_path, "fig.png")
    mtime_before = png.stat().st_mtime_ns

    _flatten_raster_alpha(str(xml_path))

    assert png.stat().st_mtime_ns == mtime_before


def test_palette_png_with_trns_flattened(tmp_path):
    png = tmp_path / "fig.png"
    base = Image.new("RGBA", (4, 4), (10, 20, 30, 0))
    base.convert("P").save(png, format="PNG", transparency=0)
    xml_path = _write_jats(tmp_path, "fig.png")

    _flatten_raster_alpha(str(xml_path))

    with Image.open(png) as out:
        rgb = out.convert("RGB")
        assert rgb.getpixel((0, 0)) == (255, 255, 255)


def test_gif_with_transparency_flattened(tmp_path):
    gif = tmp_path / "fig.gif"
    Image.new("RGBA", (4, 4), (10, 20, 30, 0)).convert("P").save(
        gif, format="GIF", transparency=0
    )
    xml_path = _write_jats(tmp_path, "fig.gif")

    _flatten_raster_alpha(str(xml_path))

    with Image.open(gif) as out:
        assert out.format == "GIF"
        rgb = out.convert("RGB")
        assert rgb.getpixel((0, 0)) == (255, 255, 255)


def test_idempotent(tmp_path):
    png = tmp_path / "fig.png"
    _semi_transparent_rgba(alpha=64).save(png, format="PNG")
    xml_path = _write_jats(tmp_path, "fig.png")

    _flatten_raster_alpha(str(xml_path))
    mtime_after_first = png.stat().st_mtime_ns
    _flatten_raster_alpha(str(xml_path))

    assert png.stat().st_mtime_ns == mtime_after_first


def test_missing_file_is_tolerated(tmp_path):
    xml_path = _write_jats(tmp_path, "nope.png")
    _flatten_raster_alpha(str(xml_path))


def test_http_href_skipped(tmp_path):
    xml_path = _write_jats(tmp_path, "https://example.org/fig.png")
    _flatten_raster_alpha(str(xml_path))


def test_xml_untouched(tmp_path):
    png = tmp_path / "fig.png"
    _semi_transparent_rgba(alpha=64).save(png, format="PNG")
    xml_path = _write_jats(tmp_path, "fig.png")
    xml_before = xml_path.read_bytes()

    _flatten_raster_alpha(str(xml_path))

    assert xml_path.read_bytes() == xml_before
    root = ET.parse(xml_path).getroot()
    assert root.find(".//graphic").get(f"{{{XLINK}}}href") == "fig.png"
