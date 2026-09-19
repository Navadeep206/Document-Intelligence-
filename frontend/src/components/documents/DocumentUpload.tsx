import React, { useRef, useState } from 'react';
import { UploadCloud, FileText, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { DocumentRole, DocumentUploadAcceptedResponse } from '@/types/document';
import { uploadDocumentApi } from '@/api/documents';
import { extractErrorMessage } from '@/api/axios';

export interface DocumentUploadProps {
  onUploadSuccess?: (response: DocumentUploadAcceptedResponse) => void;
  className?: string;
}

const ALLOWED_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];
const MAX_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUploadSuccess, className = '' }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [role, setRole] = useState<DocumentRole>('QUESTION_PAPER');
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const validateFile = (file: File): boolean => {
    setError(null);
    setSuccess(null);

    const ext = file.name.split('.').pop()?.toLowerCase();
    const isAllowedExt = ext && ['pdf', 'jpg', 'jpeg', 'png'].includes(ext);

    if (!ALLOWED_TYPES.includes(file.type) && !isAllowedExt) {
      setError('Invalid file format. Only PDF, JPG, JPEG, and PNG files are supported.');
      return false;
    }

    if (file.size > MAX_SIZE_BYTES) {
      setError('File size exceeds the 25 MB limit.');
      return false;
    }

    return true;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      } else {
        setSelectedFile(null);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      } else {
        setSelectedFile(null);
      }
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await uploadDocumentApi(selectedFile, role);
      setSuccess(`"${selectedFile.name}" uploaded and queued for processing!`);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      if (onUploadSuccess) {
        onUploadSuccess(res);
      }
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`bg-white rounded-xl border border-slate-200 p-6 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Upload Examination Document</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Ingest question papers or answer keys for automated OCR and extraction.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-600">Role:</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as DocumentRole)}
            className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500"
            disabled={isUploading}
          >
            <option value="QUESTION_PAPER">Question Paper</option>
            <option value="ANSWER_KEY">Official Answer Key</option>
          </select>
        </div>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-brand-500 bg-brand-50/50'
            : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
        }`}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-brand-50 flex items-center justify-center text-brand-600 mb-3">
            <UploadCloud className="w-6 h-6" />
          </div>
          <p className="text-sm font-medium text-slate-800">
            Click to upload <span className="text-slate-500 font-normal">or drag and drop</span>
          </p>
          <p className="text-xs text-slate-500 mt-1">PDF, JPG, JPEG, or PNG (up to 25 MB)</p>
        </div>
      </div>

      {selectedFile && (
        <div className="mt-4 flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <FileText className="w-5 h-5 text-brand-600 shrink-0" />
            <div className="truncate">
              <p className="text-xs font-medium text-slate-800 truncate">{selectedFile.name}</p>
              <p className="text-[11px] text-slate-500">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
          </div>
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              handleUpload();
            }}
            isLoading={isUploading}
          >
            Start Processing
          </Button>
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="mt-3 flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
          <span>{success}</span>
        </div>
      )}
    </div>
  );
};
