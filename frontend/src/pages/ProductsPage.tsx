import React, { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Search, Trash2, Eye, Package, Loader2, AlertCircle } from 'lucide-react';
import type { Product } from '../types/product';
import { getProducts, searchProducts, deleteProduct } from '../api/productApi';
import { getErrorMessage } from '../api/client';

export const ProductsPage: React.FC = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [searching, setSearching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const navigate = useNavigate();

  const loadProducts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProducts();
      setProducts(data);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchKeyword.trim()) {
      loadProducts();
      return;
    }

    setSearching(true);
    setError(null);
    try {
      const results = await searchProducts(searchKeyword.trim());
      setProducts(results);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setSearching(false);
    }
  };

  const handleClearSearch = () => {
    setSearchKeyword('');
    loadProducts();
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(`Are you sure you want to delete Product #${id}? This will cascade-delete its images and AI generations.`)) {
      return;
    }

    setDeletingId(id);
    try {
      await deleteProduct(id);
      setProducts((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Product Catalog</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage canonical product records and trigger AI multimodal analysis.
          </p>
        </div>

        <Link
          to="/products/new"
          className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-md shadow-xs transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New Product</span>
        </Link>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-2xs">
        <form onSubmit={handleSearch} className="flex items-center space-x-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              placeholder="Search products by title, description, or brand..."
              className="w-full pl-9 pr-4 py-2 text-sm rounded-md border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <button
            type="submit"
            disabled={searching}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-md transition-colors disabled:opacity-50"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
          {searchKeyword && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="px-3 py-2 text-sm text-slate-500 hover:text-slate-800"
            >
              Clear
            </button>
          )}
        </form>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-md flex items-start space-x-2 text-rose-700 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Product Table */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-2xs overflow-hidden">
        {loading ? (
          <div className="py-16 text-center">
            <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-2" />
            <p className="text-sm text-slate-500">Loading catalog products...</p>
          </div>
        ) : products.length === 0 ? (
          <div className="py-16 text-center space-y-3">
            <Package className="w-12 h-12 text-slate-300 mx-auto" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-slate-700">No products found</p>
              <p className="text-xs text-slate-400">
                {searchKeyword ? 'No results matched your search term.' : 'Get started by creating your first product.'}
              </p>
            </div>
            {!searchKeyword && (
              <Link
                to="/products/new"
                className="inline-flex items-center space-x-1 text-xs text-indigo-600 font-semibold hover:underline"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Create a product</span>
              </Link>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 divide-y divide-slate-200">
              <thead className="bg-slate-50 text-xs font-semibold uppercase text-slate-500 tracking-wider">
                <tr>
                  <th className="px-6 py-3">ID</th>
                  <th className="px-6 py-3">Product Title</th>
                  <th className="px-6 py-3">SKU</th>
                  <th className="px-6 py-3">Brand</th>
                  <th className="px-6 py-3">Price</th>
                  <th className="px-6 py-3">Category</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {products.map((prod) => (
                  <tr key={prod.id} className="hover:bg-slate-50/75 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">#{prod.id}</td>
                    <td className="px-6 py-4 font-medium text-slate-900 max-w-xs truncate" title={prod.title}>
                      <button
                        onClick={() => navigate(`/products/${prod.id}`)}
                        className="hover:text-indigo-600 text-left truncate block w-full"
                      >
                        {prod.title}
                      </button>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs">{prod.sku}</td>
                    <td className="px-6 py-4 text-xs text-slate-700">{prod.brand || '—'}</td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-900">${prod.price.toFixed(2)}</td>
                    <td className="px-6 py-4">
                      <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-xs font-mono">
                        Cat #{prod.category_id}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded ${
                          prod.status === 'ACTIVE'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {prod.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => navigate(`/products/${prod.id}`)}
                        className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded transition-colors"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>View</span>
                      </button>

                      <button
                        onClick={() => handleDelete(prod.id)}
                        disabled={deletingId === prod.id}
                        className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 rounded transition-colors disabled:opacity-50"
                      >
                        {deletingId === prod.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                        <span>Delete</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
