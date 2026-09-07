import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Package, FolderTree, PlusCircle, ExternalLink, Sparkles } from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();

  const navLinks = [
    { to: '/products', label: 'Products', icon: Package },
    { to: '/products/new', label: 'New Product', icon: PlusCircle },
    { to: '/categories', label: 'Categories', icon: FolderTree },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      {/* Top Navigation */}
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-8">
              <Link to="/products" className="flex items-center space-x-2.5 text-slate-900 font-semibold text-lg">
                <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs">
                  <Sparkles className="w-4 h-4" />
                </div>
                <span>AI Product Intelligence</span>
                <span className="text-xs font-mono font-normal bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200">
                  Dev Workbench
                </span>
              </Link>

              <nav className="hidden md:flex items-center space-x-1">
                {navLinks.map((link) => {
                  const Icon = link.icon;
                  const isActive =
                    link.to === '/products'
                      ? location.pathname === '/' || location.pathname === '/products'
                      : location.pathname === link.to;

                  return (
                    <Link
                      key={link.to}
                      to={link.to}
                      className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        isActive
                          ? 'bg-slate-100 text-indigo-600 font-semibold'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span>{link.label}</span>
                    </Link>
                  );
                })}
              </nav>
            </div>

            <div className="flex items-center space-x-4">
              <a
                href="http://127.0.0.1:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="flex items-center space-x-1 text-xs text-slate-500 hover:text-indigo-600 transition-colors"
                title="Open FastAPI Swagger Documentation"
              >
                <span>FastAPI Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
};
