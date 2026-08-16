from __future__ import annotations

import io
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

# Formats handled by firecrawl-anydoc (anydoc.to_markdown).
_ANYDOC_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/epub+zip",
    "application/vnd.oasis.opendocument.text",
    "text/csv",
}

_ANYDOC_EXTS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".epub",
    ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
}

_TEXT_EXTS = {".txt", ".log", ".md", ".text"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_via_anydoc(path: Path) -> str:
    """Parse a document with firecrawl-anydoc (returns GitHub-Flavored Markdown)."""
    import anydoc
    return anydoc.to_markdown(str(path))


def _read_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(str(path))
        return pytesseract.image_to_string(img)
    except ImportError:
        logger.warning("pytesseract not available; returning empty text")
        return ""


def detect_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def parse_file(path: str | Path) -> tuple[str, str, bool]:
    p = Path(path)
    mime = detect_mime(p)
    ext = p.suffix.lower()

    try:
        if ext in _IMAGE_EXTS or mime.startswith("image/"):
            return (_read_image(p), mime, True)
        if ext in _TEXT_EXTS:
            return (_read_text_file(p), mime, False)
        if ext in _ANYDOC_EXTS or mime in _ANYDOC_MIMES:
            return (_read_via_anydoc(p), mime, False)
        # Fallback: try text, then anydoc.
        try:
            return (_read_text_file(p), mime, False)
        except Exception:
            try:
                return (_read_via_anydoc(p), mime, False)
            except Exception:
                return ("", mime, False)
    except Exception as exc:
        logger.exception("Failed to parse %s", p)
        return ("", mime, False)


def parse_bytes(data: bytes, mime: str) -> tuple[str, bool]:
    try:
        if mime.startswith("image/"):
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(io.BytesIO(data))
                return (pytesseract.image_to_string(img), True)
            except ImportError:
                return ("", True)
        if mime in _ANYDOC_MIMES:
            import anydoc
            fmt = None
            try:
                fmt = anydoc.format_from_bytes(data)
            except Exception:
                fmt = None
            return (anydoc.to_markdown_bytes(data, format=fmt), False)
        # Plain text fallback.
        try:
            return (data.decode("utf-8", errors="replace"), False)
        except Exception:
            return ("", False)
    except Exception as exc:
        logger.exception("Failed to parse bytes (mime=%s)", mime)
        return ("", False)
