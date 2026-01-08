/**
 * Coupon Marketplace - Chat Application
 * Web App for Telegram Mini Apps
 */

// Telegram WebApp Integration
const tg = window.Telegram?.WebApp;

// Initialize Telegram WebApp
if (tg) {
  tg.ready();
  tg.expand();
  
  // Set header color for chat
  tg.setHeaderColor('#0F2314');
  tg.setBackgroundColor('#0F2314');
  
  // Enable back button
  tg.BackButton.show();
  tg.BackButton.onClick(() => {
    window.location.href = 'index.html';
  });
}

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

// State
let isTyping = false;

/**
 * Get current time in HH:MM format
 */
function getCurrentTime() {
  const now = new Date();
  return now.toLocaleTimeString('he-IL', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false 
  });
}

/**
 * Create a message element
 */
function createMessage(text, type = 'buyer') {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message message--${type}`;
  
  const bubbleHTML = `
    <div class="message__bubble">
      ${type === 'admin' ? '<p class="message__label">👤 צוות תמיכה</p>' : ''}
      <p class="message__text">${escapeHtml(text)}</p>
      ${type !== 'system' ? `
        <div class="message__meta">
          <span class="message__time">${getCurrentTime()}</span>
          ${type === 'buyer' ? `
            <span class="message__status">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
              </svg>
            </span>
          ` : ''}
        </div>
      ` : ''}
    </div>
  `;
  
  messageDiv.innerHTML = bubbleHTML;
  return messageDiv;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Add a message to the chat
 */
function addMessage(text, type = 'buyer') {
  const message = createMessage(text, type);
  chatMessages.appendChild(message);
  
  // Scroll to bottom
  scrollToBottom();
  
  // Update read status after a delay (simulating server response)
  if (type === 'buyer') {
    setTimeout(() => {
      updateMessageStatus(message, 'read');
    }, 1500);
  }
}

/**
 * Update message status (sent -> delivered -> read)
 */
function updateMessageStatus(messageEl, status) {
  const statusEl = messageEl.querySelector('.message__status');
  if (!statusEl) return;
  
  if (status === 'read') {
    statusEl.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z"/>
      </svg>
    `;
  }
}

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Show typing indicator
 */
function showTypingIndicator() {
  if (isTyping) return;
  isTyping = true;
  
  const typingDiv = document.createElement('div');
  typingDiv.className = 'message message--seller';
  typingDiv.id = 'typingIndicator';
  typingDiv.innerHTML = `
    <div class="message__bubble" style="padding: 12px 16px;">
      <div style="display: flex; gap: 4px; align-items: center;">
        <span class="typing-dot" style="width: 8px; height: 8px; background: var(--primary); border-radius: 50%; animation: typingPulse 1s infinite;"></span>
        <span class="typing-dot" style="width: 8px; height: 8px; background: var(--primary); border-radius: 50%; animation: typingPulse 1s infinite 0.2s;"></span>
        <span class="typing-dot" style="width: 8px; height: 8px; background: var(--primary); border-radius: 50%; animation: typingPulse 1s infinite 0.4s;"></span>
      </div>
    </div>
  `;
  
  // Add animation styles
  if (!document.getElementById('typingStyles')) {
    const style = document.createElement('style');
    style.id = 'typingStyles';
    style.textContent = `
      @keyframes typingPulse {
        0%, 100% { opacity: 0.3; transform: scale(0.8); }
        50% { opacity: 1; transform: scale(1); }
      }
    `;
    document.head.appendChild(style);
  }
  
  chatMessages.appendChild(typingDiv);
  scrollToBottom();
}

/**
 * Hide typing indicator
 */
function hideTypingIndicator() {
  const typingEl = document.getElementById('typingIndicator');
  if (typingEl) {
    typingEl.remove();
  }
  isTyping = false;
}

/**
 * Simulate seller response
 */
function simulateSellerResponse() {
  const responses = [
    'תודה על ההודעה! אבדוק ואחזור אליך בהקדם 😊',
    'בטח! אני כאן לכל שאלה',
    'מעולה! שמח שאתה מתעניין',
    'אשמח לעזור! מה עוד תרצה לדעת?',
    'זה מצוין! הקופון באמת שווה את זה',
  ];
  
  showTypingIndicator();
  
  setTimeout(() => {
    hideTypingIndicator();
    const randomResponse = responses[Math.floor(Math.random() * responses.length)];
    addMessage(randomResponse, 'seller');
    
    // Haptic feedback
    if (tg?.HapticFeedback) {
      tg.HapticFeedback.notificationOccurred('success');
    }
  }, 1500 + Math.random() * 1500);
}

/**
 * Send a message
 */
function sendMessage() {
  const text = messageInput.value.trim();
  if (!text) return;
  
  // Add buyer message
  addMessage(text, 'buyer');
  
  // Clear input
  messageInput.value = '';
  
  // Haptic feedback
  if (tg?.HapticFeedback) {
    tg.HapticFeedback.impactOccurred('light');
  }
  
  // Simulate seller response (in production, this would go through the server)
  simulateSellerResponse();
}

/**
 * Handle input enter key
 */
function handleInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

/**
 * Initialize event listeners
 */
function initEventListeners() {
  // Send button
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
  }
  
  // Enter key to send
  if (messageInput) {
    messageInput.addEventListener('keydown', handleInputKeydown);
    
    // Focus input on page load
    setTimeout(() => {
      messageInput.focus();
    }, 300);
  }
}

/**
 * Initialize the chat
 */
function init() {
  initEventListeners();
  scrollToBottom();
  
  console.log('💬 Chat initialized');
  console.log('Telegram WebApp:', tg ? 'Connected' : 'Not available');
}

// Start the app when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
