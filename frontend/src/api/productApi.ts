import { apiClient } from './client';
import type { Product, ProductCreate, ProductUpdate } from '../types/product';

export async function getProducts(): Promise<Product[]> {
  const response = await apiClient.get<Product[]>('/products');
  return response.data;
}

export async function getProduct(id: number): Promise<Product> {
  const response = await apiClient.get<Product>(`/products/${id}`);
  return response.data;
}

export async function createProduct(data: ProductCreate): Promise<Product> {
  const response = await apiClient.post<Product>('/products', data);
  return response.data;
}

export async function updateProduct(id: number, data: ProductUpdate): Promise<Product> {
  const response = await apiClient.put<Product>(`/products/${id}`, data);
  return response.data;
}

export async function deleteProduct(id: number): Promise<void> {
  await apiClient.delete(`/products/${id}`);
}

export async function getProductsByCategory(categoryId: number): Promise<Product[]> {
  const response = await apiClient.get<Product[]>(`/products/category/${categoryId}`);
  return response.data;
}

export async function searchProducts(keyword: string): Promise<Product[]> {
  const response = await apiClient.get<Product[]>(`/products/search/${encodeURIComponent(keyword)}`);
  return response.data;
}
