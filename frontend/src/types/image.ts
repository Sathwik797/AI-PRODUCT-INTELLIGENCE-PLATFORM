export interface ProductImage {
  id: number;
  product_id: number;
  image_url: string;
  filename: string;
  mime_type: string;
  file_size: number;
  width: number;
  height: number;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface ImageDisplayOrderUpdate {
  display_order: number;
}
