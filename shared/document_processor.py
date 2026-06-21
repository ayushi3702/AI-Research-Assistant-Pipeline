"""
Document processing utilities for file uploads.
Extracts text from PDF, DOCX, TXT, and Markdown files, then chunks for RAG.
"""
from __future__ import annotations
import io
import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}
MAX_CHUNK_CHARS = 1200
OVERLAP_WORDS = 50


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from a file based on its extension."""
    ext = Path(filename).suffix.lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(content)
        elif ext in (".txt", ".md"):
            return content.decode("utf-8", errors="ignore")
        elif ext == ".docx":
            return _extract_docx(content)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    except ValueError:
        raise
    except Exception as e:
        logger.error("Failed to extract text from %s: %s", filename, e, exc_info=True)
        raise ValueError(f"Could not extract text from {filename}: {e}") from e


def _extract_pdf(content: bytes) -> str:
    doc = fitz.open(stream=io.BytesIO(content), filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _extract_docx(content: bytes) -> str:
    """Extract text from DOCX using zipfile (no python-docx dependency)."""
    import zipfile
    from xml.etree import ElementTree

    text_parts = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        if "word/document.xml" in zf.namelist():
            xml_content = zf.read("word/document.xml")
            tree = ElementTree.fromstring(xml_content)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for para in tree.iter(f"{{{ns['w']}}}t"):
                if para.text:
                    text_parts.append(para.text)
    return " ".join(text_parts)


def chunk_text(text: str, chunk_size: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    if not words:
        return []

    chunks = []
    current = []
    length = 0

    for word in words:
        current.append(word)
        length += len(word) + 1
        if length >= chunk_size:
            chunks.append(" ".join(current))
            current = current[-OVERLAP_WORDS:]
            length = sum(len(w) + 1 for w in current)

    if current:
        chunks.append(" ".join(current))

    return chunks
