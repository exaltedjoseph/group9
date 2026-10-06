from __future__ import annotations

import json

import pytest

from app.core.extract import extract_text, guess_mime, human_size, is_image
from tests.conftest import make_zip


def _write(tmp_path, name, content):
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _minimal_pdf(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 18 Tf", "72 720 Td", "22 TL"]
    for line in lines:
        ops.append(f"({line}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_txt_and_whitespace_cleanup(tmp_path):
    p = _write(tmp_path, "a.txt", "Hello   world\t\tagain\r\n\r\n\r\n\r\nNext   line  \n")
    assert extract_text(p) == "Hello world again\n\nNext line"


def test_markdown(tmp_path):
    p = _write(tmp_path, "notes.md", "# Loops\n\n- for\n- while\n")
    assert extract_text(p) == "# Loops\n\n- for\n- while"


def test_cp1252_fallback(tmp_path):
    p = _write(tmp_path, "legacy.txt", "Caf\xe9 \x93quoted\x94".encode("latin-1"))
    assert extract_text(p) == "Caf\u00e9 \u201cquoted\u201d"


def test_utf8_bom_and_utf16(tmp_path):
    p = _write(tmp_path, "bom.csv", b"\xef\xbb\xbfname,score\nAna,9\n")
    assert extract_text(p) == "name,score\nAna,9"
    q = _write(tmp_path, "wide.txt", "Unicode \u2713".encode("utf-16"))
    assert extract_text(q) == "Unicode \u2713"


def test_max_chars(tmp_path):
    p = _write(tmp_path, "long.txt", "abcdefghij" * 1000)
    assert extract_text(p, max_chars=25) == "abcdefghij" * 2 + "abcde"


def test_html_strips_tags_scripts_and_entities(tmp_path):
    p = _write(tmp_path, "page.html", "<html><head><style>p{color:red}</style><script>var x=1;</script></head>"
                                      "<body><h1>Title</h1><p>Fish &amp; chips<br>today</p><!-- hidden --></body></html>")
    text = extract_text(p)
    assert "Title" in text and "Fish & chips" in text and "today" in text
    assert "color" not in text and "var x" not in text and "<" not in text and "hidden" not in text


def test_code_files(tmp_path):
    p = _write(tmp_path, "main.py", "def add(a, b):\n    return a + b\n")
    assert "return a + b" in extract_text(p)
    s = _write(tmp_path, "q.sql", "SELECT * FROM users;")
    assert extract_text(s) == "SELECT * FROM users;"


def test_ipynb_cell_sources(tmp_path):
    nb = {"cells": [{"cell_type": "markdown", "source": ["# Intro\n", "Pandas basics"]},
                    {"cell_type": "code", "source": "import pandas as pd", "outputs": [{"text": "noise"}]}],
          "metadata": {}, "nbformat": 4}
    p = _write(tmp_path, "nb.ipynb", json.dumps(nb))
    text = extract_text(p)
    assert "Pandas basics" in text and "import pandas as pd" in text and "noise" not in text


def test_rtf(tmp_path):
    rtf = (r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}{\colortbl;\red0\green0\blue0;}"
           r"{\*\generator Riched20;}\f0\fs24 Hello \b bold\b0  world\par Caf\'e9 \u8211? dash\par}")
    p = _write(tmp_path, "doc.rtf", rtf)
    text = extract_text(p)
    assert "Hello bold world" in text
    assert "Caf\u00e9 \u2013 dash" in text
    assert "Arial" not in text and "Riched20" not in text and "\\" not in text


def test_docx(tmp_path):
    doc = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:r><w:t>Variables &amp; types</w:t></w:r></w:p>'
           '<w:p><w:r><w:t xml:space="preserve">Second </w:t></w:r><w:r><w:t>paragraph</w:t></w:r>'
           '<w:r><w:br/><w:t>after break</w:t></w:r></w:p>'
           '</w:body></w:document>')
    p = make_zip(tmp_path / "doc.docx", {"[Content_Types].xml": "<Types/>", "word/document.xml": doc})
    assert extract_text(p) == "Variables & types\nSecond paragraph\nafter break"


def _slide(*paras: str) -> str:
    body = "".join(f"<a:p><a:r><a:rPr lang=\"en\"/><a:t>{t}</a:t></a:r></a:p>" for t in paras)
    return ('<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f"<p:cSld><p:spTree><p:sp><p:txBody>{body}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")


def test_pptx_slides_in_numeric_order(tmp_path):
    members = {
        "ppt/slides/slide10.xml": _slide("Ten"),
        "ppt/slides/slide2.xml": _slide("Two", "Bullet &lt;b&gt;"),
        "ppt/slides/slide1.xml": _slide("One"),
        "ppt/slides/_rels/slide1.xml.rels": "<Relationships/>",
        "ppt/slideLayouts/slideLayout1.xml": _slide("Layout text"),
    }
    p = make_zip(tmp_path / "deck.pptx", members)
    assert extract_text(p) == "One\n\nTwo\nBullet <b>\n\nTen"


def test_xlsx_shared_and_inline_strings(tmp_path):
    shared = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<si><t>Name</t></si><si><r><t>Rich </t></r><r><t>text</t></r></si></sst>')
    sheet = ('<worksheet><sheetData><row><c t="inlineStr"><is><t>Inline cell</t></is></c>'
             '<c><v>42</v></c></row></sheetData></worksheet>')
    p = make_zip(tmp_path / "book.xlsx", {"xl/sharedStrings.xml": shared, "xl/worksheets/sheet1.xml": sheet})
    assert extract_text(p) == "Name\nRich text\nInline cell"


def test_odt_and_odp(tmp_path):
    content = ('<office:document-content xmlns:office="o" xmlns:text="t"><office:body><office:text>'
               '<text:h>Heading</text:h><text:p>Para<text:s/>one<text:tab/>tab</text:p>'
               '<text:p>Line<text:line-break/>two</text:p></office:text></office:body></office:document-content>')
    p = make_zip(tmp_path / "doc.odt", {"mimetype": "application/vnd.oasis.opendocument.text",
                                        "content.xml": content})
    assert extract_text(p) == "Heading\nPara one tab\nLine\ntwo"
    slides = ('<office:document-content xmlns:draw="d" xmlns:text="t"><draw:page><text:p>Slide A</text:p>'
              '</draw:page><draw:page><text:p>Slide B</text:p></draw:page></office:document-content>')
    q = make_zip(tmp_path / "deck.odp", {"content.xml": slides})
    assert extract_text(q) == "Slide A\n\nSlide B"


def test_pdf(tmp_path):
    p = _write(tmp_path, "intro.pdf", _minimal_pdf(["Hello PDF world", "Second line"]))
    text = extract_text(p)
    assert "Hello PDF world" in text and "Second line" in text


def test_never_raises(tmp_path):
    assert extract_text(tmp_path / "missing.txt") == ""
    assert extract_text(tmp_path) == ""
    assert extract_text(_write(tmp_path, "broken.docx", b"not a zip")) == ""
    assert extract_text(_write(tmp_path, "broken.pdf", b"%PDF-1.4 garbage")) == ""
    assert extract_text(make_zip(tmp_path / "empty.pptx", {"x.xml": "<x/>"})) == ""
    assert extract_text(_write(tmp_path, "photo.png", b"\x89PNG\r\n\x1a\n")) == ""
    assert extract_text(_write(tmp_path, "data.bin", b"\x00\x01\x02")) == ""
    assert extract_text("not/a/real/path.md") == ""


@pytest.mark.parametrize("name, mime", [
    ("a.pdf", "application/pdf"), ("a.PNG", "image/png"), ("a.jpg", "image/jpeg"), ("a.md", "text/markdown"),
    ("a.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("a.unknownext", "application/octet-stream"), ("noext", "application/octet-stream"),
])
def test_guess_mime(name, mime):
    assert guess_mime(name) == mime


def test_is_image():
    assert is_image("a.PNG") and is_image("b.jpeg") and is_image("c.webp")
    assert not is_image("d.pdf") and not is_image("e")


@pytest.mark.parametrize("n, text", [
    (0, "Zero bytes"), (1, "1 byte"), (512, "512 bytes"), (999, "999 bytes"), (1000, "1 KB"), (1499, "1 KB"),
    (12_345, "12 KB"), (999_499, "999 KB"), (999_999, "1 MB"), (1_234_567, "1.2 MB"), (2_000_000, "2 MB"),
    (15_960_000, "16 MB"), (3_210_000_000, "3.2 GB"), (-5, "Zero bytes"),
])
def test_human_size(n, text):
    assert human_size(n) == text
