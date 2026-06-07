"""
Convert Markdown report text into Notion API blocks and Google Docs API requests.
"""
from __future__ import annotations
import re
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
# NOTION BLOCKS
# ══════════════════════════════════════════════════════════════════════════════

def _notion_rich_text(text: str) -> list[dict]:
    """Convert inline markdown (bold, italic, code, links) to Notion rich_text objects."""
    segments: list[dict] = []
    # Pattern: **bold**, *italic*, `code`, [text](url)
    pattern = r'(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\))'
    last_end = 0

    for match in re.finditer(pattern, text):
        # Add plain text before this match
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                segments.append({"type": "text", "text": {"content": plain}})

        if match.group(2):  # **bold**
            segments.append({
                "type": "text",
                "text": {"content": match.group(2)},
                "annotations": {"bold": True},
            })
        elif match.group(3):  # *italic*
            segments.append({
                "type": "text",
                "text": {"content": match.group(3)},
                "annotations": {"italic": True},
            })
        elif match.group(4):  # `code`
            segments.append({
                "type": "text",
                "text": {"content": match.group(4)},
                "annotations": {"code": True},
            })
        elif match.group(5) and match.group(6):  # [text](url)
            segments.append({
                "type": "text",
                "text": {"content": match.group(5), "link": {"url": match.group(6)}},
            })

        last_end = match.end()

    # Remaining text
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            segments.append({"type": "text", "text": {"content": remaining}})

    if not segments:
        segments.append({"type": "text", "text": {"content": text}})

    return segments


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    """Convert a markdown string to a list of Notion block objects."""
    blocks: list[dict] = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Headings
        if line.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": _notion_rich_text(line[4:].strip())},
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": _notion_rich_text(line[3:].strip())},
            })
        elif line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": _notion_rich_text(line[2:].strip())},
            })
        # Bullet list
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _notion_rich_text(line[2:].strip())},
            })
        # Numbered list
        elif re.match(r"^\d+\.\s", line):
            content = re.sub(r"^\d+\.\s", "", line).strip()
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _notion_rich_text(content)},
            })
        # Blockquote
        elif line.startswith("> "):
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": _notion_rich_text(line[2:].strip())},
            })
        # Horizontal rule
        elif line.strip() in ("---", "***", "___"):
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {},
            })
        # Empty line — skip
        elif not line.strip():
            pass
        # Regular paragraph
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _notion_rich_text(line.strip())},
            })

        i += 1

    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE DOCS REQUESTS
# ══════════════════════════════════════════════════════════════════════════════

def markdown_to_google_docs_requests(markdown: str) -> list[dict]:
    """
    Convert markdown to a list of Google Docs API batchUpdate requests.
    Inserts content at index 1 (start of document body).
    Returns requests in REVERSE order (Google Docs inserts shift indices).
    """
    lines = markdown.split("\n")
    requests: list[dict] = []
    # We'll build content sequentially, tracking the insert index
    index = 1  # Google Docs body starts at index 1

    for line in lines:
        if not line.strip():
            # Empty line → newline
            requests.append({
                "insertText": {"location": {"index": index}, "text": "\n"}
            })
            index += 1
            continue

        # Determine heading level and style
        heading_style = None
        text = line
        if line.startswith("### "):
            heading_style = "HEADING_3"
            text = line[4:].strip()
        elif line.startswith("## "):
            heading_style = "HEADING_2"
            text = line[3:].strip()
        elif line.startswith("# "):
            heading_style = "HEADING_1"
            text = line[2:].strip()
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            # Insert as bullet
            plain_text = _strip_markdown_inline(text)
            requests.append({
                "insertText": {"location": {"index": index}, "text": plain_text + "\n"}
            })
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": index, "endIndex": index + len(plain_text) + 1},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            })
            # Add bold/italic formatting
            requests.extend(_inline_format_requests(text, index))
            index += len(plain_text) + 1
            continue
        elif re.match(r"^\d+\.\s", line):
            text = re.sub(r"^\d+\.\s", "", line).strip()
            plain_text = _strip_markdown_inline(text)
            requests.append({
                "insertText": {"location": {"index": index}, "text": plain_text + "\n"}
            })
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": index, "endIndex": index + len(plain_text) + 1},
                    "bulletPreset": "NUMBERED_DECIMAL_NESTED",
                }
            })
            requests.extend(_inline_format_requests(text, index))
            index += len(plain_text) + 1
            continue

        # Regular text or heading
        plain_text = _strip_markdown_inline(text)
        requests.append({
            "insertText": {"location": {"index": index}, "text": plain_text + "\n"}
        })

        if heading_style:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + len(plain_text) + 1},
                    "paragraphStyle": {"namedStyleType": heading_style},
                    "fields": "namedStyleType",
                }
            })

        # Inline formatting (bold, italic)
        requests.extend(_inline_format_requests(text, index))
        index += len(plain_text) + 1

    return requests


def _strip_markdown_inline(text: str) -> str:
    """Remove markdown inline syntax, keeping just the text content."""
    # Links: [text](url) → text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # Bold: **text** → text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Italic: *text* → text
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # Code: `text` → text
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text


def _inline_format_requests(markdown_text: str, base_index: int) -> list[dict]:
    """Generate updateTextStyle requests for bold/italic in a line."""
    requests = []
    plain_so_far = ""
    # Track positions in the plain text
    plain_text = _strip_markdown_inline(markdown_text)

    # Find bold segments
    for match in re.finditer(r'\*\*(.+?)\*\*', markdown_text):
        # Find where this text appears in the plain version
        bold_text = match.group(1)
        pos = plain_text.find(bold_text, len(plain_so_far))
        if pos >= 0:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": base_index + pos, "endIndex": base_index + pos + len(bold_text)},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })

    # Find italic segments (not bold)
    for match in re.finditer(r'(?<!\*)\*([^*]+?)\*(?!\*)', markdown_text):
        italic_text = match.group(1)
        pos = plain_text.find(italic_text)
        if pos >= 0:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": base_index + pos, "endIndex": base_index + pos + len(italic_text)},
                    "textStyle": {"italic": True},
                    "fields": "italic",
                }
            })

    return requests
