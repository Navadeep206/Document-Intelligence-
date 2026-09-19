import React, { useEffect, useState } from 'react';
import { useParams, NavLink } from 'react-router-dom';
import { ArrowLeft, HelpCircle, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';
import { Card, CardBody, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ConfidenceBadge } from '@/components/ui/ConfidenceBadge';
import { Spinner } from '@/components/ui/Spinner';
import { ErrorState } from '@/components/ui/ErrorState';
import { getQuestionApi, getQuestionReviewsApi } from '@/api/questions';
import { Question } from '@/types/question';
import { ReviewItem } from '@/types/review';
import { extractErrorMessage } from '@/api/axios';

export const QuestionDetails: React.FC = () => {
  const { questionId } = useParams<{ questionId: string }>();

  const [question, setQuestion] = useState<Question | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchQuestion = async () => {
    if (!questionId) return;

    try {
      const qRes = await getQuestionApi(questionId);
      setQuestion(qRes);

      try {
        const revRes = await getQuestionReviewsApi(questionId);
        const items = Array.isArray(revRes) ? revRes : (revRes?.items || []);
        setReviews(items);
      } catch (err) {
        console.error('Failed to load reviews for question', err);
      }
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestion();
  }, [questionId]);

  if (loading) {
    return (
      <div className="py-24 flex justify-center">
        <Spinner size="lg" label="Loading question..." />
      </div>
    );
  }

  if (error || !question) {
    return (
      <div className="py-12">
        <ErrorState
          title="Failed to load question"
          message={error || 'The requested question could not be found.'}
          onRetry={fetchQuestion}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <NavLink
          to={`/documents/${question.document_id}`}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Document
        </NavLink>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2.5">
              <span className="text-sm font-bold text-slate-900 bg-slate-100 px-2.5 py-1 rounded-md">
                Question {question.question_number || '—'}
              </span>
              <span className="text-xs font-mono text-slate-500 uppercase">{question.question_type}</span>
              <StatusBadge status={question.status} />
            </div>
            <ConfidenceBadge score={question.confidence_score} />
          </div>
        </CardHeader>

        <CardBody className="p-6 space-y-6">
          {/* Question Text */}
          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Question Body</h4>
            <p className="text-sm text-slate-900 font-medium leading-relaxed bg-slate-50/70 p-4 rounded-lg border border-slate-200/80">
              {question.question_text}
            </p>
          </div>

          {/* Options */}
          {question.options && question.options.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Multiple Choice Options ({question.options.length})
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {question.options.map((opt) => (
                  <div
                    key={opt.id}
                    className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 bg-white"
                  >
                    <span className="w-6 h-6 rounded-md bg-brand-50 text-brand-700 font-bold flex items-center justify-center text-xs shrink-0">
                      {opt.label}
                    </span>
                    <span className="text-xs text-slate-800">{opt.option_text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Review Warnings for Question */}
          {reviews.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-rose-500 uppercase tracking-wider mb-2">
                Flagged Issues for Review
              </h4>
              <div className="space-y-2">
                {reviews.map((rev) => (
                  <div
                    key={rev.id}
                    className="p-3.5 bg-rose-50/60 border border-rose-200 rounded-lg flex items-start gap-3"
                  >
                    <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-rose-900">{rev.reason}</span>
                        <StatusBadge status={rev.severity} />
                        <StatusBadge status={rev.status} />
                      </div>
                      <p className="text-xs text-rose-800 mt-1">{rev.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
};
