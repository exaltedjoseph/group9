"""Dependency-light text extraction for search and AI suggestions, plus small file helpers."""
# TODO(branch3): implement Git, text extraction, classwork and syllabus.
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
TEXT_EXTENSIONS = {'txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'xml', 'html', 'htm', 'css', 'js', 'ts', 'py', 'ipynb', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'sql', 'yaml', 'yml', 'toml', 'ini', 'rtf', 'log'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'svg', 'ico'}
_MIME_TYPES = {'pdf': 'application/pdf', 'txt': 'text/plain', 'log': 'text/plain', 'md': 'text/markdown', 'markdown': 'text/markdown', 'csv': 'text/csv', 'tsv': 'text/tab-separated-values', 'json': 'application/json', 'xml': 'application/xml', 'html': 'text/html', 'htm': 'text/html', 'css': 'text/css', 'js': 'text/javascript', 'ts': 'text/plain', 'py': 'text/x-python', 'ipynb': 'application/x-ipynb+json', 'java': 'text/x-java', 'c': 'text/x-c', 'cpp': 'text/x-c++', 'h': 'text/x-c', 'hpp': 'text/x-c++', 'cs': 'text/plain', 'sql': 'application/sql', 'yaml': 'application/yaml', 'yml': 'application/yaml', 'toml': 'application/toml', 'ini': 'text/plain', 'rtf': 'application/rtf', 'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp', 'tif': 'image/tiff', 'tiff': 'image/tiff', 'heic': 'image/heic', 'heif': 'image/heif', 'svg': 'image/svg+xml', 'ico': 'image/x-icon', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'doc': 'application/msword', 'ppt': 'application/vnd.ms-powerpoint', 'xls': 'application/vnd.ms-excel', 'odt': 'application/vnd.oasis.opendocument.text', 'odp': 'application/vnd.oasis.opendocument.presentation', 'ods': 'application/vnd.oasis.opendocument.spreadsheet', 'zip': 'application/zip', 'mp4': 'video/mp4', 'mov': 'video/quicktime', 'mp3': 'audio/mpeg', 'wav': 'audio/wav'}
_TAG = re.compile('<[^>]+>')
_BLOCK_END = re.compile('</(?:p|div|li|tr|h[1-6]|section|article|header|footer|pre|blockquote|table|ul|ol)\\s*>|<br\\s*/?>', re.IGNORECASE)
_SCRIPT = re.compile('<(script|style|noscript|template)\\b.*?</\\1\\s*>', re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile('<!--.*?-->', re.DOTALL)
_CONTROL = re.compile('[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]')

def _ext(path: Path) -> str:
    ...

def guess_mime(path: Path | str) -> str:
    """MIME type for a file name, `application/octet-stream` when unknown."""
    ...

def is_image(path: Path | str) -> bool:
    ...

def human_size(n: int) -> str:
    """Finder-style size with decimal units: "512 bytes", "12 KB", "1.2 MB"."""
    ...

def _clean(text: str) -> str:
    ...

def _strip_xml(xml: str) -> str:
    ...

def _strip_html(markup: str) -> str:
    ...

def _decode(data: bytes, truncated: bool) -> str:
    ...

def _read_text(path: Path, max_bytes: int) -> str:
    ...

def _notebook(raw: str) -> str:
    ...
_RTF_SKIP_GROUPS = ('fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'listtable', 'listoverridetable', 'rsidtbl', 'generator', 'themedata', 'colorschememapping', 'latentstyles', 'datastore')
_RTF_TOKEN = re.compile("\\\\([a-zA-Z]+)(-?\\d+)? ?|\\\\'([0-9a-fA-F]{2})|\\\\(.)|([{}])|([^\\\\{}]+)", re.DOTALL)

def _rtf(raw: str) -> str:
    ...

def _text_file(path: Path, ext: str, max_chars: int) -> str:
    ...

def _zip_read(zf: zipfile.ZipFile, name: str) -> str:
    ...

def _docx(path: Path) -> str:
    ...

def _numbered(names: list[str], pattern: str) -> list[str]:
    ...
_A_PARA = re.compile('<a:p[\\s>].*?</a:p>', re.DOTALL)
_A_TEXT = re.compile('<a:t(?:\\s[^>]*)?>(.*?)</a:t>', re.DOTALL)

def _pptx(path: Path, max_chars: int) -> str:
    ...
_X_TEXT = re.compile('<t(?:\\s[^>]*)?>(.*?)</t>', re.DOTALL)
_X_SI = re.compile('<si>(.*?)</si>', re.DOTALL)
_X_INLINE = re.compile('<is>(.*?)</is>', re.DOTALL)

def _xlsx(path: Path, max_chars: int) -> str:
    ...

def _opendocument(path: Path) -> str:
    ...

def _pdf(path: Path, max_chars: int) -> str:
    ...

def extract_text(path: Path, max_chars: int=200000) -> str:
    """Plain text from a document (txt, md, code, html, pdf, docx, pptx, xlsx, odt/odp). Never raises."""
    ...
