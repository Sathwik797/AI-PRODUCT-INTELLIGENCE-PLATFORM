import { apiClient } from './client';
import type { ProductImage, ImageDisplayOrderUpdate } from '../types/image';

export function normalizeImageUrl(imageUrl: string | null | undefined): string {
  if (!imageUrl) return '';
  const normalized = imageUrl.replace(/\\/g, '/');
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
}

export async function getProductImages(productId: number): Promise<ProductImage[]> {
  const response = await apiClient.get<ProductImage[]>(`/products/${productId}/images`);
  return response.data;
}

export async function uploadProductImage(productId: number, file: File): Promise<ProductImage> {
  const formData = new FormData();
  formData.append('file', file);

  // Note: Do not manually set Content-Type header so browser sets multipart boundary automatically
  const response = await apiClient.post<ProductImage>(`/products/${productId}/images`, formData, {
    headers: {
      'Content-Type': undefined,
    },
  });
  return response.data;
}

export async function deleteProductImage(imageId: number): Promise<void> {
  await apiClient.delete(`/images/${imageId}`);
}

export async function updateImageDisplayOrder(
  imageId: number,
  displayOrder: number
): Promise<ProductImage> {
  const payload: ImageDisplayOrderUpdate = { display_order: displayOrder };
  const response = await apiClient.patch<ProductImage>(`/images/${imageId}/display-order`, payload);
  return response.data;
}
