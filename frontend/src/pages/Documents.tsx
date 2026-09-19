import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { RefreshCw, Filter, FileText, ArrowUpRight } from 'lucide-react';
import { Card, CardBody, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Pagination } from '@/components/ui/Pagination';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { DocumentUpload } from '@/components/documents/DocumentUpload';
import { getDocumentsApi } from '@/api/documents';
import { Document, DocumentListResponse } from '@/types/document';

export const Documents: React.FC = () => {
  const [data, setData] = useState<DocumentListResponse>({
    items: [],
    total: 0,
    page: 1,
    page_size: 10,
    total_pages: 1,
  });
  const [page, setPage] = useState<number>(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [showUpload, setShowUpload] = useState<boolean>(false);

  const fetchDocuments = async (pageNum = page) => {
    setLoading(true);
    try {
      const res = await getDocumentsApi({
        page: pageNum,
        page_size: 10,
        status: statusFilter || undefined,
        document_role: roleFilter || undefined,
      });
      setData(res);
      setPage(pageNum);
    } catch (err) {
      console.error('Failed to load documents', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments(1);
  }, [statusFilter, roleFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Documents Repository</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage examination question papers, answer keys, and view extraction status.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchDocuments(page)}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowUpload(!showUpload)}>
            {showUpload ? 'Hide Upload' : 'Upload Document'}
          </Button>
        </div>
      </div>

      {showUpload && (
        <DocumentUpload
          onUploadSuccess={() => {
            fetchDocuments(1);
            setShowUpload(false);
          }}
        />
      )}

      {/* Filters Bar */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-white border border-slate-200 rounded-xl text-xs">
        <div className="flex items-center gap-1.5 text-slate-500 font-medium">
          <Filter className="w-3.5 h-3.5" />
          <span>Filters:</span>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">All Statuses</option>
          <option value="COMPLETED">Completed</option>
          <option value="PROCESSING">Processing</option>
          <option value="QUEUED">Queued</option>
          <option value="FAILED">Failed</option>
        </select>

        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">All Roles</option>
          <option value="QUESTION_PAPER">Question Paper</option>
          <option value="ANSWER_KEY">Answer Key</option>
        </select>
      </div>

      {/* Documents Table */}
      <Card>
        <CardHeader>
          <CardTitle>Uploaded Documents ({data.total})</CardTitle>
          <CardDescription>All documents available within your tenant scope</CardDescription>
        </CardHeader>

        {loading ? (
          <div className="py-16 flex justify-center">
            <Spinner size="md" label="Loading documents..." />
          </div>
        ) : data.items.length === 0 ? (
          <div className="p-8">
            <EmptyState
              title="No matching documents found"
              description="Upload a document or adjust your filters to see results."
              action={
                <Button size="sm" onClick={() => setShowUpload(true)}>
                  Upload Document
                </Button>
              }
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
                  <th className="py-3 px-4">Reviews</th>
                  <th className="py-3 px-4">Uploaded</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3 px-4 font-medium text-slate-900 truncate max-w-[220px]">
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
                    <td className="py-3 px-4 text-slate-700">
                      {doc.review_count && doc.review_count > 0 ? (
                        <span className="text-amber-600 font-semibold">{doc.review_count}</span>
                      ) : (
                        '0'
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <NavLink
                        to={`/documents/${doc.id}`}
                        className="inline-flex items-center text-xs font-semibold text-brand-600 hover:text-brand-700"
                      >
                        Inspect <ArrowUpRight className="w-3.5 h-3.5 ml-0.5" />
                      </NavLink>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <Pagination
              currentPage={data.page}
              totalPages={data.total_pages}
              totalItems={data.total}
              pageSize={data.page_size}
              onPageChange={(p) => fetchDocuments(p)}
            />
          </div>
        )}
      </Card>
    </div>
  );
};
