"""Text normalization utilities for document intelligence extraction."""

import re


def normalize_extracted_text(raw_text: str | None) -> str:
    """Normalize extracted document text while strictly preserving structure and markers.

    Applies non-destructive cleanup:
    - Standardizes newline characters (\r\n and \r -> \n).
    - Removes form-feed page delimiters (\x0c).
    - Trims trailing whitespace from each line.
    - Collapses 3 or more consecutive newlines into 2 (preserving paragraph spacing).
    - Strips overall leading/trailing whitespace.

    Strict Constraints:
    - Does NOT paraphrase, summarize, or alter character content.
    - Does NOT remove punctuation or symbols.
    - Does NOT modify casing or question markers (e.g. Q1., 1., (A), Option B).
    """
    if not raw_text:
        return ""

    # 1. Standardize newlines and remove form-feed characters
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "")

    # 2. Trim trailing spaces from each individual line while preserving leading indentation
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # 3. Collapse 3 or more consecutive newlines into 2 (preserves intentional paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
