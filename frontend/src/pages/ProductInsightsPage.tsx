import React, { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Sparkles,
  ShieldCheck,
  AlertCircle,
  Package,
  Send,
  Loader2,
} from 'lucide-react';
import { getProduct } from '../api/productApi';
import { getProductImages, normalizeImageUrl } from '../api/imageApi';
import { getCurrentAIGeneration } from '../api/aiApi';
import { queryRAG } from '../api/ragApi';
import { getProductRecommendations } from '../api/recommendationApi';
import { getCategories } from '../api/categoryApi';
import type { Product } from '../types/product';
import type { ProductImage } from '../types/image';
import type { AIGenerationStatusResponse, AttributeField } from '../types/ai';
import type { RAGResponse } from '../types/rag';
import type { RecommendationItem } from '../types/recommendation';
import type { Category } from '../types/category';
import { getErrorMessage } from '../api/client';
import { formatINR } from '../utils/currency';

export const ProductInsightsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);

  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [selectedImageIndex, setSelectedImageIndex] = useState<number>(0);
  const [aiDraft, setAiDraft] = useState<AIGenerationStatusResponse | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // RAG interactive assistant state
  const [ragQuery, setRagQuery] = useState<string>('');
  const [ragLoading, setRagLoading] = useState<boolean>(false);
  const [ragResponse, setRagResponse] = useState<RAGResponse | null>(null);
  const [ragError, setRagError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!productId || isNaN(productId)) {
      setError('Invalid Product ID');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [prodData, imgsData, aiData, recsData, catsData] = await Promise.all([
        getProduct(productId),
        getProductImages(productId).catch(() => []),
        getCurrentAIGeneration(productId).catch(() => null),
        getProductRecommendations(productId, 3).catch(() => ({ recommendations: [] })),
        getCategories().catch(() => []),
      ]);

      setProduct(prodData);
      sessionStorage.setItem('last_viewed_product_id', String(prodData.id));
      setImages(imgsData);
      setAiDraft(aiData);
      setRecommendations(recsData.recommendations || []);
      setCategories(catsData);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAskRAG = async (queryText: string) => {
    if (!queryText.trim()) return;
    setRagLoading(true);
    setRagError(null);
    try {
      const res = await queryRAG({ query: queryText.trim() });
      setRagResponse(res);
    } catch (err: unknown) {
      setRagError(getErrorMessage(err));
    } finally {
      setRagLoading(false);
    }
  };

  const handleRAGSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAskRAG(ragQuery);
  };

  if (loading) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-2" />
        <p className="text-sm text-slate-500">Loading Product Insights &amp; RAG Knowledge...</p>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="max-w-md mx-auto py-16 text-center space-y-3">
        <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
        <h2 className="text-base font-bold text-slate-900">Product Not Found</h2>
        <p className="text-xs text-slate-500">{error || 'Could not load product insights.'}</p>
        <Link
          to="/storefront/search"
          className="inline-flex items-center text-xs font-semibold text-indigo-600 hover:underline pt-2"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          <span>Back to Search</span>
        </Link>
      </div>
    );
  }

  const categoryObj = categories.find((c) => c.id === product.category_id);
  const activeImage = images[selectedImageIndex] || images[0];

  // Extract accepted attributes from current AI draft
  const acceptanceState = aiDraft?.acceptance_state || {};
  const acceptedAttributes: [string, AttributeField][] = aiDraft?.output?.attributes
    ? Object.entries(aiDraft.output.attributes).filter(
        ([key]) => acceptanceState[key] === 'accepted'
      )
    : [];

  const suggestedQuestions = [
    `What are the primary specifications of ${product.title}?`,
    `Is ${product.title} in stock and what is the listed price?`,
    `What is the category and brand of this item?`,
  ];

  return (
    <div className="space-y-8">
      {/* Top Breadcrumb */}
      <div className="flex items-center space-x-2 text-xs text-slate-500">
        <Link to="/storefront/search" className="hover:text-slate-800 transition-colors">
          Search Catalog
        </Link>
        <span>/</span>
        <span>{categoryObj?.name || 'Category'}</span>
        <span>/</span>
        <span className="text-slate-900 font-semibold truncate max-w-xs">{product.title}</span>
      </div>

      {/* Main 2-Column Product Insights Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Media Gallery, Catalog Details & Accepted Attributes (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Product Media Viewer */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs space-y-4">
            <div className="w-full h-80 bg-slate-100 rounded-lg overflow-hidden border border-slate-200 flex items-center justify-center relative">
              {activeImage ? (
                <img
                  src={normalizeImageUrl(activeImage.image_url)}
                  alt={product.title}
                  className="w-full h-full object-contain p-4"
                />
              ) : (
                <Package className="w-20 h-20 text-slate-300" />
              )}
              <div className="absolute bottom-2 right-2 px-2.5 py-1 rounded-md text-[10px] font-bold bg-slate-900/80 text-white backdrop-blur-xs flex items-center gap-1">
                <span>{images.length} Viewpoint{images.length !== 1 ? 's' : ''} Synced</span>
              </div>
            </div>

            {/* Thumbnail Row */}
            {images.length > 1 && (
              <div className="flex items-center space-x-2 overflow-x-auto pb-1">
                {images.map((img, idx) => (
                  <button
                    key={img.id}
                    onClick={() => setSelectedImageIndex(idx)}
                    className={`w-16 h-16 rounded-md border-2 overflow-hidden shrink-0 transition-all ${
                      idx === selectedImageIndex
                        ? 'border-indigo-600 ring-2 ring-indigo-100'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <img
                      src={normalizeImageUrl(img.image_url)}
                      alt={`View ${idx + 1}`}
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}

            {/* Product Meta & Pricing */}
            <div className="space-y-4 pt-3 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  {product.brand || categoryObj?.name || 'Catalog Product'}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border flex items-center gap-1.5 ${
                    product.status === 'ACTIVE'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-slate-100 text-slate-600 border-slate-200'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      product.status === 'ACTIVE' ? 'bg-emerald-500' : 'bg-slate-400'
                    }`}
                  />
                  <span>{product.status === 'ACTIVE' ? 'In Stock' : product.status}</span>
                </span>
              </div>

              <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight leading-snug">
                {product.title}
              </h1>

              <div className="flex items-baseline space-x-3">
                <span className="text-3xl font-extrabold font-mono text-slate-900">
                  {formatINR(product.price)}
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  SKU: <strong className="text-slate-700">{product.sku}</strong>
                </span>
              </div>

              {/* Verified Product Facts Strip (Q104) */}
              <div className="p-3 bg-slate-50/90 rounded-xl border border-slate-200/80 space-y-1.5 text-xs">
                <div className="flex items-center space-x-1.5 text-emerald-800 font-medium">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Live Catalog Synchronized</span>
                  <span className="text-slate-400 font-normal">·</span>
                  <span className="text-slate-500 text-[11px] font-mono">Price &amp; SKU verified</span>
                </div>
                {acceptedAttributes.length > 0 && (
                  <div className="flex items-center space-x-1.5 text-indigo-800 font-medium">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    <span>{acceptedAttributes.length} Accepted Specifications</span>
                    <span className="text-slate-400 font-normal">·</span>
                    <span className="text-slate-500 text-[11px]">Grounded for AI QA</span>
                  </div>
                )}
              </div>

              {product.description && (
                <div className="space-y-1 pt-1">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Product Overview
                  </span>
                  <p className="text-xs text-slate-600 leading-relaxed bg-white p-3 rounded-lg border border-slate-200/80">
                    {product.description}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Accepted Catalog Attributes Panel */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Accepted Catalog Attributes</span>
              </h3>
              <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                {acceptedAttributes.length} Specs Verified
              </span>
            </div>

            {acceptedAttributes.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400">
                No human-accepted AI attributes for this product yet.
                <div className="mt-1">
                  <Link
                    to={`/ops/hitl/${product.id}`}
                    className="text-indigo-600 hover:underline font-medium"
                  >
                    Open in HITL Review &rarr;
                  </Link>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {acceptedAttributes.map(([key, attr]) => (
                  <div
                    key={key}
                    className="flex items-start justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-xs"
                  >
                    <div>
                      <span className="font-semibold text-slate-800 capitalize">
                        {key.replace(/_/g, ' ')}
                      </span>
                      <div className="text-[11px] text-slate-600 mt-0.5">
                        {typeof attr.value === 'object'
                          ? JSON.stringify(attr.value)
                          : String(attr.value)}
                      </div>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-emerald-100/80 text-emerald-800 rounded">
                      Accepted Spec
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Grounded Product Assistant + Product Comparison (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Grounded Product Assistant Card (Q104) */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">Grounded Product Assistant</h3>
              </div>
              <span className="text-[10px] font-medium bg-indigo-50 text-indigo-700 px-2.5 py-0.5 rounded-full border border-indigo-200">
                Grounded in Accepted Data
              </span>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed">
              Ask technical or ergonomic questions. Claims are verified against accepted catalog
              attributes with factual citation guarantees.
            </p>

            {/* Suggested Question Chips */}
            <div className="space-y-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Suggested Inquiries:
              </span>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setRagQuery(q);
                      handleAskRAG(q);
                    }}
                    className="text-left text-xs bg-slate-50 hover:bg-slate-100 text-slate-700 px-2.5 py-1 rounded-md border border-slate-200 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Input Form */}
            <form onSubmit={handleRAGSubmit} className="flex gap-2 pt-2">
              <input
                type="text"
                value={ragQuery}
                onChange={(e) => setRagQuery(e.target.value)}
                placeholder="Ask a technical or compatibility question about this product..."
                className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 focus:outline-hidden focus:bg-white focus:border-indigo-500"
              />
              <button
                type="submit"
                disabled={ragLoading || !ragQuery.trim()}
                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center space-x-1.5 disabled:opacity-60"
              >
                {ragLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                <span>Inquire</span>
              </button>
            </form>

            {ragError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs">
                {ragError}
              </div>
            )}

            {/* RAG Answer Display */}
            {ragResponse && (
              <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3 text-xs animate-in fade-in">
                <div className="flex items-center justify-between border-b border-slate-200/80 pb-2">
                  <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Answer Grounded in Accepted Specs</span>
                  </span>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                      ragResponse.grounding_passed
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {ragResponse.grounding_passed ? 'Citation Verified' : 'Standard Response'}
                  </span>
                </div>

                <div className="text-slate-700 leading-relaxed font-normal whitespace-pre-line">
                  {ragResponse.answer}
                </div>

                {/* Structured Claims & Evidence */}
                {ragResponse.claims && ragResponse.claims.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-slate-200/80">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Structured Claims &amp; Evidence
                    </div>
                    <div className="space-y-1.5">
                      {ragResponse.claims.map((claim, idx) => (
                        <div
                          key={idx}
                          className="bg-white p-2.5 rounded-lg border border-slate-200/80 flex items-start justify-between gap-3"
                        >
                          <div className="space-y-0.5">
                            <div className="font-medium text-slate-900 text-[11px]">
                              &bull; Claim: {claim.claim}
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono">
                              Attribute: {claim.attribute} | Value: {String(claim.value)}
                            </div>
                          </div>
                          {claim.citation && (
                            <span className="shrink-0 text-[10px] text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 font-medium">
                              {claim.citation.explanation || 'Verified Citation'}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Compare with Similar Products Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Compare with Similar Products
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Side-by-side comparison powered by hybrid recommendation signals.
                </p>
              </div>
              <span className="text-[11px] font-mono text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                {recommendations.length + 1} Products
              </span>
            </div>

            {recommendations.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400">
                No similar recommendations available yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-slate-700">
                      <th className="p-2.5 font-semibold">Metric / Feature</th>
                      <th className="p-2.5 font-semibold bg-indigo-50/50 text-indigo-950">
                        {product.title} (This item)
                      </th>
                      {recommendations.map((rec) => (
                        <th key={rec.product.id} className="p-2.5 font-semibold">
                          <Link
                            to={`/storefront/products/${rec.product.id}`}
                            onClick={() => sessionStorage.setItem('last_viewed_product_id', String(rec.product.id))}
                            className="hover:text-indigo-600 transition-colors"
                          >
                            {rec.product.title}
                          </Link>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-600">
                    <tr>
                      <td className="p-2.5 font-medium text-slate-900">Price</td>
                      <td className="p-2.5 font-mono font-bold text-indigo-900 bg-indigo-50/20">
                        {formatINR(product.price)}
                      </td>
                      {recommendations.map((rec) => (
                        <td key={rec.product.id} className="p-2.5 font-mono">
                          {formatINR(rec.product.price)}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-2.5 font-medium text-slate-900">Brand</td>
                      <td className="p-2.5 bg-indigo-50/20 font-medium">
                        {product.brand || '—'}
                      </td>
                      {recommendations.map((rec) => (
                        <td key={rec.product.id}>{rec.product.brand || '—'}</td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-2.5 font-medium text-slate-900">Availability</td>
                      <td className="p-2.5 bg-indigo-50/20 text-emerald-700 font-semibold">
                        {product.status}
                      </td>
                      {recommendations.map((rec) => (
                        <td
                          key={rec.product.id}
                          className={
                            rec.product.status === 'ACTIVE'
                              ? 'text-emerald-700 font-semibold'
                              : 'text-slate-500'
                          }
                        >
                          {rec.product.status}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-2.5 font-medium text-slate-900">Match Affinity</td>
                      <td className="p-2.5 bg-indigo-50/20 font-bold text-indigo-700">1.00</td>
                      {recommendations.map((rec) => (
                        <td key={rec.product.id} className="font-mono text-indigo-600 font-semibold">
                          {rec.score.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-2.5 font-medium text-slate-900">Recommendation Reasons</td>
                      <td className="p-2.5 bg-indigo-50/20 text-[11px] text-slate-400">
                        Source Anchor Product
                      </td>
                      {recommendations.map((rec) => (
                        <td key={rec.product.id} className="text-[11px] text-slate-500">
                          {rec.match_reasons?.join('; ') || 'Hybrid similarity'}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
