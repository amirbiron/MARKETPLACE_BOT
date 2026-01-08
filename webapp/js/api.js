/**
 * API Service for Coupon Marketplace Web App
 * Handles all communication with the backend
 */

class ApiService {
  constructor() {
    // API base URL - in production, this would be your server URL
    this.baseUrl = window.location.origin + '/api';
    
    // Telegram WebApp integration
    this.tg = window.Telegram?.WebApp;
    this.initData = this.tg?.initData || '';
  }

  /**
   * Make an API request
   */
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    
    const headers = {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': this.initData,
      ...options.headers
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'API request failed');
      }

      return await response.json();
    } catch (error) {
      console.error(`API Error (${endpoint}):`, error);
      throw error;
    }
  }

  // ==================== Coupons ====================

  /**
   * Get list of coupons with optional filters
   */
  async getCoupons(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.category) queryParams.append('category', params.category);
    if (params.search) queryParams.append('search', params.search);
    if (params.page !== undefined) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.sort) queryParams.append('sort', params.sort);

    const query = queryParams.toString();
    return this.request(`/coupons${query ? '?' + query : ''}`);
  }

  /**
   * Get coupon details by ID
   */
  async getCouponDetails(couponId) {
    return this.request(`/coupons/${couponId}`);
  }

  /**
   * Get available categories
   */
  async getCategories() {
    return this.request('/categories');
  }

  // ==================== Favorites ====================

  /**
   * Get user's favorite coupons
   */
  async getFavorites() {
    return this.request('/user/favorites');
  }

  /**
   * Add coupon to favorites
   */
  async addToFavorites(couponId) {
    return this.request(`/user/favorites/${couponId}`, {
      method: 'POST'
    });
  }

  /**
   * Remove coupon from favorites
   */
  async removeFromFavorites(couponId) {
    return this.request(`/user/favorites/${couponId}`, {
      method: 'DELETE'
    });
  }

  // ==================== Chats ====================

  /**
   * Get user's chats
   */
  async getChats() {
    return this.request('/chats');
  }

  /**
   * Get messages for a specific chat
   */
  async getChatMessages(chatId, page = 0) {
    return this.request(`/chats/${chatId}/messages?page=${page}`);
  }

  // ==================== User ====================

  /**
   * Get user's balance
   */
  async getBalance() {
    return this.request('/user/balance');
  }
}

// Create global API instance
const api = new ApiService();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { api, ApiService };
}
