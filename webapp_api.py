"""
Web App API Server
מספק REST API לממשק ה-Web App של הבוט
"""
import os
import logging
import hashlib
import hmac
from datetime import datetime
from functools import wraps
from typing import Optional
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from bson import ObjectId, json_util
import json

from config import Config
from database import db
from models import CouponStatus

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__, static_folder='webapp')
CORS(app)  # Enable CORS for all routes


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


@app.route('/api/categories')
async def get_categories():
    """Get all coupon categories"""
    from services.coupon_service import CouponService
    
    return jsonify({
        'categories': CouponService.CATEGORIES
    })


@app.route('/api/coupons')
async def get_coupons():
    """Get coupons with optional filters"""
    try:
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
        
        # Get coupons
        coupons_collection = await db.get_collection('coupons')
        
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
            sort_field = 'created_at'  # TODO: Calculate discount
            sort_dir = -1
        
        cursor = coupons_collection.find(query).sort(sort_field, sort_dir).skip(page * limit).limit(limit)
        coupons = []
        
        async for coupon in cursor:
            # Get seller info
            users_collection = await db.get_collection('users')
            seller = await users_collection.find_one({'user_id': coupon['seller_id']})
            
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
        total = await coupons_collection.count_documents(query)
        
        return jsonify({
            'coupons': coupons,
            'total': total,
            'page': page,
            'limit': limit,
            'has_more': (page + 1) * limit < total
        })
        
    except Exception as e:
        logger.error(f"Error getting coupons: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/coupons/<coupon_id>')
async def get_coupon_details(coupon_id: str):
    """Get single coupon details"""
    try:
        coupons_collection = await db.get_collection('coupons')
        coupon = await coupons_collection.find_one({'_id': ObjectId(coupon_id)})
        
        if not coupon:
            return jsonify({'error': 'Coupon not found'}), 404
        
        # Get seller info
        users_collection = await db.get_collection('users')
        seller = await users_collection.find_one({'user_id': coupon['seller_id']})
        
        # Get seller reviews
        reviews_collection = await db.get_collection('reviews')
        reviews_cursor = reviews_collection.find({'seller_id': coupon['seller_id']}).sort('created_at', -1).limit(5)
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
        
        return jsonify({
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
        })
        
    except Exception as e:
        logger.error(f"Error getting coupon details: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/favorites', methods=['GET'])
async def get_user_favorites():
    """Get user's favorite coupons"""
    # Get user from Telegram init data
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if not auth_data and not Config.DEBUG:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = auth_data.get('user', {}).get('id', 0) if auth_data else 0
    
    try:
        favorites_collection = await db.get_collection('favorites')
        coupons_collection = await db.get_collection('coupons')
        
        favorites = await favorites_collection.find_one({'user_id': user_id})
        favorite_ids = favorites.get('coupon_ids', []) if favorites else []
        
        # Get coupon details
        coupons = []
        for coupon_id in favorite_ids:
            coupon = await coupons_collection.find_one({'_id': coupon_id})
            if coupon and coupon.get('status') == CouponStatus.ACTIVE.value:
                coupons.append({
                    'id': str(coupon['_id']),
                    'title': coupon.get('title', ''),
                    'sale_price': coupon.get('sale_price', 0),
                    'original_price': coupon.get('original_price', 0),
                })
        
        return jsonify({'favorites': coupons})
        
    except Exception as e:
        logger.error(f"Error getting favorites: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/favorites/<coupon_id>', methods=['POST', 'DELETE'])
async def toggle_favorite(coupon_id: str):
    """Add or remove coupon from favorites"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if not auth_data and not Config.DEBUG:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = auth_data.get('user', {}).get('id', 0) if auth_data else 0
    
    try:
        favorites_collection = await db.get_collection('favorites')
        
        if request.method == 'POST':
            # Add to favorites
            await favorites_collection.update_one(
                {'user_id': user_id},
                {'$addToSet': {'coupon_ids': ObjectId(coupon_id)}},
                upsert=True
            )
            return jsonify({'success': True, 'action': 'added'})
        
        else:  # DELETE
            # Remove from favorites
            await favorites_collection.update_one(
                {'user_id': user_id},
                {'$pull': {'coupon_ids': ObjectId(coupon_id)}}
            )
            return jsonify({'success': True, 'action': 'removed'})
        
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chats')
async def get_user_chats():
    """Get user's chats"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if not auth_data and not Config.DEBUG:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = auth_data.get('user', {}).get('id', 0) if auth_data else 0
    
    try:
        chats_collection = await db.get_collection('chats')
        
        # Find chats where user is buyer or seller
        cursor = chats_collection.find({
            '$or': [
                {'buyer_id': user_id},
                {'seller_id': user_id}
            ]
        }).sort('updated_at', -1)
        
        chats = []
        async for chat in cursor:
            # Determine if user is buyer or seller
            is_buyer = chat['buyer_id'] == user_id
            other_user_id = chat['seller_id'] if is_buyer else chat['buyer_id']
            
            # Get other user info
            users_collection = await db.get_collection('users')
            other_user = await users_collection.find_one({'user_id': other_user_id})
            
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
        
        return jsonify({'chats': chats})
        
    except Exception as e:
        logger.error(f"Error getting chats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chats/<chat_id>/messages')
async def get_chat_messages(chat_id: str):
    """Get messages for a specific chat"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if not auth_data and not Config.DEBUG:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = auth_data.get('user', {}).get('id', 0) if auth_data else 0
    page = int(request.args.get('page', 0))
    limit = int(request.args.get('limit', 50))
    
    try:
        chats_collection = await db.get_collection('chats')
        messages_collection = await db.get_collection('chat_messages')
        
        # Verify user has access to chat
        chat = await chats_collection.find_one({'_id': ObjectId(chat_id)})
        if not chat:
            return jsonify({'error': 'Chat not found'}), 404
        
        if user_id not in [chat['buyer_id'], chat['seller_id']] and not Config.DEBUG:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get messages
        cursor = messages_collection.find(
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
        
        # Reverse to get chronological order
        messages.reverse()
        
        return jsonify({
            'messages': messages,
            'chat': {
                'id': str(chat['_id']),
                'buyer_id': chat['buyer_id'],
                'seller_id': chat['seller_id']
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/balance')
async def get_user_balance():
    """Get user's balance"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    auth_data = verify_telegram_data(init_data)
    
    if not auth_data and not Config.DEBUG:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = auth_data.get('user', {}).get('id', 0) if auth_data else 0
    
    try:
        users_collection = await db.get_collection('users')
        user = await users_collection.find_one({'user_id': user_id})
        
        if not user:
            return jsonify({
                'balance': 0,
                'frozen_balance': 0,
                'available': 0
            })
        
        balance = user.get('balance', 0)
        frozen = user.get('frozen_balance', 0)
        
        return jsonify({
            'balance': balance,
            'frozen_balance': frozen,
            'available': balance - frozen
        })
        
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== Main ====================

def run_webapp_server():
    """Run the webapp API server"""
    port = int(os.getenv('WEBAPP_PORT', 8080))
    
    # Connect to database
    import asyncio
    asyncio.get_event_loop().run_until_complete(db.connect())
    
    logger.info(f"Starting Web App API server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)


if __name__ == '__main__':
    run_webapp_server()
