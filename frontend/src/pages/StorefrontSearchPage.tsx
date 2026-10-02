import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Search,
  ArrowRight,
  Sparkles,
  Package,
  ChevronDown,
  X,
  Footprints,
  Laptop,
  Headphones,
  Monitor,
  Shirt,
  ShoppingBag,
  Home,
} from 'lucide-react';
import { executeHybridSearch } from '../api/searchApi';
import { getCategories } from '../api/categoryApi';
import { getProducts } from '../api/productApi';
import { getProductImages, normalizeImageUrl } from '../api/imageApi';
import type { SearchResponse } from '../types/search';
import type { Category } from '../types/category';
import type { Product } from '../types/product';
import { getErrorMessage } from '../api/client';
import { formatINR } from '../utils/currency';

interface DisplayItem {
  product: Product;
  score?: number;
  match_reasons?: string[];
}

// Canonical sequence for the 8 reference products from Google Stitch design
const CANONICAL_DEMO_SKUS = [
  'NIKE-PEGASUS-40',
  'APPLE-MBA-M3',
  'SONY-WH1000XM5',
  'ADIDAS-ULTRABOOST-LT',
  'SAMSUNG-S24',
  'LOGI-MX-MECH',
  'DELL-U2723QE',
  'BOSE-QC-ULTRA',
];

// Primary category chips matching the reference screenshot
const PRIMARY_CHIPS = [
  { label: 'All', icon: null },
  { label: 'Footwear', icon: Footprints },
  { label: 'Electronics', icon: Laptop },
  { label: 'Audio', icon: Headphones },
  { label: 'Computers', icon: Monitor },
  { label: 'Apparel', icon: Shirt },
  { label: 'Accessories', icon: ShoppingBag },
  { label: 'Home', icon: Home },
];

export const StorefrontSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // Active query is driven by searchParams
  const queryParam = searchParams.get('q') || '';
  const [searchQuery, setSearchQuery] = useState<string>(queryParam);
  const [activeQuery, setActiveQuery] = useState<string>(queryParam);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [searchData, setSearchData] = useState<SearchResponse | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [selectedCategoryChip, setSelectedCategoryChip] = useState<string>('All');
  const [productImages, setProductImages] = useState<Record<number, string>>({});

  // Sync state if URL query changes
  useEffect(() => {
    setSearchQuery(queryParam);
    setActiveQuery(queryParam);
  }, [queryParam]);

  // Load catalog categories and products on mount
  useEffect(() => {
    let isMounted = true;
    Promise.all([getCategories(), getProducts()])
      .then(([cats, prods]) => {
        if (isMounted) {
          setCategories(cats);
          setAllProducts(prods);
        }
      })
      .catch((err) => console.error('Failed to load catalog data:', err));

    return () => {
      isMounted = false;
    };
  }, []);

  // Perform hybrid search
  const performSearch = useCallback(
    async (queryText: string) => {
      const trimmed = queryText.trim();
      if (!trimmed) {
        setSearchData(null);
        setActiveQuery('');
        setSearchParams({});
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const res = await executeHybridSearch(trimmed, 24, false);
        setSearchData(res);
        setActiveQuery(trimmed);
        setSearchParams({ q: trimmed });
      } catch (err: unknown) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [setSearchParams]
  );

  // Initial search if query param is set
  useEffect(() => {
    if (queryParam.trim()) {
      performSearch(queryParam.trim());
    } else {
      setSearchData(null);
      setActiveQuery('');
    }
  }, [queryParam, performSearch]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(searchQuery);
  };

  const handleShortcutClick = (queryText: string) => {
    setSearchQuery(queryText);
    performSearch(queryText);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setActiveQuery('');
    setSearchData(null);
    setSearchParams({});
  };

  const isSearchActive = Boolean(activeQuery.trim() && searchData);

  // Raw display items: ordered by canonical reference showcase for default view
  const rawDisplayItems: DisplayItem[] = useMemo(() => {
    if (isSearchActive && searchData?.results) {
      return searchData.results;
    }
    // Sort canonical products to the front matching the reference layout
    const sorted = [...allProducts].sort((a, b) => {
      const aIdx = CANONICAL_DEMO_SKUS.indexOf(a.sku);
      const bIdx = CANONICAL_DEMO_SKUS.indexOf(b.sku);
      if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
      if (aIdx !== -1) return -1;
      if (bIdx !== -1) return 1;
      return a.id - b.id;
    });

    return sorted.map((p) => ({
      product: p,
      score: 1.0,
      match_reasons: [],
    }));
  }, [isSearchActive, searchData, allProducts]);

  // Category chip filtering
  const displayedItems = useMemo(() => {
    if (selectedCategoryChip === 'All') return rawDisplayItems;

    const chipLower = selectedCategoryChip.toLowerCase();

    return rawDisplayItems.filter((item) => {
      const cat = categories.find((c) => c.id === item.product.category_id);
      const catName = (cat?.name || '').toLowerCase();
      const brand = (item.product.brand || '').toLowerCase();
      const title = (item.product.title || '').toLowerCase();

      if (chipLower === 'footwear') {
        return (
          catName.includes('shoe') ||
          catName.includes('foot') ||
          title.includes('pegasus') ||
          title.includes('ultraboost')
        );
      }
      if (chipLower === 'electronics') {
        return (
          catName.includes('electronic') ||
          catName.includes('phone') ||
          catName.includes('laptop') ||
          brand.includes('apple') ||
          brand.includes('samsung')
        );
      }
      if (chipLower === 'audio') {
        return (
          catName.includes('audio') ||
          catName.includes('headphone') ||
          brand.includes('sony') ||
          brand.includes('bose')
        );
      }
      if (chipLower === 'computers') {
        return (
          catName.includes('laptop') ||
          catName.includes('monitor') ||
          catName.includes('keyboard') ||
          catName.includes('computer')
        );
      }
      if (chipLower === 'apparel') {
        return catName.includes('apparel') || catName.includes('cloth');
      }
      if (chipLower === 'accessories') {
        return catName.includes('access') || catName.includes('keyboard');
      }
      if (chipLower === 'home') {
        return catName.includes('home') || catName.includes('monitor');
      }

      return catName === chipLower;
    });
  }, [rawDisplayItems, selectedCategoryChip, categories]);

  // Fetch product images for displayed items
  useEffect(() => {
    displayedItems.forEach((item) => {
      const pid = item.product.id;
      if (!productImages[pid]) {
        getProductImages(pid)
          .then((imgs) => {
            if (imgs && imgs.length > 0) {
              setProductImages((prev) => ({
                ...prev,
                [pid]: normalizeImageUrl(imgs[0].image_url),
              }));
            }
          })
          .catch(() => {});
      }
    });
  }, [displayedItems, productImages]);

  // Contextual ProductIQ Understood summary
  const understoodSummary = useMemo(() => {
    if (!searchData?.metadata?.parsed_filters) return null;
    const pf = searchData.metadata.parsed_filters;
    const parts: string[] = [];

    if (pf.category) parts.push(pf.category);
    if (pf.brand) parts.push(pf.brand);
    if (pf.max_price) parts.push(`≤ ${formatINR(pf.max_price)}`);
    if (searchData.metadata.semantic_query && searchData.metadata.semantic_query !== activeQuery) {
      parts.push(searchData.metadata.semantic_query);
    }

    return parts.length > 0 ? parts.join(' · ') : 'Direct Catalog Relevance';
  }, [searchData, activeQuery]);

  return (
    <div className="w-full bg-white">
      {/* 2. SEARCH HERO SECTION - Soft Panoramic Lavender/Blue Gradient */}
      <section
        className="relative overflow-hidden pt-4 pb-2.5 px-4 sm:px-6 lg:px-8"
        style={{
          background:
            'radial-gradient(circle at 10% 45%, rgba(226, 218, 255, 0.65) 0%, rgba(243, 245, 255, 0.3) 45%, transparent 75%), radial-gradient(circle at 90% 45%, rgba(230, 222, 255, 0.65) 0%, rgba(243, 245, 255, 0.3) 45%, transparent 75%), linear-gradient(180deg, rgba(247, 246, 255, 0.5) 0%, #ffffff 100%)',
        }}
      >
        {/* Left Floating Cutout Runner Shoe with Annotation */}
        <div className="hidden lg:block absolute left-4 xl:left-14 top-1.5 pointer-events-none select-none">
          <div className="relative">
            {/* Annotation & Hand-Drawn Curved Arrow */}
            <div className="absolute -top-1 left-6 flex flex-col items-start text-indigo-500 font-sans italic text-xs tracking-wide">
              <span className="transform -rotate-6 text-xs font-medium text-indigo-500/90 font-serif">Search naturally</span>
              <svg className="w-5 h-5 text-indigo-400 transform -rotate-12 -mt-0.5 ml-5 stroke-current fill-none" viewBox="0 0 32 32">
                <path d="M6 6 C 18 10, 24 20, 20 28" strokeWidth="1.7" strokeLinecap="round" />
                <path d="M15 25 L 20 28 L 23 23" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            {/* Free-floating shoe visual (tightened weight) */}
            <div className="w-28 h-22 flex items-center justify-center mt-2.5 transform -rotate-[16deg] hover:rotate-0 transition-transform duration-300">
              <img
                src="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=320&auto=format&fit=crop&q=80"
                alt="Nike Runner"
                className="w-full h-full object-contain filter drop-shadow-sm"
              />
            </div>
          </div>
        </div>

        {/* Right Floating Cutout Headphones with Annotation */}
        <div className="hidden lg:block absolute right-4 xl:right-14 top-1.5 pointer-events-none select-none">
          <div className="relative">
            {/* Annotation & Hand-Drawn Curved Arrow */}
            <div className="absolute -top-1 right-6 flex flex-col items-end text-indigo-500 font-sans italic text-xs tracking-wide">
              <span className="transform rotate-6 text-xs font-medium text-indigo-500/90 font-serif">Smarter results</span>
              <svg className="w-5 h-5 text-indigo-400 transform rotate-12 -mt-0.5 mr-5 stroke-current fill-none" viewBox="0 0 32 32">
                <path d="M26 6 C 14 10, 8 20, 12 28" strokeWidth="1.7" strokeLinecap="round" />
                <path d="M17 25 L 12 28 L 9 23" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            {/* Free-floating headphone visual (tightened weight) */}
            <div className="w-28 h-22 flex items-center justify-center mt-2.5 transform rotate-[12deg] hover:rotate-0 transition-transform duration-300">
              <img
                src="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=320&auto=format&fit=crop&q=80"
                alt="Headphones"
                className="w-full h-full object-contain filter drop-shadow-sm"
              />
            </div>
          </div>
        </div>

        {/* Hero Centered Content */}
        <div className="max-w-2xl mx-auto text-center relative z-10">
          <h1 className="text-2xl sm:text-[28px] font-extrabold text-slate-900 tracking-tight leading-tight">
            What are you looking for?
          </h1>
          <p className="text-xs sm:text-[13px] text-slate-500 mt-0.5 max-w-lg mx-auto font-normal">
            Search naturally. ProductIQ understands the rest.
          </p>

          {/* Large Rounded Search Input */}
          <form onSubmit={handleSearchSubmit} className="mt-2.5 max-w-lg mx-auto">
            <div className="relative flex items-center bg-white rounded-full border border-slate-200/90 shadow-2xs hover:shadow-xs focus-within:shadow-sm focus-within:border-blue-500 transition-all p-1 pl-4 sm:pl-5">
              <Search className="w-4 h-4 text-slate-400 shrink-0 mr-2.5" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Find Nike running shoes under ₹10,000"
                className="w-full bg-transparent text-xs sm:text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="p-1 mr-1 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100 transition-colors"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                type="submit"
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-semibold px-4 sm:px-5 py-2 rounded-full flex items-center gap-1 shadow-2xs transition-all shrink-0 cursor-pointer disabled:opacity-70"
              >
                <span>Search</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>

          {/* 3. POPULAR SEARCHES */}
          <div className="flex items-center justify-center flex-wrap gap-1.5 mt-1.5 text-xs">
            <span className="text-slate-400 font-medium text-[11px]">Popular searches:</span>
            {[
              'Running shoes',
              'Smartphones',
              'Laptops',
              'Headphones under ₹15,000',
              'Mechanical keyboards',
            ].map((pill) => (
              <button
                key={pill}
                type="button"
                onClick={() => handleShortcutClick(pill)}
                className="px-2.5 py-0.5 rounded-full bg-white border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 text-[11px] font-medium shadow-2xs transition-all cursor-pointer"
              >
                {pill}
              </button>
            ))}
          </div>

          {/* 4. CONTEXTUAL SEARCH INTELLIGENCE STRIP (Only after search) */}
          {isSearchActive && understoodSummary && (
            <div className="mt-2 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50/90 border border-indigo-100 text-xs text-slate-700 shadow-2xs flex-wrap justify-center animate-fadeIn">
              <span className="text-slate-400 text-[11px]">You searched:</span>
              <span className="font-semibold text-slate-800 text-[11px]">&ldquo;{activeQuery}&rdquo;</span>
              <span className="text-slate-300">•</span>
              <span className="font-semibold text-indigo-700 flex items-center gap-1 text-[11px]">
                <Sparkles className="w-3 h-3 text-indigo-600" />
                ProductIQ understood:
              </span>
              <span className="font-medium text-slate-900 bg-white px-2 py-0.5 rounded-full border border-indigo-200/70 shadow-2xs text-[11px]">
                {understoodSummary}
              </span>
            </div>
          )}
        </div>
      </section>

      {/* 5. COMPACT CATEGORY CHIPS ROW */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-1">
        <div className="flex items-center justify-start sm:justify-center gap-1.5 overflow-x-auto py-1 no-scrollbar">
          {PRIMARY_CHIPS.map((chip) => {
            const isSelected = selectedCategoryChip === chip.label;
            const Icon = chip.icon;
            return (
              <button
                key={chip.label}
                type="button"
                onClick={() => setSelectedCategoryChip(chip.label)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all shadow-2xs flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  isSelected
                    ? 'bg-blue-600 text-white font-semibold shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                {Icon && <Icon className="w-3.5 h-3.5" />}
                <span>{chip.label}</span>
              </button>
            );
          })}
          <div className="relative group shrink-0">
            <button
              type="button"
              className="px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50 flex items-center gap-1 cursor-pointer"
            >
              <span>More</span>
              <ChevronDown className="w-3 h-3 text-slate-400" />
            </button>
          </div>
        </div>
      </section>

      {/* 6. EXPLORE PRODUCTS SECTION & PRODUCT GRID */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-2.5 mb-8">
        {/* Section Header */}
        <div className="flex items-end justify-between border-b border-slate-100 pb-1.5 mb-2.5">
          <div>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              {isSearchActive ? 'Search Results' : 'Explore Products'}
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {isSearchActive ? `Relevant products for "${activeQuery}"` : 'Browse our catalog of verified products'}
            </p>
          </div>

          <div>
            <span className="text-xs text-slate-400 font-medium">
              {displayedItems.length} {displayedItems.length === 1 ? 'product' : 'products'}
            </span>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mt-3 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        {/* 7. PRODUCT GRID (4 columns desktop, 3 laptop, 2 tablet, 1 mobile) */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3.5 sm:gap-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <div
                key={n}
                className="bg-white rounded-xl border border-slate-200/80 overflow-hidden shadow-2xs animate-pulse"
              >
                <div className="h-40 bg-slate-100" />
                <div className="p-3 space-y-2">
                  <div className="h-3 w-20 bg-slate-100 rounded" />
                  <div className="h-4 w-3/4 bg-slate-100 rounded" />
                  <div className="h-5 w-16 bg-slate-100 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : displayedItems.length === 0 ? (
          <div className="py-14 text-center bg-white rounded-xl border border-slate-100 space-y-2">
            <Package className="w-10 h-10 text-slate-300 mx-auto" />
            <h3 className="text-sm font-semibold text-slate-800">No products found</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Try choosing a different category or adjusting your search keywords.
            </p>
            <button
              type="button"
              onClick={() => setSelectedCategoryChip('All')}
              className="text-xs font-semibold text-blue-600 hover:text-blue-700 transition-colors"
            >
              View all products
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3.5 sm:gap-4">
            {displayedItems.map((item) => {
              const prod = item.product;
              const cat = categories.find((c) => c.id === prod.category_id);
              const categoryName = cat?.name || 'Catalog';
              const imageUrl = productImages[prod.id];
              const matchReasons = item.match_reasons || [];

              return (
                <Link
                  key={prod.id}
                  to={`/storefront/products/${prod.id}`}
                  onClick={() => sessionStorage.setItem('last_viewed_product_id', String(prod.id))}
                  className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden shadow-2xs hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 flex flex-col group cursor-pointer"
                  title={`View ${prod.title}`}
                >
                  {/* Compact Product Image Area (~160px desktop) */}
                  <div className="h-40 sm:h-44 w-full bg-[#f8fafc] p-3 flex items-center justify-center relative overflow-hidden rounded-t-2xl">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={prod.title}
                        className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-200"
                        loading="lazy"
                      />
                    ) : (
                      <Package className="w-10 h-10 text-slate-300 group-hover:text-blue-500 transition-colors" />
                    )}
                  </div>

                  {/* Product Card Content */}
                  <div className="p-3 flex-1 flex flex-col justify-between bg-white">
                    <div>
                      {/* Brand · Category */}
                      <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase line-clamp-1">
                        {prod.brand || 'CATALOG'} · {categoryName.toUpperCase()}
                      </div>

                      {/* Product Title */}
                      <h3 className="text-sm font-bold text-slate-900 mt-0.5 line-clamp-1 group-hover:text-blue-600 transition-colors">
                        {prod.title}
                      </h3>

                      {/* INR Price */}
                      <div className="text-base font-extrabold text-slate-900 mt-1 font-sans">
                        {formatINR(prod.price)}
                      </div>
                    </div>

                    {/* Contextual Search Reason (Progressive Disclosure - only on search) */}
                    {isSearchActive && matchReasons.length > 0 && (
                      <div className="mt-2 pt-1.5 border-t border-slate-100 space-y-0.5">
                        {matchReasons.slice(0, 2).map((reason, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-1 text-[11px] text-emerald-700 font-medium"
                          >
                            <span className="text-emerald-600 font-bold">✓</span>
                            <span className="line-clamp-1">{reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
