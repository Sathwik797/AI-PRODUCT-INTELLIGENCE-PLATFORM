import React, { useState } from 'react';
import { Upload, Trash2, ArrowUp, ArrowDown, Image as ImageIcon, Loader2, AlertCircle } from 'lucide-react';
import type { ProductImage } from '../types/image';
import { uploadProductImage, deleteProductImage, updateImageDisplayOrder, normalizeImageUrl } from '../api/imageApi';
import { getErrorMessage } from '../api/client';

interface ImageGalleryProps {
  productId: number;
  images: ProductImage[];
  onImagesUpdated: () => void;
}

export const ImageGallery: React.FC<ImageGalleryProps> = ({
  productId,
  images,
  onImagesUpdated,
}) => {
  const [uploading, setUploading] = useState<boolean>(false);
  const [actionInProgress, setActionInProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Basic UX size check (backend max is 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setError('File size exceeds 5 MB limit.');
      return;
    }

    setError(null);
    setUploading(true);

    try {
      await uploadProductImage(productId, file);
      onImagesUpdated();
      e.target.value = '';
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (imageId: number) => {
    if (!window.confirm('Delete this image?')) return;
    setActionInProgress(imageId);
    setError(null);
    try {
      await deleteProductImage(imageId);
      onImagesUpdated();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionInProgress(null);
    }
  };

  const handleReorder = async (image: ProductImage, newOrder: number) => {
    if (newOrder < 1) return;
    setActionInProgress(image.id);
    setError(null);
    try {
      await updateImageDisplayOrder(image.id, newOrder);
      onImagesUpdated();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionInProgress(null);
    }
  };

  // Sort images by display order ascending
  const sortedImages = [...images].sort((a, b) => a.display_order - b.display_order);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-900 flex items-center space-x-2">
          <ImageIcon className="w-5 h-5 text-indigo-600" />
          <span>Product Images ({images.length})</span>
        </h3>
        <span className="text-xs text-slate-500">Max 5MB • JPG, PNG, WEBP, AVIF</span>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-md flex items-start space-x-2 text-rose-700 text-sm">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Upload Drop Area */}
      <div className="border-2 border-dashed border-slate-300 rounded-lg p-4 bg-slate-50 hover:bg-slate-100/60 transition-colors text-center">
        <label className="cursor-pointer block">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/avif"
            onChange={handleFileChange}
            disabled={uploading}
            className="hidden"
          />
          <div className="flex flex-col items-center justify-center space-y-1.5">
            {uploading ? (
              <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
            ) : (
              <Upload className="w-6 h-6 text-slate-400" />
            )}
            <span className="text-sm font-medium text-slate-700">
              {uploading ? 'Uploading image...' : 'Click or drop to upload image'}
            </span>
            <span className="text-xs text-slate-400">All images are analyzed together by Gemini AI</span>
          </div>
        </label>
      </div>

      {/* Image Thumbnails Grid */}
      {sortedImages.length === 0 ? (
        <div className="py-8 text-center border border-dashed border-slate-200 rounded-md bg-white">
          <p className="text-sm text-slate-400">No images uploaded for this product yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {sortedImages.map((img, index) => {
            const isActing = actionInProgress === img.id;
            return (
              <div
                key={img.id}
                className="relative group border border-slate-200 rounded-lg overflow-hidden bg-white shadow-2xs flex flex-col"
              >
                <div className="aspect-square bg-slate-100 relative overflow-hidden flex items-center justify-center">
                  <img
                    src={normalizeImageUrl(img.image_url)}
                    alt={img.filename}
                    className="w-full h-full object-cover"
                    loading="lazy"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" fill="%23ccc"><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle">Missing</text></svg>';
                    }}
                  />
                  <div className="absolute top-2 left-2 bg-slate-900/70 text-white text-[10px] px-1.5 py-0.5 rounded font-mono">
                    #{img.display_order}
                  </div>
                  <div className="absolute top-2 right-2 bg-slate-900/70 text-white text-[10px] px-1.5 py-0.5 rounded font-mono">
                    ID: {img.id}
                  </div>
                </div>

                <div className="p-2 bg-white flex items-center justify-between text-xs text-slate-600 border-t border-slate-100">
                  <span className="truncate max-w-[90px] font-mono text-[11px]" title={img.filename}>
                    {img.filename}
                  </span>

                  <div className="flex items-center space-x-1">
                    <button
                      type="button"
                      title="Move up"
                      disabled={isActing || index === 0}
                      onClick={() => handleReorder(img, img.display_order - 1)}
                      className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30 rounded hover:bg-slate-100"
                    >
                      <ArrowUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      title="Move down"
                      disabled={isActing || index === sortedImages.length - 1}
                      onClick={() => handleReorder(img, img.display_order + 1)}
                      className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30 rounded hover:bg-slate-100"
                    >
                      <ArrowDown className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      title="Delete image"
                      disabled={isActing}
                      onClick={() => handleDelete(img.id)}
                      className="p-1 text-rose-500 hover:text-rose-700 hover:bg-rose-50 rounded"
                    >
                      {isActing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
