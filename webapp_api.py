"""
Web App API Server
מספק REST API לממשק ה-Web App של הבוט
"""
import os
import logging
import hashlib
import hmac
import asyncio
from datetime import datetime
from functools import wraps
from typing import Optional
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from bson import ObjectId, json_util
from motor.motor_asyncio import AsyncIOMotorClient
import json

from config import Config
from models import CouponStatus

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__, static_folder='webapp')
CORS(app)  # Enable CORS for all routes

# Allow public access without Telegram auth (for browsing coupons)
# Set WEBAPP_REQUIRE_AUTH=true to require Telegram auth for all endpoints
REQUIRE_AUTH = os.getenv('WEBAPP_REQUIRE_AUTH', 'false').lower() == 'true'

# MongoDB connection (separate from bot's connection)
mongo_client = None
mongo_db = None


def get_db():
    """Get MongoDB database connection"""
    global mongo_client, mongo_db
    if mongo_db is None:
        mongo_client = AsyncIOMotorClient(Config.MONGODB_URI)
        mongo_db = mongo_client[Config.DATABASE_NAME]
    return mongo_db


def run_async(coro):
    """Run async function in sync context"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def get_current_user():
    """Get current user from Telegram auth or return anonymous user"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if auth_data:
        return auth_data.get('user', {})
    
    # Return anonymous user for public browsing
    return {'id': 0, 'first_name': 'אורח', 'is_anonymous': True}


# ==================== Telegram Auth ====================

def verify_telegram_data(init_data: str) -> Optional[dict]:
    """
    Verify Telegram Mini App init data
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None
    
    try:
        # Parse the init data
        parsed = dict(parse_qsl(init_data))
        
        # Get the hash
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return None
        
        # Sort and create data check string
        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        
        # Create secret key
        secret_key = hmac.new(
            b'WebAppData',
            Config.BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Calculate hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Verify
        if calculated_hash == received_hash:
            # Parse user data
            if 'user' in parsed:
                parsed['user'] = json.loads(parsed['user'])
            return parsed
        
        return None
        
    except Exception as e:
        logger.error(f"Error verifying Telegram data: {e}")
        return None


def telegram_auth_required(f):
    """Decorator to require Telegram authentication"""
    @wraps(f)
    async def decorated(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        
        # In development, allow without auth
        if Config.DEBUG and not init_data:
            request.telegram_user = {'id': 0, 'first_name': 'Debug User'}
            return await f(*args, **kwargs)
        
        auth_data = verify_telegram_data(init_data)
        if not auth_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        request.telegram_user = auth_data.get('user', {})
        return await f(*args, **kwargs)
    
    return decorated


# ==================== Helper Functions ====================

def json_response(data):
    """Convert MongoDB data to JSON-safe format"""
    return json.loads(json_util.dumps(data))


# ==================== Static Files ====================

@app.route('/')
def serve_index():
    """Serve the main webapp"""
    return send_from_directory('webapp', 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('webapp', path)


# ==================== API Routes ====================

@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/api/demo/seed')
def seed_demo_data():
    """Add demo coupons for testing (only in debug mode or with secret key)"""
    secret = request.args.get('key', '')
    expected_secret = os.getenv('DEMO_SEED_KEY', 'demo123')
    
    if secret != expected_secret:
        return jsonify({'error': 'Invalid key'}), 403
    
    async def _seed():
        db = get_db()
        
        # Check if demo data already exists
        existing = await db.coupons.find_one({'title': 'ארוחת בוקר זוגית מפנקת [DEMO]'})
        if existing:
            return {'message': 'Demo data already exists', 'seeded': False}
        
        demo_coupons = [
            {
                'seller_id': 0,
                'title': 'ארוחת בוקר זוגית מפנקת [DEMO]',
                'description': 'ארוחת בוקר עשירה לזוג כולל שתייה חמה',
                'category': '🍔 מסעדות ואוכל',
                'original_price': 150,
                'sale_price': 89,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
            {
                'seller_id': 0,
                'title': 'טיפול פנים מלא + עיסוי [DEMO]',
                'description': 'טיפול פנים מפנק כולל עיסוי צוואר',
                'category': '💆 יופי וספא',
                'original_price': 350,
                'sale_price': 199,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
            {
                'seller_id': 0,
                'title': 'כרטיס לסרט + פופקורן [DEMO]',
                'description': 'כרטיס לכל סרט + פופקורן גדול',
                'category': '🎬 בידור ופנאי',
                'original_price': 75,
                'sale_price': 45,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
            {
                'seller_id': 0,
                'title': 'אוזניות בלוטות׳ איכותיות [DEMO]',
                'description': 'אוזניות TWS עם ביטול רעשים',
                'category': '📱 מוצרי אלקטרוניקה',
                'original_price': 299,
                'sale_price': 149,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
            {
                'seller_id': 0,
                'title': 'קורס יוגה - 10 שיעורים [DEMO]',
                'description': 'כרטיסייה ל-10 שיעורי יוגה',
                'category': '🏋️ ספורט וכושר',
                'original_price': 500,
                'sale_price': 299,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
            {
                'seller_id': 0,
                'title': 'ארוחה איטלקית לזוג [DEMO]',
                'description': 'פסטה + קינוח + יין לזוג',
                'category': '🍔 מסעדות ואוכל',
                'original_price': 220,
                'sale_price': 129,
                'status': 'active',
                'created_at': datetime.utcnow()
            },
        ]
        
        result = await db.coupons.insert_many(demo_coupons)
        return {
            'message': 'Demo data seeded successfully',
            'seeded': True,
            'count': len(result.inserted_ids)
        }
    
    try:
        result = run_async(_seed())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error seeding demo data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories')
def get_categories():
    """Get all coupon categories"""
    # Categories list (same as in coupon_service.py)
    CATEGORIES = [
        "🍔 מסעדות ואוכל",
        "🎬 בידור ופנאי",
        "🛍️ קניות ואופנה",
        "💆 יופי וספא",
        "🏋️ ספורט וכושר",
        "✈️ טיולים ונופש",
        "🎓 לימודים והדרכה",
        "🔧 שירותים ומוצרים",
        "🎮 משחקים וטכנולוגיה",
        "📱 מוצרי אלקטרוניקה",
    ]
    
    return jsonify({
        'categories': CATEGORIES
    })


@app.route('/api/coupons')
def get_coupons():
    """Get coupons with optional filters"""
    
    async def _get_coupons():
        db = get_db()
        
        # Get query parameters
        category = request.args.get('category')
        search = request.args.get('search')
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 20))
        sort_by = request.args.get('sort', 'created_at')
        
        # Build query
        query = {'status': CouponStatus.ACTIVE.value}
        
        if category:
            query['category'] = category
        
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}}
            ]
        
        # Sort options
        sort_field = sort_by
        sort_dir = -1  # Descending
        
        if sort_by == 'price_low':
            sort_field = 'sale_price'
            sort_dir = 1
        elif sort_by == 'price_high':
            sort_field = 'sale_price'
            sort_dir = -1
        elif sort_by == 'discount':
            sort_field = 'created_at'
            sort_dir = -1
        
        cursor = db.coupons.find(query).sort(sort_field, sort_dir).skip(page * limit).limit(limit)
        coupons = []
        
        async for coupon in cursor:
            # Get seller info
            seller = await db.users.find_one({'user_id': coupon['seller_id']})
            
            # Calculate discount percentage
            discount = 0
            if coupon.get('original_price') and coupon.get('sale_price'):
                discount = round(
                    ((coupon['original_price'] - coupon['sale_price']) / coupon['original_price']) * 100
                )
            
            coupons.append({
                'id': str(coupon['_id']),
                'title': coupon.get('title', ''),
                'description': coupon.get('description', ''),
                'category': coupon.get('category', ''),
                'original_price': coupon.get('original_price', 0),
                'sale_price': coupon.get('sale_price', 0),
                'discount': discount,
                'seller_id': coupon.get('seller_id'),
                'seller_name': seller.get('business_name', seller.get('first_name', 'מוכר')) if seller else 'מוכר',
                'seller_rating': seller.get('rating_average', 0) if seller else 0,
                'created_at': coupon.get('created_at', datetime.utcnow()).isoformat(),
                'expires_at': coupon.get('expires_at').isoformat() if coupon.get('expires_at') else None,
            })
        
        # Get total count
        total = await db.coupons.count_documents(query)
        
        return {
            'coupons': coupons,
            'total': total,
            'page': page,
            'limit': limit,
            'has_more': (page + 1) * limit < total
        }
    
    try:
        result = run_async(_get_coupons())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting coupons: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/coupons/<coupon_id>')
def get_coupon_details(coupon_id: str):
    """Get single coupon details"""
    
    async def _get_coupon():
        db = get_db()
        coupon = await db.coupons.find_one({'_id': ObjectId(coupon_id)})
        
        if not coupon:
            return None
        
        # Get seller info
        seller = await db.users.find_one({'user_id': coupon['seller_id']})
        
        # Get seller reviews
        reviews_cursor = db.reviews.find({'seller_id': coupon['seller_id']}).sort('created_at', -1).limit(5)
        reviews = []
        
        async for review in reviews_cursor:
            reviews.append({
                'rating': review.get('rating', 0),
                'comment': review.get('comment', ''),
                'created_at': review.get('created_at', datetime.utcnow()).isoformat()
            })
        
        # Calculate discount
        discount = 0
        if coupon.get('original_price') and coupon.get('sale_price'):
            discount = round(
                ((coupon['original_price'] - coupon['sale_price']) / coupon['original_price']) * 100
            )
        
        return {
            'id': str(coupon['_id']),
            'title': coupon.get('title', ''),
            'description': coupon.get('description', ''),
            'category': coupon.get('category', ''),
            'original_price': coupon.get('original_price', 0),
            'sale_price': coupon.get('sale_price', 0),
            'discount': discount,
            'expires_at': coupon.get('expires_at').isoformat() if coupon.get('expires_at') else None,
            'seller': {
                'id': coupon.get('seller_id'),
                'name': seller.get('business_name', seller.get('first_name', 'מוכר')) if seller else 'מוכר',
                'rating': seller.get('rating_average', 0) if seller else 0,
                'total_reviews': seller.get('rating_count', 0) if seller else 0,
                'is_verified': seller.get('seller_status') == 'verified' if seller else False
            },
            'reviews': reviews
        }
    
    try:
        result = run_async(_get_coupon())
        if result is None:
            return jsonify({'error': 'Coupon not found'}), 404
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting coupon details: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/favorites', methods=['GET'])
def get_user_favorites():
    """Get user's favorite coupons"""
    user = get_current_user()
    
    # Require auth for user-specific data
    if user.get('is_anonymous') and REQUIRE_AUTH:
        return jsonify({'error': 'Unauthorized', 'message': 'יש להתחבר דרך טלגרם'}), 401
    
    user_id = user.get('id', 0)
    
    async def _get_favorites():
        db = get_db()
        favorites = await db.favorites.find_one({'user_id': user_id})
        favorite_ids = favorites.get('coupon_ids', []) if favorites else []
        
        coupons = []
        for coupon_id in favorite_ids:
            coupon = await db.coupons.find_one({'_id': coupon_id})
            if coupon and coupon.get('status') == CouponStatus.ACTIVE.value:
                coupons.append({
                    'id': str(coupon['_id']),
                    'title': coupon.get('title', ''),
                    'sale_price': coupon.get('sale_price', 0),
                    'original_price': coupon.get('original_price', 0),
                })
        
        return {'favorites': coupons}
    
    try:
        result = run_async(_get_favorites())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting favorites: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/favorites/<coupon_id>', methods=['POST', 'DELETE'])
def toggle_favorite(coupon_id: str):
    """Add or remove coupon from favorites"""
    user = get_current_user()
    
    # Require auth for modifying favorites
    if user.get('is_anonymous'):
        return jsonify({'error': 'Unauthorized', 'message': 'יש להתחבר דרך טלגרם כדי להוסיף למועדפים'}), 401
    
    user_id = user.get('id', 0)
    
    async def _toggle():
        db = get_db()
        if request.method == 'POST':
            await db.favorites.update_one(
                {'user_id': user_id},
                {'$addToSet': {'coupon_ids': ObjectId(coupon_id)}},
                upsert=True
            )
            return {'success': True, 'action': 'added'}
        else:
            await db.favorites.update_one(
                {'user_id': user_id},
                {'$pull': {'coupon_ids': ObjectId(coupon_id)}}
            )
            return {'success': True, 'action': 'removed'}
    
    try:
        result = run_async(_toggle())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chats')
def get_user_chats():
    """Get user's chats"""
    user = get_current_user()
    
    # Chats require authentication
    if user.get('is_anonymous'):
        return jsonify({'error': 'Unauthorized', 'message': 'יש להתחבר דרך טלגרם לצפייה בצ\'אטים'}), 401
    
    user_id = user.get('id', 0)
    
    async def _get_chats():
        db = get_db()
        cursor = db.chats.find({
            '$or': [
                {'buyer_id': user_id},
                {'seller_id': user_id}
            ]
        }).sort('updated_at', -1)
        
        chats = []
        async for chat in cursor:
            is_buyer = chat['buyer_id'] == user_id
            other_user_id = chat['seller_id'] if is_buyer else chat['buyer_id']
            other_user = await db.users.find_one({'user_id': other_user_id})
            
            chats.append({
                'id': str(chat['_id']),
                'other_user': {
                    'id': other_user_id,
                    'name': other_user.get('business_name', other_user.get('first_name', 'משתמש')) if other_user else 'משתמש',
                    'type': 'seller' if is_buyer else 'buyer'
                },
                'last_message': chat.get('last_message', ''),
                'unread_count': chat.get('unread_buyer' if is_buyer else 'unread_seller', 0),
                'updated_at': chat.get('updated_at', datetime.utcnow()).isoformat()
            })
        
        return {'chats': chats}
    
    try:
        result = run_async(_get_chats())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting chats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chats/<chat_id>/messages')
def get_chat_messages(chat_id: str):
    """Get messages for a specific chat"""
    user = get_current_user()
    
    # Chat messages require authentication
    if user.get('is_anonymous'):
        return jsonify({'error': 'Unauthorized', 'message': 'יש להתחבר דרך טלגרם לצפייה בהודעות'}), 401
    
    user_id = user.get('id', 0)
    page = int(request.args.get('page', 0))
    limit = int(request.args.get('limit', 50))
    
    async def _get_messages():
        db = get_db()
        chat = await db.chats.find_one({'_id': ObjectId(chat_id)})
        
        if not chat:
            return None, 'Chat not found'
        
        if user_id not in [chat['buyer_id'], chat['seller_id']]:
            return None, 'Access denied'
        
        cursor = db.chat_messages.find(
            {'chat_id': ObjectId(chat_id)}
        ).sort('created_at', -1).skip(page * limit).limit(limit)
        
        messages = []
        async for msg in cursor:
            sender_type = 'buyer'
            if msg['sender_id'] == chat['seller_id']:
                sender_type = 'seller'
            elif msg.get('is_admin'):
                sender_type = 'admin'
            elif msg.get('is_system'):
                sender_type = 'system'
            
            messages.append({
                'id': str(msg['_id']),
                'text': msg.get('text', ''),
                'sender_type': sender_type,
                'sender_id': msg.get('sender_id'),
                'is_read': msg.get('is_read', False),
                'created_at': msg.get('created_at', datetime.utcnow()).isoformat()
            })
        
        messages.reverse()
        
        return {
            'messages': messages,
            'chat': {
                'id': str(chat['_id']),
                'buyer_id': chat['buyer_id'],
                'seller_id': chat['seller_id']
            }
        }, None
    
    try:
        result, error = run_async(_get_messages())
        if error:
            return jsonify({'error': error}), 404 if error == 'Chat not found' else 403
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/balance')
def get_user_balance():
    """Get user's balance"""
    user = get_current_user()
    
    # Balance requires authentication
    if user.get('is_anonymous'):
        return jsonify({'error': 'Unauthorized', 'message': 'יש להתחבר דרך טלגרם לצפייה ביתרה'}), 401
    
    user_id = user.get('id', 0)
    
    async def _get_balance():
        db = get_db()
        user = await db.users.find_one({'user_id': user_id})
        
        if not user:
            return {
                'balance': 0,
                'frozen_balance': 0,
                'available': 0
            }
        
        balance = user.get('balance', 0)
        frozen = user.get('frozen_balance', 0)
        
        return {
            'balance': balance,
            'frozen_balance': frozen,
            'available': balance - frozen
        }
    
    try:
        result = run_async(_get_balance())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== Main ====================

if __name__ == '__main__':
    port = int(os.getenv('WEBAPP_PORT', 8080))
    logger.info(f"Starting Web App API server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
