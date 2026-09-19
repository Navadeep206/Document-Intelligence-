import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, RefreshCw, Filter, Check, X } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { getReviewsApi, resolveReviewApi } from '@/api/reviews';
import { ReviewItem, ReviewStatus } from '@/types/review';
import { extractErrorMessage } from '@/api/axios';

export const Reviews: React.FC = () => {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('OPEN');
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedReview, setSelectedReview] = useState<ReviewItem | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState<string>('');
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchReviews = async () => {
    setLoading(true);
    try {
      const res = await getReviewsApi({
        status: statusFilter || undefined,
      });
      setReviews(res.items);
    } catch (err) {
      console.error('Failed to load review items', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, [statusFilter]);

  const handleResolve = async (newStatus: 'RESOLVED' | 'IGNORED') => {
    if (!selectedReview) return;
    setIsResolving(true);
    setActionError(null);

    try {
      await resolveReviewApi(selectedReview.id, {
        status: newStatus,
        notes: resolutionNotes || 'Resolved via web review dashboard.',
      });
      setSelectedReview(null);
      setResolutionNotes('');
      fetchReviews();
    } catch (err: unknown) {
      setActionError(extractErrorMessage(err));
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Human Review Queue</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Audit low-confidence questions, ambiguous answers, and missing options.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={fetchReviews}
          leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
        >
          Refresh Queue
        </Button>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 p-3 bg-white border border-slate-200 rounded-xl text-xs">
        <div className="flex items-center gap-1.5 text-slate-500 font-medium">
          <Filter className="w-3.5 h-3.5" />
          <span>Filter Status:</span>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">All Review Items</option>
          <option value="OPEN">Open (Needs Attention)</option>
          <option value="RESOLVED">Resolved</option>
          <option value="IGNORED">Ignored</option>
        </select>
      </div>

      {/* Review Queue Card */}
      <Card>
        <CardHeader>
          <CardTitle>Review Items ({reviews.length})</CardTitle>
          <CardDescription>Items automatically flagged by the confidence engine</CardDescription>
        </CardHeader>

        {loading ? (
          <div className="py-16 flex justify-center">
            <Spinner size="md" label="Loading review queue..." />
          </div>
        ) : reviews.length === 0 ? (
          <div className="p-8">
            <EmptyState
              icon={<CheckCircle2 className="w-6 h-6 text-emerald-500" />}
              title="No review items"
              description="Everything currently looks good! All extractions meet confidence criteria."
            />
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {reviews.map((item) => (
              <div
                key={item.id}
                className="p-5 hover:bg-slate-50/70 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-1.5 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold text-slate-900">{item.reason.replace(/_/g, ' ')}</span>
                    <StatusBadge status={item.severity} />
                    <StatusBadge status={item.status} />
                    <span className="text-[11px] text-slate-400">
                      Flagged {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {item.description || 'No description recorded.'}
                  </p>
                  {item.notes && (
                    <p className="text-[11px] text-slate-500 italic bg-slate-50 p-2 rounded border border-slate-200/60">
                      Note: {item.notes}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {item.question_id && (
                    <NavLink
                      to={`/questions/${item.question_id}`}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900 border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                    >
                      View Question
                    </NavLink>
                  )}

                  {item.status === 'OPEN' && (
                    <Button
                      size="sm"
                      onClick={() => {
                        setSelectedReview(item);
                        setResolutionNotes('');
                      }}
                      leftIcon={<Check className="w-3.5 h-3.5" />}
                    >
                      Resolve
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Resolve Modal */}
      <Modal
        isOpen={!!selectedReview}
        onClose={() => setSelectedReview(null)}
        title="Resolve Review Item"
      >
        {selectedReview && (
          <div className="space-y-4">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Issue</p>
              <p className="text-sm font-bold text-slate-900 mt-0.5">
                {selectedReview.reason.replace(/_/g, ' ')}
              </p>
              <p className="text-xs text-slate-600 mt-1">{selectedReview.description}</p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Resolution Notes (Optional)
              </label>
              <textarea
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                placeholder="Describe actions taken or corrections made..."
                rows={3}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {actionError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700">
                {actionError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedReview(null)}
                disabled={isResolving}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleResolve('IGNORED')}
                isLoading={isResolving}
              >
                Dismiss / Ignore
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleResolve('RESOLVED')}
                isLoading={isResolving}
              >
                Confirm Resolved
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
