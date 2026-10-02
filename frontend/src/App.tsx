import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { StorefrontSearchPage } from './pages/StorefrontSearchPage';
import { ProductInsightsPage } from './pages/ProductInsightsPage';
import { PipelineOperationsPage } from './pages/PipelineOperationsPage';
import { HITLVerificationPage } from './pages/HITLVerificationPage';
import { ProductsPage } from './pages/ProductsPage';
import { ProductCreatePage } from './pages/ProductCreatePage';
import { CategoriesPage } from './pages/CategoriesPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          {/* Canonical Storefront Routes (Screens 2 & 3) */}
          <Route path="/storefront/search" element={<StorefrontSearchPage />} />
          <Route path="/storefront/products/:id" element={<ProductInsightsPage />} />

          {/* Canonical AI Studio / Operations Routes (Screens 1 & 4) */}
          <Route path="/ops/pipeline" element={<PipelineOperationsPage />} />
          <Route path="/ops/hitl" element={<HITLVerificationPage />} />
          <Route path="/ops/hitl/:id" element={<HITLVerificationPage />} />

          {/* Existing Preserved Management Routes */}
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/products/new" element={<ProductCreatePage />} />
          <Route path="/products/:id" element={<ProductInsightsPage />} />
          <Route path="/categories" element={<CategoriesPage />} />

          {/* Convenience & Redirect Routes */}
          <Route path="/ops" element={<Navigate to="/ops/pipeline" replace />} />
          <Route path="/search" element={<Navigate to="/storefront/search" replace />} />
          <Route path="/storefront" element={<Navigate to="/storefront/search" replace />} />
          <Route path="/storefront/products" element={<Navigate to="/storefront/search" replace />} />
          <Route path="/" element={<Navigate to="/storefront/search" replace />} />
          <Route path="*" element={<Navigate to="/storefront/search" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
};

export default App;
