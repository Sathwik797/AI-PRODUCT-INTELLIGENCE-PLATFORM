import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Sparkles,
  Loader2,
  CheckCheck,
  AlertTriangle,
  RotateCcw,
  Tag,
  Cpu,
  Layers,
} from 'lucide-react';
import type {
  AIGenerationStatusResponse,
  AttributeField,
  FieldReviewAction,
  TypedNode,
} from '../types/ai';
import {
  triggerAIGeneration,
  getAIGenerationStatus,
  getCurrentAIGeneration,
  acceptAllAIMetadata,
  reviewAIMetadata,
} from '../api/aiApi';
import { getErrorMessage } from '../api/client';
import { FieldReviewCard } from './FieldReviewCard';

interface AIStudioProps {
  productId: number;
  onProductUpdated: () => void;
}

export const AIStudio: React.FC<AIStudioProps> = ({ productId, onProductUpdated }) => {
  const [generation, setGeneration] = useState<AIGenerationStatusResponse | null>(null);
  const [loadingInitial, setLoadingInitial] = useState<boolean>(true);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [acting, setActing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const pollingTimerRef = useRef<number | null>(null);

  const clearPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  const pollGeneration = useCallback(
    (genId: number) => {
      clearPolling();
      pollingTimerRef.current = window.setInterval(async () => {
        try {
          const statusRes = await getAIGenerationStatus(productId, genId);
          setGeneration(statusRes);

          if (statusRes.status === 'completed' || statusRes.status === 'failed') {
            clearPolling();
            if (statusRes.status === 'completed') {
              onProductUpdated();
            }
          }
        } catch (err: unknown) {
          setError(getErrorMessage(err));
          clearPolling();
        }
      }, 1500);
    },
    [productId, clearPolling, onProductUpdated]
  );

  // Load active generation draft on initial mount or product change
  useEffect(() => {
    let isMounted = true;
    setLoadingInitial(true);
    setError(null);

    getCurrentAIGeneration(productId)
      .then((data) => {
        if (isMounted) {
          setGeneration(data);
          setLoadingInitial(false);
          // If active generation is still processing, resume polling
          if (data && (data.status === 'pending' || data.status === 'processing')) {
            pollGeneration(data.generation_id);
          }
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(getErrorMessage(err));
          setLoadingInitial(false);
        }
      });

    return () => {
      isMounted = false;
      clearPolling();
    };
  }, [productId, clearPolling, pollGeneration]);

  const handleTrigger = async () => {
    setError(null);
    setFeedback(null);
    setTriggering(true);
    clearPolling();

    try {
      const triggerRes = await triggerAIGeneration(productId);
      // Immediately set placeholder generation with pending status
      setGeneration({
        generation_id: triggerRes.generation_id,
        product_id: triggerRes.product_id,
        generation_number: (generation?.generation_number || 0) + 1,
        status: 'pending',
        output: null,
        acceptance_state: null,
        processing_time: null,
        error_message: null,
        started_at: null,
        completed_at: null,
        created_at: new Date().toISOString(),
      });
      // Start polling
      pollGeneration(triggerRes.generation_id);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setTriggering(false);
    }
  };

  const handleAcceptAll = async () => {
    if (!generation || generation.status !== 'completed') return;
    setError(null);
    setActing(true);

    try {
      const res = await acceptAllAIMetadata(productId);
      setFeedback(`Successfully accepted all canonical fields (${res.applied_fields.join(', ')}).`);
      // Update local acceptance state
      setGeneration((prev) => (prev ? { ...prev, acceptance_state: res.acceptance_state } : null));
      onProductUpdated();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const handleFieldDecision = async (
    fieldName: string,
    action: FieldReviewAction,
    modifiedValue?: unknown
  ) => {
    if (!generation || generation.status !== 'completed') return;
    setError(null);
    setActing(true);

    try {
      const res = await reviewAIMetadata(productId, {
        [fieldName]: { action, modified_value: modifiedValue },
      });
      setGeneration((prev) => (prev ? { ...prev, acceptance_state: res.acceptance_state } : null));
      setFeedback(`Saved review decision for '${fieldName}' (${action}).`);
      onProductUpdated();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActing(false);
    }
  };

  // Safe recursive attribute node renderer
  const renderAttributeNode = (node: TypedNode | AttributeField): React.ReactNode => {
    if (!node) return <span className="text-slate-400 italic">null</span>;

    switch (node.type) {
      case 'text':
        return node.value ?? <span className="text-slate-400 italic">Unknown / Not determined</span>;
      case 'number':
        return node.value !== null ? String(node.value) : <span className="text-slate-400 italic">Unknown</span>;
      case 'boolean':
        return node.value !== null ? (node.value ? 'Yes' : 'No') : <span className="text-slate-400 italic">Unknown</span>;
      case 'measurement':
        return node.value !== null ? `${node.value} ${node.unit || ''}` : <span className="text-slate-400 italic">Unknown</span>;
      case 'range':
        return node.value ? `${node.value.min} - ${node.value.max} ${node.unit || ''}` : <span className="text-slate-400 italic">Unknown</span>;
      case 'dimensions':
        return node.value
          ? `${node.value.length} × ${node.value.width} × ${node.value.height} ${node.unit || ''}`
          : <span className="text-slate-400 italic">Unknown</span>;
      case 'array':
        if (!node.value || node.value.length === 0) {
          return <span className="text-slate-400 italic">Empty list</span>;
        }
        return (
          <ul className="list-disc list-inside space-y-0.5">
            {node.value.map((item, idx) => (
              <li key={idx} className="text-xs">{renderAttributeNode(item)}</li>
            ))}
          </ul>
        );
      case 'object':
        if (!node.value || Object.keys(node.value).length === 0) {
          return <span className="text-slate-400 italic">Empty object</span>;
        }
        return (
          <div className="space-y-1 pl-2 border-l border-slate-200">
            {Object.entries(node.value).map(([k, v]) => (
              <div key={k} className="text-xs">
                <span className="font-semibold text-slate-700">{k}: </span>
                {renderAttributeNode(v)}
              </div>
            ))}
          </div>
        );
      default:
        return <span className="text-slate-500 font-mono text-xs">{JSON.stringify(node)}</span>;
    }
  };

  if (loadingInitial) {
    return (
      <div className="p-8 text-center bg-white rounded-lg border border-slate-200">
        <Loader2 className="w-6 h-6 text-indigo-600 animate-spin mx-auto mb-2" />
        <p className="text-sm text-slate-500">Checking active AI draft...</p>
      </div>
    );
  }

  const isPendingOrProcessing = Boolean(
    generation && (generation.status === 'pending' || generation.status === 'processing')
  );

  return (
    <div className="space-y-6">
      {/* Top Banner & Trigger Action */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-2xs">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-5 h-5 text-indigo-600" />
              <h3 className="text-base font-semibold text-slate-900">Multimodal AI Studio</h3>
              {generation && (
                <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                  Run #{generation.generation_number} (ID: {generation.generation_id})
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Analyzes all product images + seller specs via {generation?.model_name || 'gemini-3.1-flash-lite'} to suggest verified metadata.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            {generation?.status === 'completed' && (
              <button
                type="button"
                disabled={acting || triggering}
                onClick={handleAcceptAll}
                className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-md shadow-xs transition-colors disabled:opacity-50"
              >
                <CheckCheck className="w-4 h-4" />
                <span>Accept All Fields</span>
              </button>
            )}

            <button
              type="button"
              disabled={triggering || isPendingOrProcessing}
              onClick={handleTrigger}
              className="flex items-center space-x-1.5 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md shadow-xs transition-colors disabled:opacity-50"
            >
              {triggering || isPendingOrProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{generation?.status === 'processing' ? 'Processing Inference...' : 'Dispatching AI...'}</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>{generation ? 'Regenerate Metadata' : 'Generate AI Metadata'}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Notifications */}
        {error && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-md text-rose-700 text-xs flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {feedback && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-md text-emerald-800 text-xs flex items-center space-x-2">
            <CheckCheck className="w-4 h-4 shrink-0" />
            <span>{feedback}</span>
          </div>
        )}
      </div>

      {/* Progress / Status Display */}
      {isPendingOrProcessing && (
        <div className="p-8 text-center bg-white rounded-lg border border-indigo-200 shadow-2xs space-y-3 animate-pulse">
          <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
          <div className="space-y-1">
            <h4 className="text-sm font-semibold text-slate-900">
              AI Generation in Progress ({generation?.status.toUpperCase()})
            </h4>
            <p className="text-xs text-slate-500">
              Multimodal ensemble analysis running against product catalog assets. Polling for results...
            </p>
          </div>
        </div>
      )}

      {/* Failure Display */}
      {generation?.status === 'failed' && (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-lg space-y-3">
          <div className="flex items-center space-x-2 text-rose-800 font-semibold text-sm">
            <AlertTriangle className="w-5 h-5 text-rose-600" />
            <span>Generation Failed</span>
          </div>
          <p className="text-xs text-rose-700 font-mono bg-white/80 p-2 rounded border border-rose-100">
            {generation.error_message || 'An unexpected error occurred during AI processing.'}
          </p>
          <button
            type="button"
            onClick={handleTrigger}
            className="flex items-center space-x-1 px-3 py-1.5 bg-rose-600 text-white rounded text-xs font-medium hover:bg-rose-700"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Try Again</span>
          </button>
        </div>
      )}

      {/* Completed State: Review Studio */}
      {generation?.status === 'completed' && generation.output && (
        <div className="space-y-6">
          {/* Execution Metrics Bar */}
          <div className="flex items-center justify-between text-xs text-slate-500 bg-slate-100 px-4 py-2 rounded-md font-mono">
            <span className="flex items-center space-x-1.5">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span>Model: {generation.model_name || 'gemini-3.1-flash-lite'}</span>
            </span>
            <span>Latency: {generation.processing_time ? `${generation.processing_time}s` : 'N/A'}</span>
            <span>Status: Completed</span>
          </div>

          {/* Canonical Fields Section */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center space-x-1.5">
              <Layers className="w-4 h-4 text-indigo-600" />
              <span>Canonical Product Fields (Direct Catalog Overwrites on Approval)</span>
            </h4>

            <div className="grid grid-cols-1 gap-4">
              {/* Title */}
              <FieldReviewCard
                fieldName="title"
                fieldLabel="Product Title"
                isCanonical={true}
                valueRender={generation.output.title.value ?? <span className="text-slate-400 italic">Unknown / Not determined</span>}
                confidence={generation.output.title.confidence}
                evidence={generation.output.title.evidence}
                status={generation.acceptance_state?.title || 'pending'}
                initialModifyValue={generation.output.title.value || ''}
                onDecision={(act, val) => handleFieldDecision('title', act, val)}
                loading={acting}
              />

              {/* Description */}
              <FieldReviewCard
                fieldName="description"
                fieldLabel="Description"
                isCanonical={true}
                valueRender={
                  <p className="whitespace-pre-line leading-relaxed">
                    {generation.output.description.value ?? <span className="text-slate-400 italic">Unknown / Not determined</span>}
                  </p>
                }
                confidence={generation.output.description.confidence}
                evidence={generation.output.description.evidence}
                status={generation.acceptance_state?.description || 'pending'}
                initialModifyValue={generation.output.description.value || ''}
                onDecision={(act, val) => handleFieldDecision('description', act, val)}
                loading={acting}
              />

              {/* Brand */}
              <FieldReviewCard
                fieldName="brand"
                fieldLabel="Brand"
                isCanonical={true}
                valueRender={generation.output.brand.value ?? <span className="text-slate-400 italic">Unknown / Not determined</span>}
                confidence={generation.output.brand.confidence}
                evidence={generation.output.brand.evidence}
                status={generation.acceptance_state?.brand || 'pending'}
                initialModifyValue={generation.output.brand.value || ''}
                onDecision={(act, val) => handleFieldDecision('brand', act, val)}
                loading={acting}
              />

              {/* Category */}
              <FieldReviewCard
                fieldName="category"
                fieldLabel="Category Classification"
                isCanonical={true}
                isModifyingCategory={true}
                valueRender={
                  generation.output.category.value ? (
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold">Recommended Existing:</span>
                        <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded text-xs font-mono">
                          {generation.output.category.value.recommended_category_name || 'None'} (ID: {generation.output.category.value.recommended_category_id ?? 'None'})
                        </span>
                      </div>
                      {generation.output.category.value.proposed_category && (
                        <div className="text-xs text-slate-500">
                          <span>Proposed Subcategory: </span>
                          <span className="italic font-medium text-slate-700">{generation.output.category.value.proposed_category}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-slate-400 italic">Unknown / Not determined</span>
                  )
                }
                confidence={generation.output.category.confidence}
                evidence={generation.output.category.evidence}
                status={generation.acceptance_state?.category || 'pending'}
                initialModifyValue={String(generation.output.category.value?.recommended_category_id || '')}
                onDecision={(act, val) => handleFieldDecision('category', act, val)}
                loading={acting}
              />
            </div>
          </div>

          {/* Non-Canonical Discovery Metadata Section */}
          <div className="space-y-3 pt-4 border-t border-slate-200">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center space-x-1.5">
              <Tag className="w-4 h-4 text-purple-600" />
              <span>Discovery Metadata (Search Indexing & Specifications)</span>
            </h4>

            <div className="grid grid-cols-1 gap-4">
              {/* Tags */}
              <FieldReviewCard
                fieldName="tags"
                fieldLabel="Discovery Tags"
                isCanonical={false}
                valueRender={
                  generation.output.tags && generation.output.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {generation.output.tags.map((tag, idx) => (
                        <span key={idx} className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-xs">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-slate-400 italic">No tags detected</span>
                  )
                }
                status={generation.acceptance_state?.tags || 'pending'}
                onDecision={(act, val) => handleFieldDecision('tags', act, val)}
                loading={acting}
              />

              {/* Keywords */}
              <FieldReviewCard
                fieldName="keywords"
                fieldLabel="Search & SEO Keywords"
                isCanonical={false}
                valueRender={
                  generation.output.keywords && generation.output.keywords.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {generation.output.keywords.map((kw, idx) => (
                        <span key={idx} className="bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded text-xs font-mono">
                          {kw}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-slate-400 italic">No keywords detected</span>
                  )
                }
                status={generation.acceptance_state?.keywords || 'pending'}
                onDecision={(act, val) => handleFieldDecision('keywords', act, val)}
                loading={acting}
              />

              {/* Dynamic Attributes */}
              <FieldReviewCard
                fieldName="attributes"
                fieldLabel="Extracted Specifications & Attributes"
                isCanonical={false}
                valueRender={
                  generation.output.attributes && Object.keys(generation.output.attributes).length > 0 ? (
                    <div className="divide-y divide-slate-100">
                      {Object.entries(generation.output.attributes).map(([attrKey, attrVal]) => (
                        <div key={attrKey} className="py-2 first:pt-0 last:pb-0 flex items-start justify-between">
                          <div className="space-y-0.5">
                            <span className="font-semibold text-xs text-slate-900 capitalize">{attrKey}</span>
                            <div className="text-xs text-slate-700">{renderAttributeNode(attrVal)}</div>
                          </div>
                          {attrVal.confidence !== undefined && (
                            <span className="text-[10px] font-mono text-slate-400">
                              conf: {attrVal.confidence.toFixed(2)}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-slate-400 italic">No dynamic attributes extracted</span>
                  )
                }
                status={generation.acceptance_state?.attributes || 'pending'}
                onDecision={(act, val) => handleFieldDecision('attributes', act, val)}
                loading={acting}
              />
            </div>
          </div>
        </div>
      )}

      {/* Empty State when no generation exists yet */}
      {!generation && (
        <div className="p-8 text-center bg-white rounded-lg border border-dashed border-slate-200">
          <Sparkles className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm text-slate-600 font-medium">No AI metadata generated yet.</p>
          <p className="text-xs text-slate-400 mt-1">
            Click "Generate AI Metadata" above to trigger multimodal extraction with Gemini.
          </p>
        </div>
      )}
    </div>
  );
};
