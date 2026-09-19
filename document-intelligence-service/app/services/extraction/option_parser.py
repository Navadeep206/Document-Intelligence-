"""Contextual option parser supporting multi-format and inline multiple-choice options."""

import re
from typing import Optional

from app.services.extraction.models import ExtractedOption


class OptionParser:
    """Parses multiple choice options from question block text and strips them from the question stem."""

    # Line-starting option patterns
    # Format examples: A., A), (A), [A], a., a), (a), Option A:, Option 1:
    OPTION_LINE_PATTERNS = [
        # (A) or (a) or [A] or [1]
        re.compile(r"^(?:[\(\[]([A-Da-d0-9])[\)\]])\s*(.*)$"),
        # Option A: or Option 1:
        re.compile(r"^(?:Option\s+([A-Da-d0-9])[\:\.\-\)]?)\s*(.*)$", re.IGNORECASE),
        # A. or A) or A: or A - or a. or a)
        re.compile(r"^([A-Da-d])(?:[\.\)\:\-\–\—]|\s*[\)\/])\s*(.*)$"),
    ]

    # Pattern to detect multiple options embedded horizontally on a single line
    # e.g., (A) Apple  (B) Banana  (C) Cherry  (D) Date
    # e.g., A) 10   B) 20   C) 30   D) 40
    INLINE_OPTION_SPLITTER = re.compile(
        r"(?:(?<=\s)|(?<=^))(?:(?:\(([A-Da-d0-9])\)|Option\s+([A-Da-d0-9])[\:\.]?|([A-Da-d])[\.\)\:\-]))\s+",
    )

    def parse_options(self, lines: list[str]) -> tuple[str, list[ExtractedOption]]:
        """Parse options from a block of text lines, returning (cleaned_question_stem, options)."""
        stem_lines: list[str] = []
        options: list[ExtractedOption] = []
        position = 1

        in_options_section = False
        current_option_label: Optional[str] = None
        current_option_text: list[str] = []

        def flush_current_option():
            nonlocal position, current_option_label, current_option_text
            if current_option_label and current_option_text:
                full_text = " ".join(current_option_text).strip()
                options.append(
                    ExtractedOption(
                        label=current_option_label,
                        text=full_text,
                        position=position,
                    )
                )
                position += 1
            current_option_label = None
            current_option_text = []

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # First, check if the line contains horizontal / inline multiple options
            inline_options = self._parse_inline_options(trimmed)
            if inline_options and len(inline_options) >= 2:
                in_options_section = True
                flush_current_option()
                for opt in inline_options:
                    opt.position = position
                    options.append(opt)
                    position += 1
                continue

            # Check if line starts an individual option
            opt_match = self._match_option_start(trimmed)
            if opt_match:
                in_options_section = True
                flush_current_option()
                label, text_part = opt_match
                current_option_label = label
                current_option_text.append(text_part)
            elif in_options_section:
                # Continuation of current option text
                current_option_text.append(trimmed)
            else:
                # Still part of the question stem
                stem_lines.append(line)

        flush_current_option()

        # If options were found, ensure positions are sequential
        cleaned_stem = "\n".join(stem_lines).strip()
        return cleaned_stem, options

    def _match_option_start(self, line: str) -> Optional[tuple[str, str]]:
        """Check if line starts with an option identifier and return (label, remaining_text)."""
        for pattern in self.OPTION_LINE_PATTERNS:
            match = pattern.match(line)
            if match:
                label = match.group(1).upper()
                text_part = match.group(2).strip()
                return label, text_part
        return None

    def _parse_inline_options(self, line: str) -> list[ExtractedOption]:
        """Detect and split inline horizontal options like '(A) Alpha (B) Beta (C) Gamma'."""
        matches = list(self.INLINE_OPTION_SPLITTER.finditer(line))
        if len(matches) < 2:
            return []

        parsed: list[ExtractedOption] = []
        for i, match in enumerate(matches):
            label = match.group(1) or match.group(2) or match.group(3)
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            text_part = line[start_pos:end_pos].strip()

            parsed.append(
                ExtractedOption(
                    label=label.upper(),
                    text=text_part,
                    position=i + 1,
                )
            )

        return parsed


option_parser = OptionParser()
