import React, { useState } from 'react';
import { Check, X, Edit3, Sparkles } from 'lucide-react';
import type { AcceptanceStatus, Evidence } from '../types/ai';

interface FieldReviewCardProps {
  fieldName: string;
  fieldLabel: string;
  isCanonical: boolean;
  valueRender: React.ReactNode;
  confidence?: number | null;
  evidence?: Evidence | null;
  status: AcceptanceStatus;
  initialModifyValue?: string;
  isModifyingCategory?: boolean;
  onDecision: (action: 'accept' | 'modify' | 'reject', modifiedValue?: unknown) => Promise<void>;
  loading?: boolean;
}

export const FieldReviewCard: React.FC<FieldReviewCardProps> = ({
  fieldName,
  fieldLabel,
  isCanonical,
  valueRender,
  confidence,
  evidence,
  status,
  initialModifyValue = '',
  isModifyingCategory = false,
  onDecision,
  loading = false,
}) => {
  const [showModifyInput, setShowModifyInput] = useState<boolean>(false);
  const [modifiedValue, setModifiedValue] = useState<string>(initialModifyValue);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const getStatusBadge = (st: AcceptanceStatus) => {
    switch (st) {
      case 'accepted':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-50 text-emerald-700 border border-emerald-200">Accepted</span>;
      case 'modified':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-50 text-blue-700 border border-blue-200">Modified</span>;
      case 'rejected':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-rose-50 text-rose-700 border border-rose-200">Rejected</span>;
      case 'pending':
      default:
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-50 text-amber-700 border border-amber-200">Pending Review</span>;
    }
  };

  const handleAction = async (action: 'accept' | 'reject') => {
    setActionInProgress(action);
    try {
      await onDecision(action);
      setShowModifyInput(false);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleModifySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionInProgress('modify');
    try {
      const val = isModifyingCategory ? Number(modifiedValue) : modifiedValue;
      await onDecision('modify', val);
      setShowModifyInput(false);
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-white shadow-2xs space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-sm text-slate-900">{fieldLabel}</span>
          <span className="text-[11px] font-mono text-slate-400">({fieldName})</span>
          {isCanonical ? (
            <span className="px-1.5 py-0.5 text-[10px] uppercase font-medium tracking-wide bg-slate-100 text-slate-600 rounded">
              Canonical Column
            </span>
          ) : (
            <span className="px-1.5 py-0.5 text-[10px] uppercase font-medium tracking-wide bg-purple-50 text-purple-700 border border-purple-200 rounded">
              Discovery Metadata
            </span>
          )}
        </div>
        <div>{getStatusBadge(status)}</div>
      </div>

      {/* Value Container */}
      <div className="bg-slate-50 border border-slate-100 rounded-md p-3 text-sm text-slate-800">
        {valueRender}
      </div>

      {/* Confidence & Evidence Footer */}
      {(confidence !== undefined && confidence !== null) || evidence ? (
        <div className="flex items-center justify-between text-xs text-slate-500 pt-1 border-t border-slate-100 flex-wrap gap-2">
          <div className="flex items-center space-x-3">
            {confidence !== undefined && confidence !== null && (
              <span className="flex items-center space-x-1 font-mono">
                <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                <span>Confidence: {confidence.toFixed(2)}</span>
              </span>
            )}
            {evidence && (
              <span className="flex items-center space-x-1">
                <span className="text-slate-400">Source:</span>
                <span className="font-medium capitalize text-slate-700">
                  {evidence.source.type === 'image' ? `Image #${evidence.source.image_id}` : evidence.source.type}
                </span>
              </span>
            )}
          </div>
          {evidence?.explanation && (
            <span className="italic text-slate-400 truncate max-w-[280px]" title={evidence.explanation}>
              "{evidence.explanation}"
            </span>
          )}
        </div>
      ) : null}

      {/* Review Actions */}
      <div className="pt-2 flex items-center justify-between gap-2 border-t border-slate-100">
        <div className="flex items-center space-x-2">
          <button
            type="button"
            disabled={loading || actionInProgress !== null}
            onClick={() => handleAction('accept')}
            className={`flex items-center space-x-1 px-2.5 py-1 text-xs font-medium rounded border transition-colors ${
              status === 'accepted'
                ? 'bg-emerald-600 text-white border-emerald-600'
                : 'bg-white text-emerald-700 border-emerald-300 hover:bg-emerald-50'
            }`}
          >
            <Check className="w-3.5 h-3.5" />
            <span>Accept</span>
          </button>

          <button
            type="button"
            disabled={loading || actionInProgress !== null}
            onClick={() => setShowModifyInput(!showModifyInput)}
            className={`flex items-center space-x-1 px-2.5 py-1 text-xs font-medium rounded border transition-colors ${
              status === 'modified' || showModifyInput
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-blue-700 border-blue-300 hover:bg-blue-50'
            }`}
          >
            <Edit3 className="w-3.5 h-3.5" />
            <span>{showModifyInput ? 'Cancel' : 'Modify'}</span>
          </button>

          <button
            type="button"
            disabled={loading || actionInProgress !== null}
            onClick={() => handleAction('reject')}
            className={`flex items-center space-x-1 px-2.5 py-1 text-xs font-medium rounded border transition-colors ${
              status === 'rejected'
                ? 'bg-rose-600 text-white border-rose-600'
                : 'bg-white text-rose-700 border-rose-300 hover:bg-rose-50'
            }`}
          >
            <X className="w-3.5 h-3.5" />
            <span>Reject</span>
          </button>
        </div>

        {!isCanonical && (
          <span className="text-[11px] text-slate-400 hidden sm:inline">
            Applies to discovery state only
          </span>
        )}
      </div>

      {/* Inline Modify Input */}
      {showModifyInput && (
        <form onSubmit={handleModifySubmit} className="pt-2 space-y-2 bg-blue-50/50 p-3 rounded-md border border-blue-100">
          <label className="block text-xs font-medium text-slate-700">
            {isModifyingCategory ? 'Enter Category ID (Integer):' : 'Enter Seller Override Value:'}
          </label>
          {fieldName === 'description' ? (
            <textarea
              rows={3}
              value={modifiedValue}
              onChange={(e) => setModifiedValue(e.target.value)}
              placeholder="Enter custom description..."
              required
              className="w-full text-xs p-2 rounded border border-slate-300 bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            />
          ) : (
            <input
              type={isModifyingCategory ? 'number' : 'text'}
              value={modifiedValue}
              onChange={(e) => setModifiedValue(e.target.value)}
              placeholder={isModifyingCategory ? 'e.g. 2' : 'Enter custom value...'}
              required
              className="w-full text-xs p-2 rounded border border-slate-300 bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            />
          )}
          <div className="flex justify-end space-x-2">
            <button
              type="button"
              onClick={() => setShowModifyInput(false)}
              className="px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || actionInProgress !== null}
              className="px-3 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded shadow-xs"
            >
              {actionInProgress === 'modify' ? 'Submitting...' : 'Apply Modification'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
