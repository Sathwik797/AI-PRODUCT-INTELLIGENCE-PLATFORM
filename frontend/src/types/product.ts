export interface Product {
  id: number;
  title: string;
  sku: string;
  price: number;
  category_id: number;
  description?: string | null;
  brand?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  title: string;
  sku: string;
  price: number;
  category_id: number;
  description?: string | null;
  brand?: string | null;
  status?: string;
}

export interface ProductUpdate {
  title?: string;
  sku?: string;
  price?: number;
  category_id?: number;
  description?: string | null;
  brand?: string | null;
  status?: string;
}
