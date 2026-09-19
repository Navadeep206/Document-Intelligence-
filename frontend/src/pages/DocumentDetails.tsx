import React, { useEffect, useState } from 'react';
import { useParams, NavLink } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  HelpCircle,
  ExternalLink,
} from 'lucide-react';
import { Card, CardBody, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ConfidenceBadge } from '@/components/ui/ConfidenceBadge';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import {
  getDocumentApi,
  getDocumentStatusApi,
  getDocumentQuestionsApi,
  getDocumentReviewsApi,
} from '@/api/documents';
import { Document, DocumentProcessingStatus } from '@/types/document';
import { Question } from '@/types/question';
import { ReviewItem } from '@/types/review';
import { extractErrorMessage } from '@/api/axios';

export const DocumentDetails: React.FC = () => {
  const { documentId } = useParams<{ documentId: string }>();

  const [document, setDocument] = useState<Document | null>(null);
  const [status, setStatus] = useState<DocumentProcessingStatus | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [justRefreshed, setJustRefreshed] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'questions' | 'reviews'>('questions');

  const fetchDetails = async (isManual = false) => {
    if (!documentId) return;
    if (isManual) setRefreshing(true);

    try {
      const [docRes, statusRes] = await Promise.all([
        getDocumentApi(documentId),
        getDocumentStatusApi(documentId),
      ]);
      setDocument(docRes);
      setStatus(statusRes);

      // Fetch questions and reviews (up to 100 for comprehensive review)
      try {
        const qRes = await getDocumentQuestionsApi(documentId, { page_size: 100 });
        setQuestions(qRes.items || []);
      } catch (err) {
        console.error('Failed to fetch questions', err);
      }

      try {
        const revRes = await getDocumentReviewsApi(documentId, { page_size: 100 });
        const items = Array.isArray(revRes) ? revRes : (revRes?.items || []);
        setReviews(items);
      } catch (err) {
        console.error('Failed to fetch reviews', err);
      }

      if (isManual) {
        setJustRefreshed(true);
        setTimeout(() => setJustRefreshed(false), 2500);
      }
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDetails();

    // Auto-poll status if processing
    const interval = setInterval(() => {
      if (document && (document.status === 'PROCESSING' || document.status === 'QUEUED')) {
        fetchDetails();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documentId, document?.status]);

  if (loading) {
    return (
      <div className="py-24 flex justify-center">
        <Spinner size="lg" label="Loading document details..." />
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="py-12">
        <ErrorState
          title="Failed to load document"
          message={error || 'The requested document could not be found.'}
          onRetry={() => fetchDetails(true)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb & Navigation */}
      <div className="flex items-center justify-between">
        <NavLink
          to="/documents"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Documents
        </NavLink>

        <div className="flex items-center gap-2">
          {justRefreshed && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 transition-opacity">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Refreshed
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchDetails(true)}
            isLoading={refreshing}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />}
          >
            {refreshing ? 'Refreshing...' : 'Refresh Status'}
          </Button>
        </div>
      </div>

      {/* Overview Card */}
      <Card>
        <CardBody className="p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-5">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-brand-50 flex items-center justify-center text-brand-600 shrink-0">
                <FileText className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 leading-snug">{document.filename}</h2>
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span className="text-xs font-mono text-slate-500">ID: {document.id}</span>
                  <span className="text-slate-300">&bull;</span>
                  <span className="text-xs text-slate-500 font-medium">{document.document_role}</span>
                  <span className="text-slate-300">&bull;</span>
                  <span className="text-xs text-slate-500">
                    Uploaded {new Date(document.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <StatusBadge status={document.status} />
            </div>
          </div>

          {/* Telemetry Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-5">
            <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg">
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Pages Processed</span>
              <div className="mt-1 text-lg font-bold text-slate-900">
                {status?.pages_processed ?? 0} / {status?.total_pages ?? document.page_count ?? '—'}
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg">
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Questions Extracted</span>
              <div className="mt-1 text-lg font-bold text-slate-900">
                {status?.questions_extracted ?? questions.length}
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg">
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Review Warnings</span>
              <div className="mt-1 text-lg font-bold text-amber-600">
                {typeof status?.review_required === 'number' ? status.review_required : reviews.length}
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg">
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">OCR Engine</span>
              <div className="mt-1 text-xs font-semibold text-slate-700">
                Tesseract + PyMuPDF
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Tabs */}
      <div className="border-b border-slate-200 flex gap-4 text-xs font-semibold">
        <button
          onClick={() => setActiveTab('questions')}
          className={`pb-2.5 transition-colors border-b-2 ${
            activeTab === 'questions'
              ? 'border-brand-600 text-brand-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Extracted Questions ({questions.length})
        </button>
        <button
          onClick={() => setActiveTab('reviews')}
          className={`pb-2.5 transition-colors border-b-2 ${
            activeTab === 'reviews'
              ? 'border-brand-600 text-brand-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Review Items ({reviews.length})
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === 'questions' ? (
        <Card>
          <CardHeader>
            <CardTitle>Structured Questions</CardTitle>
            <CardDescription>Questions identified across document pages</CardDescription>
          </CardHeader>

          {questions.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={<HelpCircle className="w-6 h-6 text-slate-400" />}
                title="No questions extracted yet"
                description="This document may still be processing or contains no recognizable questions."
              />
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {questions.map((q) => (
                <div key={q.id} className="p-5 hover:bg-slate-50/60 transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                          Q{q.question_number || '—'}
                        </span>
                        <span className="text-[11px] font-mono text-slate-500 uppercase">{q.question_type}</span>
                        <StatusBadge status={q.status} />
                        <ConfidenceBadge score={q.confidence_score} />
                      </div>
                      <p className="text-xs text-slate-800 font-medium leading-relaxed">{q.question_text}</p>
                    </div>

                    <NavLink
                      to={`/questions/${q.id}`}
                      className="text-xs font-semibold text-brand-600 hover:text-brand-700 shrink-0 inline-flex items-center gap-1"
                    >
                      Detail <ExternalLink className="w-3.5 h-3.5" />
                    </NavLink>
                  </div>

                  {/* Options List */}
                  {q.options && q.options.length > 0 && (
                    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 pl-4 border-l-2 border-slate-200">
                      {q.options.map((opt) => (
                        <div key={opt.id} className="text-xs flex items-center gap-2">
                          <span className="w-5 h-5 rounded bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-[10px]">
                            {opt.label}
                          </span>
                          <span className="text-slate-700">{opt.option_text}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Human Review Warnings</CardTitle>
            <CardDescription>Issues requiring operator verification</CardDescription>
          </CardHeader>

          {reviews.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={<CheckCircle2 className="w-6 h-6 text-emerald-500" />}
                title="No review items"
                description="Extraction passed all confidence and structural consistency validations."
              />
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {reviews.map((rev) => (
                <div key={rev.id} className="p-4 flex items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-900">{rev.reason}</span>
                      <StatusBadge status={rev.severity} />
                      <StatusBadge status={rev.status} />
                    </div>
                    <p className="text-xs text-slate-600">{rev.description || 'No description provided.'}</p>
                  </div>
                  <NavLink
                    to="/reviews"
                    className="text-xs font-semibold text-brand-600 hover:text-brand-700 shrink-0"
                  >
                    Open in Queue &rarr;
                  </NavLink>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};
