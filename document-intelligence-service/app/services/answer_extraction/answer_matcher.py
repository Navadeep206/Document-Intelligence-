"""Deterministic question-number matching and uncertainty preservation engine."""

import logging
from typing import Optional, Sequence
import uuid

from app.db.models.question import Question
from app.services.answer_extraction.answer_models import MatchResult, ParsedAnswerEntry
from app.services.answer_extraction.answer_parser import answer_parser

logger = logging.getLogger("document-intelligence-service")


class AnswerMatcher:
    """Matches parsed answer entries to Question records deterministically without silent guessing."""

    def match_answers(
        self,
        entries: list[ParsedAnswerEntry],
        questions: Sequence[Question],
    ) -> list[MatchResult]:
        """Associate each parsed answer entry with a Question or record as unmatched/uncertain."""
        # 1. Build index of questions by raw and normalized question numbers
        # questions_by_norm: normalized_number -> list of Question objects
        questions_by_norm: dict[str, list[Question]] = {}
        for q in questions:
            if not q.question_number:
                continue
            norm_qnum = answer_parser.normalize_reference(q.question_number)
            questions_by_norm.setdefault(norm_qnum, []).append(q)

        results: list[MatchResult] = []

        for entry in entries:
            # 2. Uncertainty check: if answer indicates '?' or 'unclear', DO NOT assign answer
            if entry.is_uncertain:
                results.append(
                    MatchResult(
                        entry=entry,
                        matched_question_id=None,
                        confidence=0.0,
                        match_strategy="UNCERTAIN",
                        notes=["Answer value indicates uncertainty or placeholder."],
                    )
                )
                continue

            norm_ref = entry.normalized_reference
            candidate_questions = questions_by_norm.get(norm_ref, [])

            # 3. Exact unique match
            if len(candidate_questions) == 1:
                matched_q = candidate_questions[0]
                is_exact_raw = (entry.question_reference == matched_q.question_number)
                conf = 0.98 if is_exact_raw else 0.92
                strategy = "EXACT" if is_exact_raw else "NORMALIZED"

                results.append(
                    MatchResult(
                        entry=entry,
                        matched_question_id=matched_q.id,
                        confidence=conf,
                        match_strategy=strategy,
                        notes=[f"Matched to question {matched_q.question_number} ({strategy})."],
                    )
                )
                logger.info(
                    "answer_mapping reference=%s match=%s question_id=%s source_page=%s",
                    entry.question_reference,
                    strategy,
                    matched_q.id,
                    entry.source_page,
                )

            # 4. Ambiguous reference: multiple questions share the same number
            elif len(candidate_questions) > 1:
                results.append(
                    MatchResult(
                        entry=entry,
                        matched_question_id=None,
                        confidence=0.30,
                        match_strategy="AMBIGUOUS",
                        notes=[
                            f"Ambiguous match: {len(candidate_questions)} questions match reference '{norm_ref}'."
                        ],
                    )
                )
                logger.warning(
                    "answer_mapping reference=%s match=AMBIGUOUS candidate_count=%d source_page=%s",
                    entry.question_reference,
                    len(candidate_questions),
                    entry.source_page,
                )

            # 5. No question found matching this reference
            else:
                results.append(
                    MatchResult(
                        entry=entry,
                        matched_question_id=None,
                        confidence=0.0,
                        match_strategy="UNMATCHED",
                        notes=[f"No question found matching reference '{norm_ref}'."],
                    )
                )
                logger.info(
                    "answer_mapping reference=%s match=UNMATCHED question_id=None source_page=%s",
                    entry.question_reference,
                    entry.source_page,
                )

        return results


answer_matcher = AnswerMatcher()
