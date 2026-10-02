import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Database,
  ShieldCheck,
  Package,
  Activity,
  Sparkles,
} from 'lucide-react';
import { getReadiness } from '../api/healthApi';
import type { ReadinessResponse } from '../types/health';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  const isOpsMode = location.pathname.startsWith('/ops');

  // Header scroll hide/show behavior (Section 3)
  const [isHeaderVisible, setIsHeaderVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY <= 15) {
        setIsHeaderVisible(true);
      } else if (currentScrollY > lastScrollY && currentScrollY > 60) {
        // Scrolling downward
        setIsHeaderVisible(false);
      } else if (currentScrollY < lastScrollY) {
        // Scrolling upward
        setIsHeaderVisible(true);
      }
      setLastScrollY(currentScrollY);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [lastScrollY]);

  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      try {
        const res = await getReadiness();
        if (isMounted) setReadiness(res);
      } catch (e) {
        if (isMounted) {
          setReadiness({
            status: 'not_ready',
            dependencies: { mysql: 'unhealthy', faiss: 'degraded' },
            capabilities: { structured_search: false, semantic_search: false },
          });
        }
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const mysqlHealthy = readiness?.dependencies?.mysql === 'healthy';
  const faissHealthy = readiness?.dependencies?.faiss === 'healthy';

  return (
    <div className="min-h-screen bg-white text-slate-800 font-sans flex flex-col">
      {/* Top Persistent Header - Hides on downward scroll, reappears on upward scroll */}
      <header
        className={`sticky top-0 z-40 bg-white border-b border-slate-100 shadow-2xs transition-transform duration-300 ${
          isHeaderVisible ? 'translate-y-0' : '-translate-y-full'
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14 sm:h-16">
            {/* Left: Brand + Subtitle */}
            <div className="flex items-center">
              <Link
                to={isOpsMode ? '/ops/pipeline' : '/storefront/search'}
                className="flex items-center space-x-2.5 group"
              >
                <div className="leading-tight">
                  <div className="text-lg font-black tracking-tight text-slate-900 flex items-center gap-1">
                    <span>Product<span className="text-blue-600">IQ</span></span>
                    <Sparkles className="w-4 h-4 text-blue-500 fill-blue-500 ml-0.5" />
                  </div>
                  <div className="text-[11px] text-slate-400 font-medium">
                    Smarter Shopping. Real Answers.
                  </div>
                </div>
              </Link>
            </div>

            {/* Center: Primary Mode Switcher Toggle */}
            <div className="flex items-center bg-slate-100 p-1 rounded-full border border-slate-200/80 shadow-2xs">
              <button
                type="button"
                onClick={() => navigate('/storefront/search')}
                className={`flex items-center space-x-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                  !isOpsMode
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span>Storefront Discovery</span>
              </button>

              <button
                type="button"
                onClick={() => navigate('/ops/pipeline')}
                className={`flex items-center space-x-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                  isOpsMode
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span>AI Studio / Operations</span>
              </button>
            </div>

            {/* Right: User Profile (No Catalog Live badge on Storefront) */}
            <div className="flex items-center space-x-3">
              {isOpsMode && (
                <div className="hidden md:flex items-center space-x-2">
                  <div
                    className={`flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                      mysqlHealthy
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-rose-50 text-rose-700 border-rose-200'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        mysqlHealthy ? 'bg-emerald-500' : 'bg-rose-500'
                      }`}
                    />
                    <span>MySQL: {mysqlHealthy ? 'Connected' : 'Disconnected'}</span>
                  </div>

                  <div
                    className={`flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                      faissHealthy
                        ? 'bg-sky-50 text-sky-700 border-sky-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        faissHealthy ? 'bg-sky-500' : 'bg-amber-500'
                      }`}
                    />
                    <span>FAISS: {faissHealthy ? '768d' : 'Cold'}</span>
                  </div>
                </div>
              )}

              {/* User Avatar */}
              <div className="flex items-center space-x-1 pl-1 cursor-pointer">
                <div className="w-8 h-8 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shadow-xs">
                  U
                </div>
                <span className="text-slate-400 text-xs">▾</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className={isOpsMode ? "flex-1 flex max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6" : "flex-1 w-full flex flex-col"}>
        {/* Left Sidebar for Ops Mode */}
        {isOpsMode && (
          <aside className="w-56 shrink-0 pr-6 space-y-6">
            <div>
              <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                Intelligence Operations
              </div>
              <nav className="space-y-1">
                <Link
                  to="/ops/pipeline"
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    location.pathname === '/ops/pipeline' || location.pathname === '/ops'
                      ? 'bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Activity className="w-4 h-4" />
                  <span>Pipeline & Ingestion</span>
                </Link>

                <Link
                  to="/ops/hitl"
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    location.pathname.startsWith('/ops/hitl')
                      ? 'bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>HITL Verification</span>
                </Link>

                <Link
                  to="/products"
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    location.pathname === '/products'
                      ? 'bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Package className="w-4 h-4" />
                  <span>Catalog Index</span>
                </Link>

                <Link
                  to="/categories"
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    location.pathname === '/categories'
                      ? 'bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Database className="w-4 h-4" />
                  <span>Categories Manager</span>
                </Link>
              </nav>
            </div>

            {/* Background Queue Telemetry Card */}
            <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs space-y-2 text-xs">
              <div className="flex items-center justify-between text-slate-500 font-medium">
                <span>Background Queue</span>
                <span className="text-emerald-600 font-semibold">Active</span>
              </div>
              <div className="text-[11px] text-slate-600">
                Tasks dispatched via FastAPI BackgroundTasks worker.
              </div>
              <div className="text-[10px] font-mono text-slate-400 pt-1 border-t border-slate-100">
                Broker: In-Process (Zero Celery/Kafka)
              </div>
            </div>
          </aside>
        )}

        {/* Content Area */}
        <main className="flex-1 min-w-0">{children}</main>
      </div>

      {/* Global Footer */}
      <footer className="border-t border-slate-100 bg-white py-5 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between text-xs text-slate-400">
          <div>
            &copy; 2026 ProductIQ &bull; Smarter Shopping. Real Answers.
          </div>
          <div className="text-slate-400 text-[11px]">
            AI Product Intelligence Platform
          </div>
        </div>
      </footer>
    </div>
  );
};
