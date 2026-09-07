import React, { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Edit2,
  X,
  Package,
  Loader2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import type { Product, ProductUpdate } from '../types/product';
import type { ProductImage } from '../types/image';
import { getProduct, updateProduct } from '../api/productApi';
import { getProductImages } from '../api/imageApi';
import { getErrorMessage } from '../api/client';
import { CategorySelector } from '../components/CategorySelector';
import { ImageGallery } from '../components/ImageGallery';
import { AIStudio } from '../components/AIStudio';

export const ProductDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);

  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit Mode state
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editFormData, setEditFormData] = useState<ProductUpdate>({});
  const [saving, setSaving] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!productId || isNaN(productId)) {
      setError('Invalid product ID');
      setLoading(false);
      return;
    }

    try {
      const [prodData, imgsData] = await Promise.all([
        getProduct(productId),
        getProductImages(productId),
      ]);
      setProduct(prodData);
      setImages(imgsData);
      setEditFormData({
        title: prodData.title,
        sku: prodData.sku,
        price: prodData.price,
        category_id: prodData.category_id,
        description: prodData.description || '',
        brand: prodData.brand || '',
        status: prodData.status,
      });
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setEditError(null);

    try {
      const updated = await updateProduct(productId, {
        ...editFormData,
        price: editFormData.price !== undefined ? Number(editFormData.price) : undefined,
      });
      setProduct(updated);
      setIsEditing(false);
      // Reload to ensure all backend hooks and synced AI acceptance states are reflected
      loadData();
    } catch (err: unknown) {
      setEditError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-2" />
        <p className="text-sm text-slate-500">Loading product workbench #{productId}...</p>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="max-w-2xl mx-auto py-12 space-y-4 text-center">
        <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
        <h2 className="text-lg font-bold text-slate-900">Failed to Load Product</h2>
        <p className="text-sm text-slate-600">{error || 'Product not found'}</p>
        <Link
          to="/products"
          className="inline-flex items-center space-x-1 text-sm font-semibold text-indigo-600 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Products</span>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header Breadcrumb & Actions */}
      <div className="flex items-center justify-between flex-wrap gap-4 border-b border-slate-200 pb-4">
        <div className="flex items-center space-x-3">
          <Link
            to="/products"
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            title="Back to Product List"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">{product.title}</h1>
              <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded border border-slate-200">
                #{product.id}
              </span>
            </div>
            <div className="flex items-center space-x-3 text-xs text-slate-400 mt-0.5">
              <span>SKU: <strong className="text-slate-600 font-mono">{product.sku}</strong></span>
              <span>•</span>
              <span className="flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>Updated: {new Date(product.updated_at).toLocaleString()}</span>
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsEditing(!isEditing)}
          className={`flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors shadow-2xs ${
            isEditing
              ? 'bg-slate-200 text-slate-700 border-slate-300'
              : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
          }`}
        >
          {isEditing ? <X className="w-3.5 h-3.5" /> : <Edit2 className="w-3.5 h-3.5" />}
          <span>{isEditing ? 'Cancel Editing' : 'Edit Product'}</span>
        </button>
      </div>

      {/* Main 3-Area Testing Workbench Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Product Info & Images (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Section A: Product Information */}
          <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-semibold text-slate-900 flex items-center space-x-2">
                <Package className="w-4 h-4 text-indigo-600" />
                <span>Canonical Catalog Details</span>
              </h3>
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded ${
                  product.status === 'ACTIVE'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-slate-100 text-slate-600'
                }`}
              >
                {product.status}
              </span>
            </div>

            {editError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded text-rose-700 text-xs">
                {editError}
              </div>
            )}

            {isEditing ? (
              <form onSubmit={handleEditSubmit} className="space-y-3 text-xs">
                <div>
                  <label className="block font-medium text-slate-600 mb-1">Title</label>
                  <input
                    type="text"
                    value={editFormData.title || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                    required
                    className="w-full text-xs p-2 rounded border border-slate-300"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block font-medium text-slate-600 mb-1">SKU</label>
                    <input
                      type="text"
                      value={editFormData.sku || ''}
                      onChange={(e) => setEditFormData({ ...editFormData, sku: e.target.value })}
                      required
                      className="w-full text-xs p-2 rounded border border-slate-300 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-600 mb-1">Price ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={editFormData.price || ''}
                      onChange={(e) => setEditFormData({ ...editFormData, price: parseFloat(e.target.value) || 0 })}
                      required
                      className="w-full text-xs p-2 rounded border border-slate-300 font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block font-medium text-slate-600 mb-1">Category</label>
                    <CategorySelector
                      value={editFormData.category_id || ''}
                      onChange={(catId) => setEditFormData({ ...editFormData, category_id: catId })}
                      required
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-600 mb-1">Brand</label>
                    <input
                      type="text"
                      value={editFormData.brand || ''}
                      onChange={(e) => setEditFormData({ ...editFormData, brand: e.target.value })}
                      className="w-full text-xs p-2 rounded border border-slate-300"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-600 mb-1">Description</label>
                  <textarea
                    rows={4}
                    value={editFormData.description || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                    className="w-full text-xs p-2 rounded border border-slate-300"
                  />
                </div>

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="px-3 py-1.5 rounded text-xs text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-3 py-1.5 rounded text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 shadow-2xs"
                  >
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-3 text-xs text-slate-700">
                <div>
                  <span className="text-slate-400 block mb-0.5">Title</span>
                  <span className="font-medium text-slate-900 text-sm">{product.title}</span>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                  <div>
                    <span className="text-slate-400 block mb-0.5">Price</span>
                    <span className="font-mono font-semibold text-slate-900">${product.price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Category ID</span>
                    <span className="font-mono text-slate-900">#{product.category_id}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                  <div>
                    <span className="text-slate-400 block mb-0.5">Brand</span>
                    <span className="text-slate-900">{product.brand || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">SKU</span>
                    <span className="font-mono text-slate-900">{product.sku}</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100">
                  <span className="text-slate-400 block mb-1">Description</span>
                  <p className="text-slate-600 whitespace-pre-line leading-relaxed bg-slate-50 p-2.5 rounded border border-slate-100">
                    {product.description || 'No description provided.'}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section B: Images Gallery */}
          <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-2xs">
            <ImageGallery
              productId={productId}
              images={images}
              onImagesUpdated={loadData}
            />
          </div>
        </div>

        {/* Right Column: Section C: AI Product Intelligence (7 cols) */}
        <div className="lg:col-span-7">
          <AIStudio
            productId={productId}
            onProductUpdated={loadData}
          />
        </div>
      </div>
    </div>
  );
};
