import React, { useEffect, useState } from 'react';
import { Link } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { FileText, HelpCircle, AlertTriangle, Clock, ArrowRight, RefreshCw } from 'lucide-react';
import { Card, CardBody, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { DocumentUpload } from '@/components/documents/DocumentUpload';
import { getDocumentsApi } from '@/api/documents';
import { getReviewsApi } from '@/api/reviews';
import { Document } from '@/types/document';

export const Dashboard: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [totalQuestions, setTotalQuestions] = useState<number>(0);
  const [pendingReviews, setPendingReviews] = useState<number>(0);
  const [processingCount, setProcessingCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const fetchDashboardData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const docRes = await getDocumentsApi({ page: 1, page_size: 10 });
      setDocuments(docRes.items);

      // Compute statistics directly from real API responses
      const questionsCount = docRes.items.reduce((acc, doc) => acc + (doc.question_count || 0), 0);
      setTotalQuestions(questionsCount);

      const processing = docRes.items.filter(
        (doc) => doc.status === 'PROCESSING' || doc.status === 'QUEUED' || doc.status === 'PENDING'
      ).length;
      setProcessingCount(processing);

      try {
        const revRes = await getReviewsApi({ status: 'OPEN' });
        setPendingReviews(revRes.total || revRes.items.length);
      } catch {
        // Fallback to review_count from documents if review endpoint is restricted
        const fallbackReviews = docRes.items.reduce((acc, doc) => acc + (doc.review_count || 0), 0);
        setPendingReviews(fallbackReviews);
      }
    } catch (error) {
      console.error('Failed to load dashboard data', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const stats = [
    {
      label: 'Total Documents',
      value: documents.length,
      icon: FileText,
      color: 'text-brand-600 bg-brand-50 border-brand-200',
    },
    {
      label: 'Questions Extracted',
      value: totalQuestions,
      icon: HelpCircle,
      color: 'text-emerald-600 bg-emerald-50 border-emerald-200',
    },
    {
      label: 'Needs Review',
      value: pendingReviews,
      icon: AlertTriangle,
      color: 'text-amber-600 bg-amber-50 border-amber-200',
    },
    {
      label: 'In Processing',
      value: processingCount,
      icon: Clock,
      color: 'text-sky-600 bg-sky-50 border-sky-200',
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Intelligence Dashboard</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Operational overview of examination documents, questions, and review warnings.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchDashboardData(true)}
          isLoading={refreshing}
          leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />}
        >
          Refresh Data
        </Button>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => {
          const Icon = stat.icon;
          return (
            <Card key={i} className="border-slate-200">
              <CardBody className="p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-500">{stat.label}</span>
                  <div className={`w-7 h-7 rounded-lg border flex items-center justify-center ${stat.color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl font-bold tracking-tight text-slate-900">
                    {loading ? '—' : stat.value}
                  </span>
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>

      {/* Upload Section */}
      <DocumentUpload onUploadSuccess={() => fetchDashboardData(true)} />

      {/* Recent Documents Table */}
      <Card>
        <CardHeader
          action={
            <NavLink
              to="/documents"
              className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
            >
              View All <ArrowRight className="w-3.5 h-3.5" />
            </NavLink>
          }
        >
          <CardTitle>Recent Documents</CardTitle>
          <CardDescription>Processed examination papers and question keys</CardDescription>
        </CardHeader>

        {loading ? (
          <div className="py-12 flex justify-center">
            <Spinner size="md" label="Loading documents..." />
          </div>
        ) : documents.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No documents yet"
              description="Upload your first question paper or answer key above to start extracting questions."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200 uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Pages</th>
                  <th className="py-3 px-4">Questions</th>
                  <th className="py-3 px-4">Created</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {documents.slice(0, 5).map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3 px-4 font-medium text-slate-900 truncate max-w-[200px]">
                      {doc.filename}
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-[11px] font-mono text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                        {doc.document_role}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="py-3 px-4 text-slate-700">{doc.page_count ?? '—'}</td>
                    <td className="py-3 px-4 text-slate-700">{doc.question_count ?? '—'}</td>
                    <td className="py-3 px-4 text-slate-500">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <NavLink
                        to={`/documents/${doc.id}`}
                        className="inline-flex items-center text-xs font-medium text-brand-600 hover:text-brand-700"
                      >
                        Details &rarr;
                      </NavLink>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
