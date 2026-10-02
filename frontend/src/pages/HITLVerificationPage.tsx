import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  Check,
  X,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Loader2,
  AlertCircle,
  Package,
  Image as ImageIcon,
  FileText,
  CheckCircle2,
} from 'lucide-react';
import { getProducts, getProduct } from '../api/productApi';
import { getProductImages, normalizeImageUrl } from '../api/imageApi';
import {
  getCurrentAIGeneration,
  triggerAIGeneration,
  getAIGenerationStatus,
  acceptAllAIMetadata,
  reviewAIMetadata,
} from '../api/aiApi';
import type { Product } from '../types/product';
import type { ProductImage } from '../types/image';
import type {
  AIGenerationStatusResponse,
  FieldReviewAction,
  FieldReviewDecision,
} from '../types/ai';
import { getErrorMessage } from '../api/client';

export const HITLVerificationPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [products, setProducts] = useState<Product[]>([]);
  const [currentProduct, setCurrentProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [activeImageIdx, setActiveImageIdx] = useState<number>(0);

  const [generation, setGeneration] = useState<AIGenerationStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // 1. Fetch catalog queue
  useEffect(() => {
    let isMounted = true;
    getProducts()
      .then((prods) => {
        if (isMounted) {
          setProducts(prods);
          if (!id && prods.length > 0) {
            navigate(`/ops/hitl/${prods[0].id}`, { replace: true });
          }
        }
      })
      .catch((err) => setError(getErrorMessage(err)));

    return () => {
      isMounted = false;
    };
  }, [id, navigate]);

  const productId = Number(id) || (products[0] ? products[0].id : null);

  // 2. Fetch specific product assets and active AI draft
  const loadProductData = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    setError(null);
    try {
      const [prod, imgs, gen] = await Promise.all([
        getProduct(productId),
        getProductImages(productId).catch(() => []),
        getCurrentAIGeneration(productId).catch(() => null),
      ]);
      setCurrentProduct(prod);
      setImages(imgs);
      setGeneration(gen);
      setActiveImageIdx(0);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    loadProductData();
  }, [loadProductData]);

  // Navigate between SKUs in queue
  const currentIndex = products.findIndex((p) => p.id === productId);
  const handlePrev = () => {
    if (currentIndex > 0) {
      navigate(`/ops/hitl/${products[currentIndex - 1].id}`);
    }
  };
  const handleNext = () => {
    if (currentIndex < products.length - 1) {
      navigate(`/ops/hitl/${products[currentIndex + 1].id}`);
    }
  };

  // Trigger Gemini AI generation
  const handleTriggerAI = async () => {
    if (!productId) return;
    setActionLoading(true);
    setError(null);
    setMessage('Dispatched multimodal extraction to Gemini 3.1 Flash Lite...');
    try {
      const res = await triggerAIGeneration(productId);
      // Poll until finished
      const pollInterval = setInterval(async () => {
        try {
          const st = await getAIGenerationStatus(productId, res.generation_id);
          setGeneration(st);
          if (st.status === 'completed' || st.status === 'failed') {
            clearInterval(pollInterval);
            setActionLoading(false);
            setMessage(
              st.status === 'completed'
                ? 'AI extraction completed successfully.'
                : `AI extraction failed: ${st.error_message || 'Validation error'}`
            );
          }
        } catch {
          clearInterval(pollInterval);
          setActionLoading(false);
        }
      }, 1500);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
      setActionLoading(false);
    }
  };

  // Approve all suggested fields
  const handleApproveAll = async () => {
    if (!productId) return;
    setActionLoading(true);
    setError(null);
    try {
      await acceptAllAIMetadata(productId);
      setMessage('All suggested AI metadata accepted & promoted to canonical catalog.');
      loadProductData();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  // Single Field Decision: Accept or Reject
  const handleFieldDecision = async (
    fieldKey: string,
    action: FieldReviewAction,
    modifiedVal?: unknown
  ) => {
    if (!productId) return;
    setActionLoading(true);
    setError(null);
    try {
      const decisionPayload: Record<string, FieldReviewDecision> = {
        [fieldKey]: {
          action,
          modified_value: action === 'modify' ? modifiedVal : undefined,
        },
      };
      await reviewAIMetadata(productId, decisionPayload);
      loadProductData();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !currentProduct) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-2" />
        <p className="text-sm text-slate-500">Loading HITL Verification Queue...</p>
      </div>
    );
  }

  if (!currentProduct) {
    return (
      <div className="py-16 text-center space-y-2">
        <Package className="w-10 h-10 text-slate-300 mx-auto" />
        <h3 className="text-base font-bold text-slate-900">No SKUs in Review Queue</h3>
        <p className="text-xs text-slate-500">Add products to your catalog to begin HITL review.</p>
      </div>
    );
  }

  const activeImg = images[activeImageIdx] || images[0];
  const aiOutput = generation?.output;
  const acceptance = generation?.acceptance_state || {};

  return (
    <div className="space-y-6">
      {/* Top SKU Queue Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-2xs space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center space-x-2 text-[11px] font-mono font-medium text-slate-500">
              <span>SKU: {currentProduct.sku}</span>
              <span>•</span>
              <span>Product #{currentProduct.id}</span>
              <span>•</span>
              <span className="text-indigo-600 font-semibold">Human-in-the-Loop Active</span>
            </div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight mt-1">
              {currentProduct.title}
            </h1>
          </div>

          {/* Queue Navigation & Actions */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200">
              <button
                onClick={handlePrev}
                disabled={currentIndex <= 0}
                className="p-1 rounded hover:bg-white text-slate-600 disabled:opacity-30"
                title="Previous SKU"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 text-xs font-mono font-semibold text-slate-700">
                {currentIndex + 1} / {products.length}
              </span>
              <button
                onClick={handleNext}
                disabled={currentIndex >= products.length - 1}
                className="p-1 rounded hover:bg-white text-slate-600 disabled:opacity-30"
                title="Next SKU"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <button
              onClick={handleTriggerAI}
              disabled={actionLoading}
              className="px-3 py-2 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold border border-indigo-200 shadow-2xs transition-colors flex items-center space-x-1.5"
            >
              {actionLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              <span>Extract AI Specs</span>
            </button>

            <button
              onClick={handleApproveAll}
              disabled={actionLoading || !aiOutput}
              className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition-colors flex items-center space-x-1.5 disabled:opacity-40"
            >
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span>Approve All Suggested</span>
            </button>
          </div>
        </div>

        {/* Catalog Safety Alert */}
        <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3 text-xs text-slate-600 flex items-center space-x-2">
          <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0" />
          <span>
            <strong>Catalog Safety Notice:</strong> AI suggestions require human approval prior to
            canonical catalog ingestion. Only fields marked Accepted or Modified are published to
            FAISS and Customer Discovery.
          </span>
        </div>

        {/* Review Progress Bar (Stitch Image 4) */}
        {aiOutput && (
          <div className="flex items-center justify-between text-xs pt-1 px-1">
            <span className="text-slate-600 font-medium">
              Review Progress:{' '}
              <strong className="text-indigo-600">
                {Object.values(acceptance).filter((v) => v === 'accepted' || v === 'modified').length}
              </strong>{' '}
              of 5 Fields Reviewed
            </span>
            <div className="w-48 h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
              <div
                className="h-full bg-indigo-600 rounded-full transition-all duration-300"
                style={{
                  width: `${
                    (Object.values(acceptance).filter((v) => v === 'accepted' || v === 'modified')
                      .length /
                      5) *
                    100
                  }%`,
                }}
              />
            </div>
          </div>
        )}

        {message && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{message}</span>
          </div>
        )}

        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Main Two-Column Review Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Supplier Ground Truth & Ingested Assets (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-slate-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Supplier Ground Truth &amp; Assets
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                READ-ONLY PIPELINE
              </span>
            </div>

            {/* Ingested Asset Image Preview */}
            <div className="space-y-2">
              <div className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                <span>Ingested Product Images ({images.length})</span>
                <span className="text-[10px] text-slate-400 font-mono">Grounding Source</span>
              </div>
              <div className="w-full h-56 bg-slate-100 rounded-lg overflow-hidden border border-slate-200 flex items-center justify-center relative">
                {activeImg ? (
                  <img
                    src={normalizeImageUrl(activeImg.image_url)}
                    alt={currentProduct.title}
                    className="w-full h-full object-contain p-3"
                  />
                ) : (
                  <ImageIcon className="w-12 h-12 text-slate-300" />
                )}
              </div>

              {images.length > 1 && (
                <div className="flex items-center space-x-2 overflow-x-auto pt-1">
                  {images.map((img, idx) => (
                    <button
                      key={img.id}
                      onClick={() => setActiveImageIdx(idx)}
                      className={`w-12 h-12 rounded border overflow-hidden shrink-0 ${
                        idx === activeImageIdx
                          ? 'border-indigo-600 ring-1 ring-indigo-200'
                          : 'border-slate-200'
                      }`}
                    >
                      <img
                        src={normalizeImageUrl(img.image_url)}
                        alt={`Asset ${idx + 1}`}
                        className="w-full h-full object-cover"
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Raw Supplier Title */}
            <div className="space-y-1 pt-2 border-t border-slate-100 text-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                Raw Supplier SKU Title
              </span>
              <p className="font-semibold text-slate-900 bg-slate-50 p-2.5 rounded border border-slate-100">
                {currentProduct.title}
              </p>
            </div>

            {/* Raw Ingested Specifications / Description */}
            <div className="space-y-1 pt-2 border-t border-slate-100 text-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                Raw Ingested Description / Corpus
              </span>
              <p className="text-slate-600 bg-slate-50 p-2.5 rounded border border-slate-100 leading-relaxed max-h-36 overflow-y-auto whitespace-pre-line">
                {currentProduct.description || 'No raw supplier description provided.'}
              </p>
            </div>

            {/* Ingested JSON Specifications Payload */}
            <div className="space-y-1 pt-2 border-t border-slate-100 text-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Raw Ingested Specifications</span>
                <span className="font-mono text-[10px] text-slate-400">Supplier JSON Payload</span>
              </span>
              <pre className="p-3 bg-slate-900 text-slate-200 rounded-lg text-[10px] font-mono overflow-x-auto leading-tight">
                {JSON.stringify(
                  {
                    sku: currentProduct.sku,
                    price: currentProduct.price,
                    brand: currentProduct.brand,
                    category_id: currentProduct.category_id,
                    status: currentProduct.status,
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          </div>
        </div>

        {/* Right Column: AI Metadata Enrichment & Human Review (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-indigo-600" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  AI Metadata Enrichment &amp; Human Review
                </h3>
              </div>
              <span className="text-[10px] font-mono text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                Google Gemini &bull; gemini-3.1-flash-lite
              </span>
            </div>

            {!aiOutput ? (
              <div className="py-12 text-center space-y-3">
                <Sparkles className="w-10 h-10 text-slate-300 mx-auto" />
                <h4 className="text-sm font-semibold text-slate-800">
                  No AI Metadata Draft Available
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click below to dispatch multimodal image and text analysis to Gemini 3.1 Flash Lite.
                </p>
                <button
                  onClick={handleTriggerAI}
                  disabled={actionLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors inline-flex items-center space-x-1.5"
                >
                  {actionLoading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" />
                  )}
                  <span>Generate Metadata</span>
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Field 01: Canonical Product Title */}
                {aiOutput.title && (
                  <div className="border border-slate-200 rounded-xl p-4 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                          Field 01
                        </span>
                        <span className="font-semibold text-xs text-slate-900">
                          Commercial Product Title
                        </span>
                        {aiOutput.title.confidence !== undefined && (
                          <span className="text-[10px] font-mono text-slate-500">
                            Confidence: {(aiOutput.title.confidence * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          acceptance['title'] === 'accepted'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : acceptance['title'] === 'modified'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200'
                            : acceptance['title'] === 'rejected'
                            ? 'bg-rose-50 text-rose-700 border border-rose-200'
                            : 'bg-purple-50 text-purple-700 border border-purple-200'
                        }`}
                      >
                        {acceptance['title'] || 'pending'}
                      </span>
                    </div>

                    <p className="text-xs text-slate-800 bg-slate-50 p-2.5 rounded-lg border border-slate-100 font-medium">
                      {aiOutput.title.value}
                    </p>

                    <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 flex-wrap gap-2">
                      <span className="text-slate-400">
                        Grounding: {aiOutput.title.evidence?.explanation || 'Supplier Spec'}
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <button
                          onClick={() => handleFieldDecision('title', 'accept')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded text-xs font-semibold transition-colors flex items-center gap-1"
                        >
                          <Check className="w-3 h-3" />
                          <span>Accept</span>
                        </button>
                        <button
                          onClick={() => handleFieldDecision('title', 'reject')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded text-xs font-semibold transition-colors flex items-center gap-1"
                        >
                          <X className="w-3 h-3" />
                          <span>Reject</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Field 02: Description / Summary */}
                {aiOutput.description && (
                  <div className="border border-slate-200 rounded-xl p-4 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                          Field 02
                        </span>
                        <span className="font-semibold text-xs text-slate-900">
                          Storefront Product Summary
                        </span>
                        {aiOutput.description.confidence !== undefined && (
                          <span className="text-[10px] font-mono text-slate-500">
                            Confidence: {(aiOutput.description.confidence * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          acceptance['description'] === 'accepted'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : acceptance['description'] === 'modified'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200'
                            : acceptance['description'] === 'rejected'
                            ? 'bg-rose-50 text-rose-700 border border-rose-200'
                            : 'bg-purple-50 text-purple-700 border border-purple-200'
                        }`}
                      >
                        {acceptance['description'] || 'pending'}
                      </span>
                    </div>

                    <p className="text-xs text-slate-800 bg-slate-50 p-2.5 rounded-lg border border-slate-100 leading-relaxed">
                      {aiOutput.description.value}
                    </p>

                    <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 flex-wrap gap-2">
                      <span className="text-slate-400">
                        Grounding: {aiOutput.description.evidence?.explanation || 'Supplier OCR'}
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <button
                          onClick={() => handleFieldDecision('description', 'accept')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded text-xs font-semibold transition-colors flex items-center gap-1"
                        >
                          <Check className="w-3 h-3" />
                          <span>Accept</span>
                        </button>
                        <button
                          onClick={() => handleFieldDecision('description', 'reject')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded text-xs font-semibold transition-colors flex items-center gap-1"
                        >
                          <X className="w-3 h-3" />
                          <span>Reject</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Field 03: Tags & Semantic Traits */}
                {aiOutput.tags && (
                  <div className="border border-slate-200 rounded-xl p-4 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                          Field 03
                        </span>
                        <span className="font-semibold text-xs text-slate-900">
                          Search Semantic Traits &amp; Keywords
                        </span>
                      </div>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          acceptance['tags'] === 'accepted'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-purple-50 text-purple-700 border border-purple-200'
                        }`}
                      >
                        {acceptance['tags'] || 'pending'}
                      </span>
                    </div>

                    <div className="flex flex-wrap gap-1.5 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                      {Array.isArray(aiOutput.tags) ? (
                        aiOutput.tags.map((t: string, i: number) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-[11px] font-medium text-slate-700"
                          >
                            #{t}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-slate-500">No tags generated.</span>
                      )}
                    </div>

                    <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 flex-wrap gap-2">
                      <span className="text-slate-400">
                        Grounding: Product Image &amp; Keywords
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <button
                          onClick={() => handleFieldDecision('tags', 'accept')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded text-xs font-semibold transition-colors"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => handleFieldDecision('tags', 'reject')}
                          disabled={actionLoading}
                          className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded text-xs font-semibold transition-colors"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Field 04+: Rich Attributes */}
                {aiOutput.attributes &&
                  Object.entries(aiOutput.attributes).map(([attrKey, attrNode], i) => (
                    <div key={attrKey} className="border border-slate-200 rounded-xl p-4 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="font-mono text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                            Field 0{i + 4}
                          </span>
                          <span className="font-semibold text-xs text-slate-900 capitalize">
                            {attrKey.replace(/_/g, ' ')}
                          </span>
                          {attrNode.confidence !== undefined && (
                            <span className="text-[10px] font-mono text-slate-500">
                              Confidence: {(attrNode.confidence * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <span
                          className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                            acceptance[attrKey] === 'accepted'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : acceptance[attrKey] === 'modified'
                              ? 'bg-blue-50 text-blue-700 border border-blue-200'
                              : acceptance[attrKey] === 'rejected'
                              ? 'bg-rose-50 text-rose-700 border border-rose-200'
                              : 'bg-purple-50 text-purple-700 border border-purple-200'
                          }`}
                        >
                          {acceptance[attrKey] || 'pending'}
                        </span>
                      </div>

                      <div className="text-xs text-slate-800 bg-slate-50 p-2.5 rounded-lg border border-slate-100 font-medium">
                        {typeof attrNode.value === 'object'
                          ? JSON.stringify(attrNode.value)
                          : String(attrNode.value)}
                      </div>

                      <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 flex-wrap gap-2">
                        <span className="text-slate-400">
                          Grounding: {attrNode.evidence?.explanation || 'Authoritative Catalog Spec'}
                        </span>
                        <div className="flex items-center space-x-1.5">
                          <button
                            onClick={() => handleFieldDecision(attrKey, 'accept')}
                            disabled={actionLoading}
                            className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded text-xs font-semibold transition-colors"
                          >
                            Accept
                          </button>
                          <button
                            onClick={() => handleFieldDecision(attrKey, 'reject')}
                            disabled={actionLoading}
                            className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded text-xs font-semibold transition-colors"
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Reviewer Status Bar (Stitch Image 4) */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs flex items-center justify-between flex-wrap gap-3 text-xs text-slate-500">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-slate-800 font-medium">Human-in-the-Loop Operator Active</span>
          <span>·</span>
          <span>Changes synchronize to Canonical MySQL Catalog and trigger FAISS projection update</span>
        </div>
        <div className="flex items-center space-x-4 font-mono text-[11px] text-slate-400">
          <span>Target Model: gemini-3.1-flash-lite</span>
          <span>·</span>
          <span>Product #{currentProduct.id}</span>
        </div>
      </div>
    </div>
  );
};
