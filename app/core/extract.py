"""Dependency-light text extraction for search and AI suggestions, plus small file helpers."""
from __future__ import annotations

import codecs
import html
import json
import logging
import mimetypes
import re
import zipfile
from pathlib import Path

MAX_PDF_PAGES = 60
_MAX_TEXT_BYTES = 8 * 1024 * 1024
_MAX_XML_BYTES = 64 * 1024 * 1024

TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "xml", "html", "htm", "css", "js", "ts", "py", "ipynb",
    "java", "c", "cpp", "h", "hpp", "cs", "sql", "yaml", "yml", "toml", "ini", "rtf", "log",
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "heic", "heif", "svg", "ico"}

_MIME_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain", "log": "text/plain", "md": "text/markdown", "markdown": "text/markdown",
    "csv": "text/csv", "tsv": "text/tab-separated-values", "json": "application/json", "xml": "application/xml",
    "html": "text/html", "htm": "text/html", "css": "text/css", "js": "text/javascript", "ts": "text/plain",
    "py": "text/x-python", "ipynb": "application/x-ipynb+json", "java": "text/x-java", "c": "text/x-c",
    "cpp": "text/x-c++", "h": "text/x-c", "hpp": "text/x-c++", "cs": "text/plain", "sql": "application/sql",
    "yaml": "application/yaml", "yml": "application/yaml", "toml": "application/toml", "ini": "text/plain",
    "rtf": "application/rtf",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "heic": "image/heic", "heif": "image/heif",
    "svg": "image/svg+xml", "ico": "image/x-icon",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "doc": "application/msword", "ppt": "application/vnd.ms-powerpoint", "xls": "application/vnd.ms-excel",
    "odt": "application/vnd.oasis.opendocument.text",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "zip": "application/zip", "mp4": "video/mp4", "mov": "video/quicktime", "mp3": "audio/mpeg",
    "wav": "audio/wav",
}

_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</(?:p|div|li|tr|h[1-6]|section|article|header|footer|pre|blockquote|table|ul|ol)\s*>"
                        r"|<br\s*/?>", re.IGNORECASE)
_SCRIPT = re.compile(r"<(script|style|noscript|template)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def guess_mime(path: Path | str) -> str:
    """MIME type for a file name, `application/octet-stream` when unknown."""
    p = Path(path)
    known = _MIME_TYPES.get(_ext(p))
    if known:
        return known
    guessed, _ = mimetypes.guess_type(p.name, strict=False)
    return guessed or "application/octet-stream"


def is_image(path: Path | str) -> bool:
    return _ext(Path(path)) in IMAGE_EXTENSIONS


def human_size(n: int) -> str:
    """Finder-style size with decimal units: "512 bytes", "12 KB", "1.2 MB"."""
    try:
        n = max(0, int(n or 0))
    except (TypeError, ValueError):
        n = 0
    if n == 0:
        return "Zero bytes"
    if n < 1000:
        return f"{n} byte" if n == 1 else f"{n} bytes"
    units = (("KB", 0), ("MB", 1), ("GB", 1), ("TB", 1))
    value = n / 1000
    for i, (unit, decimals) in enumerate(units):
        rounded = round(value, decimals)
        if rounded < 1000 or i == len(units) - 1:
            text = f"{rounded:,.{decimals}f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{text} {unit}"
        value /= 1000
    return f"{n} bytes"


# ---------------------------------------------------------------------- cleanup
def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = _CONTROL.sub("", text)
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_xml(xml: str) -> str:
    return html.unescape(_TAG.sub("", xml))


def _strip_html(markup: str) -> str:
    markup = _COMMENT.sub(" ", markup)
    markup = _SCRIPT.sub(" ", markup)
    markup = _BLOCK_END.sub("\n", markup)
    return html.unescape(_TAG.sub(" ", markup))


# ---------------------------------------------------------------------- plain text
def _decode(data: bytes, truncated: bool) -> str:
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8):]
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return codecs.getincrementaldecoder("utf-8")().decode(data, final=not truncated)
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _read_text(path: Path, max_bytes: int) -> str:
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    return _decode(data[:max_bytes], truncated)


def _notebook(raw: str) -> str:
    try:
        nb = json.loads(raw)
    except ValueError:
        return raw
    cells = nb.get("cells", []) if isinstance(nb, dict) else []
    parts = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        src = cell.get("source", "")
        parts.append("".join(src) if isinstance(src, list) else str(src))
    return "\n\n".join(p for p in parts if p.strip())


_RTF_SKIP_GROUPS = ("fonttbl", "colortbl", "stylesheet", "info", "pict", "listtable", "listoverridetable",
                    "rsidtbl", "generator", "themedata", "colorschememapping", "latentstyles", "datastore")
_RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}]+)", re.DOTALL)


def _rtf(raw: str) -> str:
    out: list[str] = []
    stack: list[bool] = []
    skipping = False
    pending_group = False
    uc_skip = 0
    for word, arg, hexcode, sym, brace, text in _RTF_TOKEN.findall(raw):
        if brace == "{":
            stack.append(skipping)
            pending_group = True
            continue
        if brace == "}":
            skipping = stack.pop() if stack else False
            pending_group = False
            continue
        first = pending_group
        pending_group = False
        if skipping:
            continue
        if word:
            if first and word in _RTF_SKIP_GROUPS:
                skipping = True
            elif word in ("par", "line", "sect", "page", "row"):
                out.append("\n")
            elif word in ("tab", "cell"):
                out.append("\t")
            elif word == "u" and arg:
                code = int(arg)
                out.append(chr(code + 65536 if code < 0 else code))
                uc_skip = 1
        elif hexcode:
            if uc_skip:
                uc_skip = 0
                continue
            out.append(bytes([int(hexcode, 16)]).decode("cp1252", errors="replace"))
        elif sym:
            if sym == "*" and first:
                skipping = True
            elif sym in "\\{}":
                out.append(sym)
            elif sym == "~":
                out.append(" ")
            elif sym in "\n\r":
                out.append("\n")
        elif text:
            if uc_skip:
                text = text[1:]
                uc_skip = 0
            out.append(text.replace("\r", "").replace("\n", ""))
    return "".join(out)


def _text_file(path: Path, ext: str, max_chars: int) -> str:
    if ext in ("ipynb", "rtf"):
        raw = _read_text(path, _MAX_TEXT_BYTES)
        return _notebook(raw) if ext == "ipynb" else _rtf(raw)
    raw = _read_text(path, min(_MAX_TEXT_BYTES, max_chars * 4 + 1024))
    if ext in ("html", "htm"):
        return _strip_html(raw)
    return raw


# ---------------------------------------------------------------------- office / zip based
def _zip_read(zf: zipfile.ZipFile, name: str) -> str:
    info = zf.getinfo(name)
    if info.file_size > _MAX_XML_BYTES:
        return ""
    return zf.read(info).decode("utf-8", errors="replace")


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = _zip_read(zf, "word/document.xml")
    xml = re.sub(r"<w:tab\s*/>", "\t", xml)
    xml = re.sub(r"<w:(?:br|cr)\b[^>]*/>", "\n", xml)
    xml = xml.replace("</w:p>", "\n")
    return _strip_xml(xml)


def _numbered(names: list[str], pattern: str) -> list[str]:
    rx = re.compile(pattern)
    found = [(int(m.group(1)), n) for n in names if (m := rx.fullmatch(n))]
    return [n for _, n in sorted(found)]


_A_PARA = re.compile(r"<a:p[\s>].*?</a:p>", re.DOTALL)
_A_TEXT = re.compile(r"<a:t(?:\s[^>]*)?>(.*?)</a:t>", re.DOTALL)


def _pptx(path: Path, max_chars: int) -> str:
    slides: list[str] = []
    total = 0
    with zipfile.ZipFile(path) as zf:
        for name in _numbered(zf.namelist(), r"ppt/slides/slide(\d+)\.xml"):
            xml = _zip_read(zf, name)
            lines = ["".join(_A_TEXT.findall(p)) for p in _A_PARA.findall(xml)] or _A_TEXT.findall(xml)
            text = html.unescape("\n".join(line for line in lines if line.strip()))
            if text.strip():
                slides.append(text)
                total += len(text)
            if total >= max_chars:
                break
    return "\n\n".join(slides)


_X_TEXT = re.compile(r"<t(?:\s[^>]*)?>(.*?)</t>", re.DOTALL)
_X_SI = re.compile(r"<si>(.*?)</si>", re.DOTALL)
_X_INLINE = re.compile(r"<is>(.*?)</is>", re.DOTALL)


def _xlsx(path: Path, max_chars: int) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "xl/sharedStrings.xml" in names:
            xml = _zip_read(zf, "xl/sharedStrings.xml")
            parts += ["".join(_X_TEXT.findall(si)) for si in _X_SI.findall(xml)]
        for name in _numbered(names, r"xl/worksheets/sheet(\d+)\.xml"):
            if sum(len(p) for p in parts) >= max_chars:
                break
            xml = _zip_read(zf, name)
            parts += ["".join(_X_TEXT.findall(s)) for s in _X_INLINE.findall(xml)]
    return html.unescape("\n".join(p for p in parts if p.strip()))


def _opendocument(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = _zip_read(zf, "content.xml")
    xml = re.sub(r"<text:tab\s*/>", "\t", xml)
    xml = re.sub(r"<text:line-break\s*/>", "\n", xml)
    xml = re.sub(r"<text:s(?:\s[^>]*)?/>", " ", xml)
    xml = re.sub(r"</text:(?:p|h)>", "\n", xml)
    xml = re.sub(r"</draw:page>", "\n\n", xml)
    return _strip_xml(xml)


def _pdf(path: Path, max_chars: int) -> str:
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return ""
    pages: list[str] = []
    total = 0
    for i, page in enumerate(reader.pages):
        if i >= MAX_PDF_PAGES or total >= max_chars:
            break
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        pages.append(text)
        total += len(text)
    return "\n\n".join(pages)


def extract_text(path: Path, max_chars: int = 200_000) -> str:
    """Plain text from a document (txt, md, code, html, pdf, docx, pptx, xlsx, odt/odp). Never raises."""
    try:
        path = Path(path)
        if not path.is_file():
            return ""
        ext = _ext(path)
        if ext in TEXT_EXTENSIONS:
            text = _text_file(path, ext, max_chars)
        elif ext == "pdf":
            text = _pdf(path, max_chars)
        elif ext in ("docx", "docm", "dotx"):
            text = _docx(path)
        elif ext in ("pptx", "pptm", "ppsx"):
            text = _pptx(path, max_chars)
        elif ext in ("xlsx", "xlsm"):
            text = _xlsx(path, max_chars)
        elif ext in ("odt", "odp", "ods"):
            text = _opendocument(path)
        else:
            return ""
        return _clean(text)[:max_chars]
    except Exception:
        return ""
