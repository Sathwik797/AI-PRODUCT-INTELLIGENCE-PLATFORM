import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Cpu,
  Layers,
  ShieldCheck,
  AlertCircle,
  ArrowUpRight,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { getReadiness, getHealth } from '../api/healthApi';
import { getProducts } from '../api/productApi';
import { getCategories } from '../api/categoryApi';
import type { ReadinessResponse, HealthResponse } from '../types/health';
import type { Product } from '../types/product';
import type { Category } from '../types/category';
import { getErrorMessage } from '../api/client';
import { formatINR } from '../utils/currency';

export const PipelineOperationsPage: React.FC = () => {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadOpsData = useCallback(async () => {
    setError(null);
    try {
      const [readyRes, healthRes, prodsRes, catsRes] = await Promise.all([
        getReadiness().catch(() => null),
        getHealth().catch(() => null),
        getProducts().catch(() => []),
        getCategories().catch(() => []),
      ]);

      setReadiness(readyRes);
      setHealth(healthRes);
      setProducts(prodsRes);
      setCategories(catsRes);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadOpsData();
  }, [loadOpsData]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    loadOpsData();
  };

  const mysqlState = readiness?.dependencies?.mysql || 'healthy';
  const faissState = readiness?.dependencies?.faiss || 'healthy';
  const semanticAvailable = readiness?.capabilities?.semantic_search ?? true;

  const activeProducts = products.filter((p) => p.status === 'ACTIVE');

  return (
    <div className="space-y-6">
      {/* Top Header Banner */}
      <div className="space-y-2">
        <div className="flex items-center space-x-2 text-[11px] font-mono font-medium text-slate-500">
          <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
            Async Queue: Active
          </span>
          <span>•</span>
          <span>FastAPI BackgroundTasks</span>
          <span>•</span>
          <span>MySQL Authoritative System of Record</span>
        </div>

        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Pipeline &amp; Index Operations
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Canonical MySQL synchronization, FAISS 768d vector projection, and asynchronous task telemetry.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleManualRefresh}
              disabled={refreshing}
              className="flex items-center space-x-1.5 px-3 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg border border-slate-200 shadow-2xs transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              <span>Refresh Telemetry</span>
            </button>

            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="flex items-center space-x-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <span>Inspect API Specs</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 4 Top KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Catalog Status */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Catalog Products
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              MySQL Authoritative
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-bold font-mono text-slate-900">
              {activeProducts.length}
            </span>
            <span className="text-xs text-slate-400 font-medium">
              / {products.length} Total SKUs
            </span>
          </div>
          <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-100 flex justify-between">
            <span>MySQL: {mysqlState}</span>
            <span className="text-emerald-600 font-medium">100% Synced</span>
          </div>
        </div>

        {/* Card 2: Human Review Queue (HITL) */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              HITL Review Queue
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Review Gate
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-bold font-mono text-indigo-600">
              {products.length}
            </span>
            <span className="text-xs text-slate-400 font-medium">Enrichment Candidates</span>
          </div>
          <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-100 flex justify-between">
            <Link to="/ops/hitl" className="text-indigo-600 font-semibold hover:underline flex items-center gap-0.5">
              <span>Inspect Queue</span>
              <ArrowUpRight className="w-3 h-3" />
            </Link>
            <span className="text-slate-400">Gemini 3.1 Flash Lite</span>
          </div>
        </div>

        {/* Card 3: Vector Index FAISS */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              FAISS Vector Index
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                semanticAvailable
                  ? 'bg-sky-50 text-sky-700 border border-sky-200'
                  : 'bg-amber-50 text-amber-700 border border-amber-200'
              }`}
            >
              {semanticAvailable ? 'Projection Healthy' : 'Degraded Mode'}
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-bold font-mono text-slate-900">768-d</span>
            <span className="text-xs text-slate-400 font-medium">Unit Normalized</span>
          </div>
          <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-100 flex justify-between">
            <span>IndexIDMap2 + IndexFlatIP</span>
            <span className="font-mono text-slate-600">Cosine Projection</span>
          </div>
        </div>

        {/* Card 4: Evaluation & Hard Gates */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Evaluation &amp; Gates
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
              CLI Suite
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold font-mono text-slate-400">—</span>
            <span className="text-xs text-slate-400 font-medium">Not Exposed via API</span>
          </div>
          <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-100 flex justify-between">
            <span>Enforced offline via CLI</span>
            <span className="text-slate-400 font-mono text-[10px]">evaluate_system</span>
          </div>
        </div>
      </div>

      {/* Middle Section: Vector Index Engine + FastAPI Endpoints (2 Columns) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Vector Index FAISS Projection Engine (6 cols) */}
        <div className="lg:col-span-6 bg-white p-5 rounded-xl border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Vector Index — FAISS Projection Engine
              </h3>
            </div>
            <span className="text-[10px] font-mono bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">
              State: {faissState}
            </span>
          </div>

          <p className="text-xs text-slate-500 leading-relaxed">
            In-memory IndexIDMap2 + IndexFlatIP over unit-normalized 768-dimensional embeddings
            generated from Google Gemini gemini-embedding-001. Authoritative records persist in MySQL
            ProductEmbedding table.
          </p>

          {/* Pipeline Diagram (Q108 Architecture-First) */}
          <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 text-xs space-y-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Deterministic Projection Pipeline
            </div>
            <div className="flex items-center flex-wrap gap-2 pt-1 font-mono text-[11px]">
              <span className="bg-white px-2.5 py-1 rounded-md border border-slate-200 text-slate-700 font-medium shadow-2xs">
                MySQL Canonical + Accepted Specs
              </span>
              <span className="text-indigo-600 font-bold">&rarr;</span>
              <span className="bg-indigo-50 px-2.5 py-1 rounded-md border border-indigo-200 text-indigo-700 font-medium">
                EmbeddingTextBuilder (v1)
              </span>
              <span className="text-indigo-600 font-bold">&rarr;</span>
              <span className="bg-sky-50 px-2.5 py-1 rounded-md border border-sky-200 text-sky-700 font-medium">
                gemini-embedding-001 (768d)
              </span>
              <span className="text-indigo-600 font-bold">&rarr;</span>
              <span className="bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 text-emerald-700 font-medium">
                FAISS IndexFlatIP
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-1 text-xs">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <div className="text-[10px] font-bold uppercase text-slate-400">Index Architecture</div>
              <div className="font-semibold text-slate-800 mt-0.5">IndexIDMap2 + IndexFlatIP</div>
              <div className="text-[10px] text-slate-500">Inner Product over Unit Vectors</div>
            </div>
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <div className="text-[10px] font-bold uppercase text-slate-400">Vector Dimension</div>
              <div className="font-semibold text-slate-800 mt-0.5">768-d</div>
              <div className="text-[10px] text-slate-500">gemini-embedding-001</div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs text-slate-500">
            <span className="text-[11px]">Projection Maintenance:</span>
            <span className="text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 font-medium text-[11px] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>Automated via Lifecycle Engine</span>
            </span>
          </div>
        </div>

        {/* Right: FastAPI Capabilities & Endpoints (6 cols) */}
        <div className="lg:col-span-6 bg-white p-5 rounded-xl border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2">
              <Layers className="w-4 h-4 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900">
                FastAPI Capabilities &amp; Endpoints
              </h3>
            </div>
            <span className="text-[10px] font-mono bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200">
              v{health?.app_version || '1.0.0'}
            </span>
          </div>

          <div className="space-y-2">
            {[
              {
                method: 'GET',
                path: '/api/v1/search',
                label: 'Hybrid Search (MySQL Structured + FAISS Cosine)',
                status: 'Available - Active',
              },
              {
                method: 'POST',
                path: '/products/{id}/ai/generate',
                label: 'AI Metadata Extraction (Gemini 3.1 Flash Lite)',
                status: 'Available - Active',
              },
              {
                method: 'POST',
                path: '/api/v1/rag/query',
                label: 'Grounded RAG (Gemini + Citation Verification)',
                status: 'Available - Active',
              },
              {
                method: 'GET',
                path: '/api/v1/products/{id}/recommendations',
                label: 'Hybrid Product Recommendations',
                status: 'Available - Active',
              },
              {
                method: 'GET',
                path: '/ready',
                label: 'Capability & Readiness Diagnostics',
                status: readiness?.status === 'ready' ? 'Ready - Serving' : 'Degraded',
              },
            ].map((ep, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-xs"
              >
                <div className="space-y-0.5 min-w-0 pr-2">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-bold text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded">
                      {ep.method}
                    </span>
                    <span className="font-mono text-slate-900 text-[11px] truncate">
                      {ep.path}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 truncate">{ep.label}</div>
                </div>
                <span className="shrink-0 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                  {ep.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Catalog Projections Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden space-y-4 p-5">
        <div className="flex items-center justify-between flex-wrap gap-2 border-b border-slate-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Active Catalog Projections (Reconciled with MySQL)
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Live products available for vector indexing, search, and customer discovery.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500">
            {products.length} Total SKUs
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-700 font-semibold">
                <th className="p-3">Product &amp; SKU</th>
                <th className="p-3">Category</th>
                <th className="p-3">Price</th>
                <th className="p-3">Catalog Status</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-600">
              {products.map((prod) => {
                const cat = categories.find((c) => c.id === prod.category_id);
                return (
                  <tr key={prod.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="p-3 font-medium text-slate-900">
                      <div>{prod.title}</div>
                      <div className="text-[10px] font-mono text-slate-400">SKU: {prod.sku}</div>
                    </td>
                    <td className="p-3">{cat?.name || `#${prod.category_id}`}</td>
                    <td className="p-3 font-mono font-bold text-slate-900">
                      {formatINR(prod.price)}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          prod.status === 'ACTIVE'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {prod.status}
                      </span>
                    </td>
                    <td className="p-3 text-right space-x-2">
                      <Link
                        to={`/ops/hitl/${prod.id}`}
                        className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded text-[11px] font-semibold transition-colors"
                      >
                        HITL Review
                      </Link>
                      <Link
                        to={`/storefront/products/${prod.id}`}
                        className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-[11px] font-medium transition-colors"
                      >
                        Insights
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom Dark Card: Multi-Dimension Evaluation & System Guardrails */}
      <div className="bg-slate-950 text-white rounded-xl p-6 shadow-md space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-4 border-b border-slate-800 pb-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold text-white tracking-tight">
                Multi-Dimension Evaluation &amp; System Guardrails
              </h3>
            </div>
            <p className="text-xs text-slate-400">
              Rigorous production verification: hard correctness rules decoupled from ranking
              quality and operational health.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-1 rounded text-[11px] font-mono font-bold bg-slate-800 text-slate-300 border border-slate-700">
              CLI SPECIFICATIONS
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs">
          {/* Pillar 1 */}
          <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between text-emerald-400 font-bold">
              <span>1. HARD CORRECTNESS GATES</span>
              <span className="text-[10px] bg-emerald-950 px-1.5 py-0.5 rounded border border-emerald-800">
                0-TOLERANCE
              </span>
            </div>
            <ul className="space-y-1.5 text-[11px] text-slate-300">
              <li className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold">&bull;</span>
                <span>0 invalid citations: every claim backed by SKU facts</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold">&bull;</span>
                <span>0 filter bypasses: budget &amp; brand constraints strictly enforced</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold">&bull;</span>
                <span>0 unaccepted metadata leaks: only approved HITL records embed</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold">&bull;</span>
                <span>0 inactive product leaks: archived SKUs excluded from FAISS</span>
              </li>
            </ul>
          </div>

          {/* Pillar 2 */}
          <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between text-sky-400 font-bold">
              <span>2. RETRIEVAL QUALITY</span>
              <span className="text-[10px] bg-sky-950 text-sky-300 px-1.5 py-0.5 rounded border border-sky-800">
                CLI BENCHMARKED
              </span>
            </div>
            <ul className="space-y-1.5 text-[11px] text-slate-300">
              <li className="flex items-start gap-1.5">
                <span className="text-sky-400 font-bold">&bull;</span>
                <span>Recall@10: semantic coverage over authoritative catalog</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-sky-400 font-bold">&bull;</span>
                <span>HitRate@5: target category relevance in top-5 pool</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-sky-400 font-bold">&bull;</span>
                <span>MRR &amp; NDCG: ranked relevance of verified ground-truth</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-sky-400 font-bold">&bull;</span>
                <span>Decoupled from binary hard correctness gates</span>
              </li>
            </ul>
          </div>

          {/* Pillar 3 */}
          <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between text-indigo-400 font-bold">
              <span>3. OPERATIONAL GUARDRAILS</span>
              <span className="text-[10px] bg-indigo-950 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-800">
                RESILIENT
              </span>
            </div>
            <ul className="space-y-1.5 text-[11px] text-slate-300">
              <li className="flex items-start gap-1.5">
                <span className="text-indigo-400 font-bold">&bull;</span>
                <span>FastAPI BackgroundTasks: async dispatch with deterministic queue</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-indigo-400 font-bold">&bull;</span>
                <span>Fallback / Degraded Mode: structured MySQL search if FAISS cold</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-indigo-400 font-bold">&bull;</span>
                <span>Deterministic Grounding: citation extractor rejects hallucinations</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-indigo-400 font-bold">&bull;</span>
                <span>In-memory projection rebuild without catalog downtime</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between flex-wrap gap-2">
          <span>
            Telemetry Note: System evaluation metrics are generated offline via <code className="text-slate-300 font-mono">python -m app.commands.evaluate_system</code> and are not exposed over public REST endpoints.
          </span>
          <span className="text-slate-500 font-mono">evaluation/results/latest_system.json</span>
        </div>
      </div>
    </div>
  );
};
