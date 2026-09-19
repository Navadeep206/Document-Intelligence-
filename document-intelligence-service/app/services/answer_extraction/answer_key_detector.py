"""Answer-key section, page range, and format detector."""

from dataclasses import dataclass
import re
from typing import Optional, Sequence

from app.db.models.enums import DocumentRole
from app.db.models.page import DocumentPage
from app.services.answer_extraction.answer_models import AnswerSection


class AnswerKeyDetector:
    """Detects answer-key sections, candidate pages, and format styles across document pages."""

    # Explicit answer-key heading indicators
    ANSWER_KEY_HEADERS = [
        re.compile(r"^(?:answer\s+keys?|answers?|correct\s+answers?|solutions?|key\s+answers?|scoring\s+key)(?:\s*[\:\-–—].*|\s*)$", re.IGNORECASE),
        re.compile(r"^(?:ans\.?\s*key|answer\s+sheet)(?:\s*[\:\-–—].*|\s*)$", re.IGNORECASE),
        re.compile(r"^(?:section\s+[a-z0-9]+\s*[\:\-]?\s*)?(?:answers?|answer\s+key)(?:\s*[\:\-–—].*|\s*)$", re.IGNORECASE),
    ]

    # Negative context patterns (phrases containing 'answer' that are exam instructions, NOT answer keys)
    INSTRUCTION_NEGATIVES = [
        re.compile(r"^(?:answer\s+(?:all|any|the\s+following|either|both))\b", re.IGNORECASE),
        re.compile(r"^(?:write\s+your\s+answers?|each\s+question\s+carries|marks?\s+for\s+correct\s+answer)\b", re.IGNORECASE),
        re.compile(r"^(?:answers?\s+must\s+be\s+written|candidate\s+must\s+answer)\b", re.IGNORECASE),
    ]

    # Question section indicators that would end a beginning answer key
    QUESTION_SECTION_HEADERS = [
        re.compile(r"^(?:questions?|part\s+[a-z0-9]+|section\s+[a-z0-9]+)\b", re.IGNORECASE),
    ]

    def is_answer_key_header(self, text: str) -> bool:
        """Check if a single line represents an answer-key section heading."""
        cleaned = text.strip()
        if not cleaned or len(cleaned) > 60:
            return False

        # First verify it is not an exam instruction
        for neg in self.INSTRUCTION_NEGATIVES:
            if neg.search(cleaned):
                return False

        # Check for explicit header match
        for pattern in self.ANSWER_KEY_HEADERS:
            if pattern.search(cleaned):
                return True

        return False

    def detect_sections(
        self,
        pages: Sequence[DocumentPage],
        document_role: DocumentRole = DocumentRole.UNKNOWN,
    ) -> list[AnswerSection]:
        """Identify answer-key sections and their corresponding page lines."""
        # 1. If explicitly designated as an ANSWER_KEY document role, treat all pages as answer-key content
        if document_role == DocumentRole.ANSWER_KEY:
            all_lines: list[tuple[int, str]] = []
            min_page = 1
            max_page = 1
            for page in sorted(pages, key=lambda p: p.page_number):
                if not page.text_content:
                    continue
                min_page = min(min_page, page.page_number)
                max_page = max(max_page, page.page_number)
                for raw_line in page.text_content.splitlines():
                    line = raw_line.strip()
                    if line:
                        all_lines.append((page.page_number, line))

            if all_lines:
                return [
                    AnswerSection(
                        source_page_start=min_page,
                        source_page_end=max_page,
                        header_text="ROLE_ANSWER_KEY",
                        format_description=self.detect_format_description(all_lines),
                        lines=all_lines,
                    )
                ]
            return []

        # 2. For QUESTION_PAPER or UNKNOWN roles: scan page text for answer-key sections
        sections: list[AnswerSection] = []
        in_answer_key = False
        current_header = ""
        current_lines: list[tuple[int, str]] = []
        start_page = 1
        end_page = 1

        for page in sorted(pages, key=lambda p: p.page_number):
            if not page.text_content:
                continue

            for raw_line in page.text_content.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                # Check if this line starts an answer-key section
                if self.is_answer_key_header(line):
                    if in_answer_key and current_lines:
                        sections.append(
                            AnswerSection(
                                source_page_start=start_page,
                                source_page_end=end_page,
                                header_text=current_header,
                                format_description=self.detect_format_description(current_lines),
                                lines=current_lines,
                            )
                        )
                    in_answer_key = True
                    current_header = line
                    current_lines = []
                    start_page = page.page_number
                    end_page = page.page_number
                    continue

                if in_answer_key:
                    # Check if a question section begins (ending an initial answer key)
                    if self._is_question_section_start(line, current_lines):
                        sections.append(
                            AnswerSection(
                                source_page_start=start_page,
                                source_page_end=end_page,
                                header_text=current_header,
                                format_description=self.detect_format_description(current_lines),
                                lines=current_lines,
                            )
                        )
                        in_answer_key = False
                        current_lines = []
                        continue

                    current_lines.append((page.page_number, line))
                    end_page = page.page_number

        if in_answer_key and current_lines:
            sections.append(
                AnswerSection(
                    source_page_start=start_page,
                    source_page_end=end_page,
                    header_text=current_header,
                    format_description=self.detect_format_description(current_lines),
                    lines=current_lines,
                )
            )

        return sections

    def _is_question_section_start(self, line: str, accumulated_lines: list[tuple[int, str]]) -> bool:
        """Check if an answer-key section at the beginning transitions into questions."""
        # Only consider ending answer-key if we have already accumulated at least 2 answer entries
        if len(accumulated_lines) < 2:
            return False
        for pattern in self.QUESTION_SECTION_HEADERS:
            if pattern.match(line):
                return True
        return False

    def detect_format_description(self, lines: list[tuple[int, str]]) -> str:
        """Infer high-level answer format description from sample lines."""
        text_samples = " ".join(l for _, l in lines[:15])
        if re.search(r"\b(?:true|false)\b", text_samples, re.IGNORECASE):
            return "True/False"
        if re.search(r"\b[A-D]\s*,\s*[A-D]\b", text_samples):
            return "Multiple Choice (Multi-select)"
        if re.search(r"\b[A-Da-d]\b", text_samples):
            return "Standard Multiple Choice"
        if re.search(r"\b[0-9]+\.[0-9]+\b", text_samples):
            return "Numerical"
        return "Standard"


answer_key_detector = AnswerKeyDetector()
