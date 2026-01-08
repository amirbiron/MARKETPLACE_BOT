/**
 * Coupon Marketplace - Main Application
 * Web App for Telegram Mini Apps
 */

// Telegram WebApp Integration
const tg = window.Telegram?.WebApp;

// Initialize Telegram WebApp
if (tg) {
  tg.ready();
  tg.expand();
  
  // Set header color
  tg.setHeaderColor('#183018');
  tg.setBackgroundColor('#183018');
}

// API mode flag - set to true when API is available
const USE_API = typeof api !== 'undefined';

// Sample Product Data (fallback when API is not available)
const sampleProducts = [
  {
    id: 1,
    name: 'ארוחת בוקר זוגית מפנקת',
    business: 'קפה שוק',
    price: 89,
    originalPrice: 150,
    discount: 40,
    image: 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=400&h=400&fit=crop',
    rating: 4.8,
    reviews: 124,
    isFavorite: false,
    category: 'food'
  },
  {
    id: 2,
    name: 'טיפול פנים מלא + עיסוי',
    business: 'ספא אורגני',
    price: 199,
    originalPrice: 350,
    discount: 43,
    image: 'https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=400&h=400&fit=crop',
    rating: 4.9,
    reviews: 89,
    isFavorite: true,
    category: 'beauty'
  },
  {
    id: 3,
    name: 'כרטיס לסרט + פופקורן',
    business: 'סינמה סיטי',
    price: 45,
    originalPrice: 75,
    discount: 40,
    image: 'https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=400&h=400&fit=crop',
    rating: 4.5,
    reviews: 256,
    isFavorite: false,
    category: 'entertainment'
  },
  {
    id: 4,
    name: 'חולצת ספורט מקצועית',
    business: 'סטייל פיט',
    price: 79,
    originalPrice: 149,
    discount: 47,
    image: 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop',
    rating: 4.6,
    reviews: 67,
    isFavorite: false,
    category: 'fashion'
  },
  {
    id: 5,
    name: 'אוזניות בלוטות׳ איכותיות',
    business: 'טק זון',
    price: 149,
    originalPrice: 299,
    discount: 50,
    image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop',
    rating: 4.7,
    reviews: 312,
    isFavorite: true,
    category: 'electronics'
  },
  {
    id: 6,
    name: 'ארוחה איטלקית לזוג',
    business: 'לה פיצה',
    price: 129,
    originalPrice: 220,
    discount: 41,
    image: 'https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=400&h=400&fit=crop',
    rating: 4.4,
    reviews: 178,
    isFavorite: false,
    category: 'food'
  },
  {
    id: 7,
    name: 'קורס יוגה - 10 שיעורים',
    business: 'סטודיו זן',
    price: 299,
    originalPrice: 500,
    discount: 40,
    image: 'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=400&h=400&fit=crop',
    rating: 4.9,
    reviews: 95,
    isFavorite: false,
    category: 'beauty'
  },
  {
    id: 8,
    name: 'מארז קוסמטיקה טבעית',
    business: 'נייצ׳ר ביוטי',
    price: 159,
    originalPrice: 280,
    discount: 43,
    image: 'https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400&h=400&fit=crop',
    rating: 4.8,
    reviews: 143,
    isFavorite: false,
    category: 'beauty'
  }
];

// DOM Elements
const productGrid = document.getElementById('productGrid');
const tabs = document.querySelectorAll('.tab');
const filterBtns = document.querySelectorAll('.filter-btn');

// State
let currentCategory = 'all';
let currentFilter = 'sale';
let favorites = new Set();

// Initialize favorites from sample data
sampleProducts.forEach(product => {
  if (product.isFavorite) {
    favorites.add(product.id);
  }
});

/**
 * Render a single product card
 */
function renderProductCard(product) {
  const isFavorite = favorites.has(product.id);
  
  return `
    <article class="product-card" data-id="${product.id}" onclick="openProduct(${product.id})">
      <div class="product-card__image-container">
        <img 
          src="${product.image}" 
          alt="${product.name}" 
          class="product-card__image"
          loading="lazy"
        >
        <span class="product-card__badge">${product.discount}% הנחה</span>
        <button 
          class="product-card__favorite ${isFavorite ? 'product-card__favorite--active' : ''}"
          onclick="toggleFavorite(event, ${product.id})"
          aria-label="${isFavorite ? 'הסר מהמועדפים' : 'הוסף למועדפים'}"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${isFavorite ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
        </button>
      </div>
      <div class="product-card__content">
        <h3 class="product-card__name">${product.name}</h3>
        <p class="product-card__business">${product.business}</p>
        <div class="product-card__price-container">
          <span class="product-card__price">${product.price}₪</span>
          <span class="product-card__price-original">${product.originalPrice}₪</span>
        </div>
        <div class="product-card__rating">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          <span class="product-card__rating-text">${product.rating} (${product.reviews})</span>
        </div>
      </div>
    </article>
  `;
}

/**
 * Render all products to the grid
 */
function renderProducts(products) {
  if (!productGrid) return;
  
  if (products.length === 0) {
    productGrid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <svg class="empty-state__icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 class="empty-state__title">לא נמצאו קופונים</h3>
        <p class="empty-state__text">נסה לשנות את הסינון או הקטגוריה</p>
      </div>
    `;
    return;
  }
  
  productGrid.innerHTML = products.map(renderProductCard).join('');
}

/**
 * Filter products by category
 */
function filterByCategory(category) {
  currentCategory = category;
  applyFilters();
}

/**
 * Apply all active filters
 */
function applyFilters() {
  if (USE_API) {
    // When using API, reload products with new filters
    loadProducts();
  } else {
    // When using sample data, filter locally
    let filteredProducts = [...sampleProducts];
    
    // Filter by category
    if (currentCategory !== 'all') {
      const categoryMap = {
        'food': 'food',
        'fashion': 'fashion',
        'electronics': 'electronics',
        'beauty': 'beauty',
        'entertainment': 'entertainment'
      };
      filteredProducts = filteredProducts.filter(p => p.category === currentCategory);
    }
    
    // Apply sort/filter
    switch (currentFilter) {
      case 'sale':
        filteredProducts.sort((a, b) => b.discount - a.discount);
        break;
      case 'new':
        // In production, sort by date
        filteredProducts.reverse();
        break;
      case 'popular':
        filteredProducts.sort((a, b) => b.reviews - a.reviews);
        break;
    }
    
    renderProducts(filteredProducts);
  }
}

/**
 * Toggle favorite status
 */
function toggleFavorite(event, productId) {
  event.stopPropagation();
  
  const btn = event.currentTarget;
  const svg = btn.querySelector('svg');
  
  if (favorites.has(productId)) {
    favorites.delete(productId);
    btn.classList.remove('product-card__favorite--active');
    svg.setAttribute('fill', 'none');
    
    // Haptic feedback
    if (tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred('light');
    }
  } else {
    favorites.add(productId);
    btn.classList.add('product-card__favorite--active');
    svg.setAttribute('fill', 'currentColor');
    
    // Heart animation
    btn.style.transform = 'scale(1.2)';
    setTimeout(() => {
      btn.style.transform = '';
    }, 200);
    
    // Haptic feedback
    if (tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred('medium');
    }
  }
}

/**
 * Open product detail / chat
 */
function openProduct(productId) {
  const product = sampleProducts.find(p => p.id === productId);
  if (!product) return;
  
  // Haptic feedback
  if (tg?.HapticFeedback) {
    tg.HapticFeedback.impactOccurred('light');
  }
  
  // Navigate to chat page (in production, would pass product context)
  window.location.href = `chat.html?product=${productId}`;
}

/**
 * Initialize tab click handlers
 */
function initTabs() {
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      // Update active state
      tabs.forEach(t => t.classList.remove('tab--active'));
      tabs.forEach(t => t.classList.add('tab--inactive'));
      tab.classList.remove('tab--inactive');
      tab.classList.add('tab--active');
      
      // Get category from tab text
      const tabText = tab.textContent.trim();
      const categoryMap = {
        'הכל': 'all',
        'אוכל ומסעדות': 'food',
        'אופנה': 'fashion',
        'אלקטרוניקה': 'electronics',
        'בריאות ויופי': 'beauty',
        'בידור': 'entertainment',
        'נסיעות': 'travel'
      };
      
      filterByCategory(categoryMap[tabText] || 'all');
      
      // Haptic feedback
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.selectionChanged();
      }
    });
  });
}

/**
 * Initialize filter button handlers
 */
function initFilters() {
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      // Get filter type from button text
      const btnText = btn.textContent.trim();
      const filterMap = {
        'ירידת מחירים': 'sale',
        'חדש': 'new',
        'פופולרי': 'popular',
        'קרוב אליי': 'nearby'
      };
      
      currentFilter = filterMap[btnText] || 'sale';
      applyFilters();
      
      // Haptic feedback
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
      }
    });
  });
}

/**
 * Load products from API or use sample data
 */
async function loadProducts() {
  if (USE_API) {
    try {
      showLoading();
      const params = {
        page: 0,
        limit: 20
      };
      
      if (currentCategory !== 'all') {
        params.category = currentCategory;
      }
      
      if (currentFilter === 'sale') {
        params.sort = 'discount';
      } else if (currentFilter === 'new') {
        params.sort = 'created_at';
      } else if (currentFilter === 'popular') {
        params.sort = 'popular';
      }
      
      const response = await api.getCoupons(params);
      
      // Transform API data to match our format
      const products = response.coupons.map(coupon => ({
        id: coupon.id,
        name: coupon.title,
        business: coupon.seller_name,
        price: coupon.sale_price,
        originalPrice: coupon.original_price,
        discount: coupon.discount,
        image: `https://via.placeholder.com/400x400/1E3728/30F078?text=${encodeURIComponent(coupon.title.substring(0, 10))}`,
        rating: coupon.seller_rating || 4.5,
        reviews: 0,
        isFavorite: false,
        category: coupon.category
      }));
      
      hideLoading();
      renderProducts(products);
      
    } catch (error) {
      console.error('Failed to load from API, using sample data:', error);
      hideLoading();
      renderProducts(sampleProducts);
    }
  } else {
    renderProducts(sampleProducts);
  }
}

/**
 * Show loading state
 */
function showLoading() {
  if (!productGrid) return;
  
  productGrid.innerHTML = `
    <div class="product-card">
      <div class="skeleton skeleton--image"></div>
      <div style="padding: var(--spacing-md);">
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text-sm"></div>
      </div>
    </div>
    <div class="product-card">
      <div class="skeleton skeleton--image"></div>
      <div style="padding: var(--spacing-md);">
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text-sm"></div>
      </div>
    </div>
    <div class="product-card">
      <div class="skeleton skeleton--image"></div>
      <div style="padding: var(--spacing-md);">
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text-sm"></div>
      </div>
    </div>
    <div class="product-card">
      <div class="skeleton skeleton--image"></div>
      <div style="padding: var(--spacing-md);">
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text-sm"></div>
      </div>
    </div>
  `;
}

/**
 * Hide loading state
 */
function hideLoading() {
  // Loading will be replaced by actual content
}

/**
 * Initialize the application
 */
function init() {
  initTabs();
  initFilters();
  loadProducts();
  
  console.log('🛒 Coupon Marketplace initialized');
  console.log('Telegram WebApp:', tg ? 'Connected' : 'Not available');
  console.log('API Mode:', USE_API ? 'Enabled' : 'Demo Mode');
}

// Start the app when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
