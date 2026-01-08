"""
MongoDB Database Management with Motor (async MongoDB driver)
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import IndexModel, ASCENDING, DESCENDING
from config import Config
import logging

logger = logging.getLogger(__name__)


class Database:
    """MongoDB Database Manager using Motor (async MongoDB driver)"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        
        # Collections
        self.users: Optional[AsyncIOMotorCollection] = None
        self.coupons: Optional[AsyncIOMotorCollection] = None
        self.orders: Optional[AsyncIOMotorCollection] = None
        self.auctions: Optional[AsyncIOMotorCollection] = None
        self.messages: Optional[AsyncIOMotorCollection] = None
        self.chats: Optional[AsyncIOMotorCollection] = None
        self.notifications: Optional[AsyncIOMotorCollection] = None
        self.payouts: Optional[AsyncIOMotorCollection] = None
        self.reviews: Optional[AsyncIOMotorCollection] = None
        self.review_reports: Optional[AsyncIOMotorCollection] = None
        self.favorites: Optional[AsyncIOMotorCollection] = None
        self.disputes: Optional[AsyncIOMotorCollection] = None
        self.dispute_messages: Optional[AsyncIOMotorCollection] = None
        self.transactions: Optional[AsyncIOMotorCollection] = None
        self.payment_requests: Optional[AsyncIOMotorCollection] = None
        self.support_tickets: Optional[AsyncIOMotorCollection] = None
        self.deposit_requests: Optional[AsyncIOMotorCollection] = None
        self.fraud_logs: Optional[AsyncIOMotorCollection] = None
        self.escrow_transactions: Optional[AsyncIOMotorCollection] = None
        self.escrow_logs: Optional[AsyncIOMotorCollection] = None
        self.payment_gateway_transactions: Optional[AsyncIOMotorCollection] = None
        self.saved_cards: Optional[AsyncIOMotorCollection] = None
        self.payout_transactions: Optional[AsyncIOMotorCollection] = None
        self.daily_card_limits: Optional[AsyncIOMotorCollection] = None
        self.seller_analytics: Optional[AsyncIOMotorCollection] = None
        self.seller_alert_settings: Optional[AsyncIOMotorCollection] = None
        self.scheduled_coupons: Optional[AsyncIOMotorCollection] = None
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = AsyncIOMotorClient(Config.MONGODB_URI)
            self.db = self.client[Config.DATABASE_NAME]
            
            # Initialize collections
            self.users = self.db["users"]
            self.coupons = self.db["coupons"]
            self.orders = self.db["orders"]
            self.auctions = self.db["auctions"]
            self.messages = self.db["messages"]
            self.chats = self.db["chats"]
            self.notifications = self.db["notifications"]
            self.payouts = self.db["payouts"]
            self.reviews = self.db["reviews"]
            self.review_reports = self.db["review_reports"]
            self.favorites = self.db["favorites"]
            self.disputes = self.db["disputes"]
            self.dispute_messages = self.db["dispute_messages"]
            self.transactions = self.db["transactions"]
            self.payment_requests = self.db["payment_requests"]
            self.support_tickets = self.db["support_tickets"]
            self.deposit_requests = self.db["deposit_requests"]
            self.fraud_logs = self.db["fraud_logs"]
            self.escrow_transactions = self.db["escrow_transactions"]
            self.escrow_logs = self.db["escrow_logs"]
            self.payment_gateway_transactions = self.db["payment_gateway_transactions"]
            self.saved_cards = self.db["saved_cards"]
            self.payout_transactions = self.db["payout_transactions"]
            self.daily_card_limits = self.db["daily_card_limits"]
            self.seller_analytics = self.db["seller_analytics"]
            self.seller_alert_settings = self.db["seller_alert_settings"]
            self.scheduled_coupons = self.db["scheduled_coupons"]
            
            # Test connection
            await self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            
            # Migration/compat: older versions created a unique index on `telegram_id`
            # which breaks inserts that only set `user_id` (missing `telegram_id` becomes
            # a duplicate null in a non-sparse unique index). Drop it if present.
            try:
                existing = await self.users.index_information()
                telegram_idx = existing.get("telegram_id_1")
                if telegram_idx and telegram_idx.get("unique") and not telegram_idx.get("sparse"):
                    await self.users.drop_index("telegram_id_1")
                    logger.info("Dropped legacy unique index users.telegram_id_1")
            except Exception as e:
                logger.warning(f"Failed to check/drop legacy telegram_id index: {e}")

            # Create indexes
            await self._create_indexes()
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    async def _create_indexes(self):
        """Create database indexes"""
        try:
            # Users indexes
            await self.users.create_indexes([
                # NOTE: the codebase uses `user_id` (Telegram ID) as the primary key.
                # Keep this unique to prevent duplicate user documents.
                IndexModel([("user_id", ASCENDING)], unique=True),
                IndexModel([("role", ASCENDING)]),
                IndexModel([("is_verified", ASCENDING)])
            ])
            
            # Coupons indexes
            await self.coupons.create_indexes([
                IndexModel([("seller_id", ASCENDING)]),
                IndexModel([("category", ASCENDING)]),
                IndexModel([("status", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)])
            ])
            
            # Orders indexes
            await self.orders.create_indexes([
                IndexModel([("buyer_id", ASCENDING)]),
                IndexModel([("seller_id", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING)])
            ])
            
            # Auctions indexes
            await self.auctions.create_indexes([
                IndexModel([("status", ASCENDING)]),
                IndexModel([("end_time", ASCENDING)]),
                IndexModel([("seller_id", ASCENDING)])
            ])

            # Notifications indexes
            await self.notifications.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("read", ASCENDING), ("created_at", DESCENDING)])
            ])

            # Chats indexes
            await self.chats.create_indexes([
                IndexModel([("buyer_id", ASCENDING), ("status", ASCENDING), ("last_message_at", DESCENDING)]),
                IndexModel([("seller_id", ASCENDING), ("status", ASCENDING), ("last_message_at", DESCENDING)]),
            ])

            # Messages indexes (used both for anonymous chat and chat service)
            await self.messages.create_indexes([
                IndexModel([("chat_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("recipient_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)]),
            ])

            # Support tickets indexes
            await self.support_tickets.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
            ])
            
            # Reviews indexes
            await self.reviews.create_indexes([
                IndexModel([("seller_id", ASCENDING)]),
                IndexModel([("buyer_id", ASCENDING), ("seller_id", ASCENDING)], unique=True)
            ])

            # Review reports indexes
            await self.review_reports.create_indexes([
                IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
                IndexModel([("review_id", ASCENDING)]),
            ])
            
            # Transactions indexes
            await self.transactions.create_indexes([
                IndexModel([("user_id", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)])
            ])

            # Payment requests indexes
            await self.payment_requests.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING), ("expires_at", ASCENDING)]),
            ])

            # Dispute messages indexes
            await self.dispute_messages.create_indexes([
                IndexModel([("dispute_id", ASCENDING), ("created_at", ASCENDING)]),
            ])

            # Deposit requests indexes
            await self.deposit_requests.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
                IndexModel([("reference_code", ASCENDING)]),
            ])

            # Fraud logs indexes
            await self.fraud_logs.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("event_type", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("risk_level", ASCENDING), ("reviewed", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("reviewed", ASCENDING), ("created_at", ASCENDING)]),
            ])

            # Escrow transactions indexes
            await self.escrow_transactions.create_indexes([
                IndexModel([("order_id", ASCENDING)], unique=True),
                IndexModel([("buyer_id", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("seller_id", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("status", ASCENDING), ("release_scheduled_at", ASCENDING)]),
                IndexModel([("held_at", DESCENDING)]),
            ])

            # Escrow logs indexes
            await self.escrow_logs.create_indexes([
                IndexModel([("escrow_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("action", ASCENDING), ("created_at", DESCENDING)]),
            ])

            # Payment gateway transactions indexes
            await self.payment_gateway_transactions.create_indexes([
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("gateway", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("gateway_transaction_id", ASCENDING)]),
                IndexModel([("expires_at", ASCENDING)], sparse=True),
                IndexModel([("order_id", ASCENDING)], sparse=True),
            ])

            # Saved cards indexes
            await self.saved_cards.create_indexes([
                IndexModel([("user_id", ASCENDING)]),
                IndexModel([("user_id", ASCENDING), ("is_default", ASCENDING)]),
                IndexModel([("card_token", ASCENDING)], unique=True),
            ])

            # Payout transactions indexes
            await self.payout_transactions.create_indexes([
                IndexModel([("seller_id", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
                IndexModel([("method", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("gateway_reference", ASCENDING)], sparse=True),
            ])

            # Daily card limits indexes
            await self.daily_card_limits.create_indexes([
                IndexModel([("user_id", ASCENDING), ("date", ASCENDING)], unique=True),
            ])

            # Seller analytics indexes
            await self.seller_analytics.create_indexes([
                IndexModel([("seller_id", ASCENDING), ("date", DESCENDING)]),
                IndexModel([("seller_id", ASCENDING), ("date", ASCENDING)], unique=True),
            ])

            # Seller alert settings indexes
            await self.seller_alert_settings.create_indexes([
                IndexModel([("seller_id", ASCENDING)], unique=True),
            ])

            # Scheduled coupons indexes
            await self.scheduled_coupons.create_indexes([
                IndexModel([("seller_id", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("status", ASCENDING), ("scheduled_at", ASCENDING)]),
            ])
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            raise
    
    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    # User Methods
    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user by telegram ID"""
        return await self.users.find_one({"telegram_id": telegram_id})
    
    async def create_user(self, telegram_id: int, username: Optional[str] = None, 
                         first_name: Optional[str] = None) -> Dict[str, Any]:
        """Create new user"""
        user_data = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "role": "buyer",
            "balance": 0.0,
            "frozen_balance": 0.0,
            "verified": False,
            "blocked": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await self.users.insert_one(user_data)
        return user_data
    
    async def update_user_balance(self, telegram_id: int, amount: float, 
                                 freeze: bool = False) -> bool:
        """Update user balance"""
        field = "frozen_balance" if freeze else "balance"
        result = await self.users.update_one(
            {"telegram_id": telegram_id},
            {
                "$inc": {field: amount},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return result.modified_count > 0
    
    async def upgrade_to_seller(self, telegram_id: int, business_name: str, 
                               phone: str, verified: bool = False, 
                               id_number: Optional[str] = None) -> bool:
        """Upgrade user to seller"""
        update_data = {
            "role": "seller",
            "business_name": business_name,
            "phone": phone,
            "verified": verified,
            "seller_registered_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        if id_number:
            update_data["id_number"] = id_number
        
        result = await self.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def get_pending_sellers(self) -> List[Dict[str, Any]]:
        """Get pending seller approvals"""
        cursor = self.users.find({
            "role": "seller",
            "blocked": False,
            "seller_approved": {"$exists": False}
        })
        return await cursor.to_list(length=None)
    
    async def approve_seller(self, telegram_id: int, approved: bool) -> bool:
        """Approve or reject seller"""
        result = await self.users.update_one(
            {"telegram_id": telegram_id},
            {
                "$set": {
                    "seller_approved": approved,
                    "blocked": not approved,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    # Coupon Methods
    async def create_coupon(self, seller_id: int, category: str, name: str,
                           original_price: float, sale_price: float,
                           description: Optional[str] = None,
                           expiry_date: Optional[datetime] = None) -> str:
        """Create new coupon"""
        coupon_data = {
            "seller_id": seller_id,
            "category": category,
            "name": name,
            "original_price": original_price,
            "sale_price": sale_price,
            "description": description,
            "expiry_date": expiry_date,
            "status": "active",
            "views": 0,
            "purchases": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.coupons.insert_one(coupon_data)
        return str(result.inserted_id)
    
    async def get_coupons_by_category(self, category: str, 
                                     page: int = 0) -> List[Dict[str, Any]]:
        """Get coupons by category with pagination"""
        skip = page * Config.ITEMS_PER_PAGE
        cursor = self.coupons.find({
            "category": category,
            "status": "active"
        }).sort("created_at", DESCENDING).skip(skip).limit(Config.ITEMS_PER_PAGE)
        return await cursor.to_list(length=None)
    
    async def get_coupon_by_id(self, coupon_id: str) -> Optional[Dict[str, Any]]:
        """Get coupon by ID"""
        from bson.objectid import ObjectId
        try:
            return await self.coupons.find_one({"_id": ObjectId(coupon_id)})
        except:
            return None
    
    async def increment_coupon_views(self, coupon_id: str):
        """Increment coupon view counter"""
        from bson.objectid import ObjectId
        await self.coupons.update_one(
            {"_id": ObjectId(coupon_id)},
            {"$inc": {"views": 1}}
        )
    
    async def get_seller_coupons(self, seller_id: int) -> List[Dict[str, Any]]:
        """Get all coupons by seller"""
        cursor = self.coupons.find({
            "seller_id": seller_id
        }).sort("created_at", DESCENDING)
        return await cursor.to_list(length=None)
    
    async def count_seller_coupons_today(self, seller_id: int) -> int:
        """Count coupons created today by seller"""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        count = await self.coupons.count_documents({
            "seller_id": seller_id,
            "created_at": {"$gte": today_start}
        })
        return count
    
    # Order Methods
    async def create_order(self, buyer_id: int, seller_id: int, coupon_id: str,
                          original_price: float, sale_price: float, 
                          buyer_commission: float, seller_commission: float,
                          coupon_code: str) -> str:
        """Create new order"""
        order_data = {
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "coupon_id": coupon_id,
            "original_price": original_price,
            "sale_price": sale_price,
            "buyer_commission": buyer_commission,
            "seller_commission": seller_commission,
            "total_paid": sale_price + buyer_commission,
            "seller_receives": sale_price - seller_commission,
            "coupon_code": coupon_code,
            "status": "completed",
            "can_report_until": datetime.utcnow() + timedelta(hours=Config.DISPUTE_WINDOW_HOURS),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.orders.insert_one(order_data)
        
        # Update coupon purchases counter
        await self.coupons.update_one(
            {"_id": __import__('bson').objectid.ObjectId(coupon_id)},
            {"$inc": {"purchases": 1}}
        )
        
        return str(result.inserted_id)
    
    async def get_user_orders(self, user_id: int, as_buyer: bool = True) -> List[Dict[str, Any]]:
        """Get user's orders (as buyer or seller)"""
        field = "buyer_id" if as_buyer else "seller_id"
        cursor = self.orders.find({
            field: user_id
        }).sort("created_at", DESCENDING)
        return await cursor.to_list(length=None)
    
    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order by ID"""
        from bson.objectid import ObjectId
        try:
            return await self.orders.find_one({"_id": ObjectId(order_id)})
        except:
            return None
    
    async def get_sold_coupons(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recently sold coupons for transparency"""
        cursor = self.orders.find({
            "status": "completed"
        }).sort("created_at", DESCENDING).limit(limit)
        return await cursor.to_list(length=None)
    
    # Review Methods
    async def create_review(self, buyer_id: int, seller_id: int, 
                           rating: int, comment: str) -> bool:
        """Create review for seller"""
        review_data = {
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "rating": rating,
            "comment": comment[:15],  # Max 15 characters
            "created_at": datetime.utcnow()
        }
        try:
            await self.reviews.insert_one(review_data)
            return True
        except:
            return False
    
    async def get_seller_reviews(self, seller_id: int, 
                                page: int = 0) -> List[Dict[str, Any]]:
        """Get seller reviews with pagination"""
        skip = page * Config.ITEMS_PER_PAGE
        cursor = self.reviews.find({
            "seller_id": seller_id
        }).sort("created_at", DESCENDING).skip(skip).limit(Config.ITEMS_PER_PAGE)
        return await cursor.to_list(length=None)
    
    async def get_seller_average_rating(self, seller_id: int) -> float:
        """Calculate seller's average rating"""
        pipeline = [
            {"$match": {"seller_id": seller_id}},
            {"$group": {
                "_id": None,
                "avg_rating": {"$avg": "$rating"}
            }}
        ]
        cursor = self.reviews.aggregate(pipeline)
        results = await cursor.to_list(length=1)
        if results:
            return round(results[0]["avg_rating"], 1)
        return 0.0
    
    async def can_user_review_seller(self, buyer_id: int, seller_id: int) -> bool:
        """Check if user can review seller (must have purchased)"""
        # Check if already reviewed
        existing = await self.reviews.find_one({
            "buyer_id": buyer_id,
            "seller_id": seller_id
        })
        if existing:
            return False
        
        # Check if has purchased from this seller
        order = await self.orders.find_one({
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "status": "completed"
        })
        return order is not None
    
    # Transaction Methods
    async def create_transaction(self, user_id: int, transaction_type: str,
                                amount: float, description: str,
                                reference_id: Optional[str] = None) -> str:
        """Create transaction record"""
        transaction_data = {
            "user_id": user_id,
            "type": transaction_type,
            "amount": amount,
            "description": description,
            "reference_id": reference_id,
            "created_at": datetime.utcnow()
        }
        result = await self.transactions.insert_one(transaction_data)
        return str(result.inserted_id)
    
    async def get_user_transactions(self, user_id: int, 
                                   limit: int = 50) -> List[Dict[str, Any]]:
        """Get user's transaction history"""
        cursor = self.transactions.find({
            "user_id": user_id
        }).sort("created_at", DESCENDING).limit(limit)
        return await cursor.to_list(length=None)
    
    # Favorite Methods
    async def add_favorite(self, user_id: int, coupon_id: str) -> bool:
        """Add coupon to favorites"""
        try:
            await self.favorites.insert_one({
                "user_id": user_id,
                "coupon_id": coupon_id,
                "created_at": datetime.utcnow()
            })
            return True
        except:
            return False
    
    async def remove_favorite(self, user_id: int, coupon_id: str) -> bool:
        """Remove coupon from favorites"""
        result = await self.favorites.delete_one({
            "user_id": user_id,
            "coupon_id": coupon_id
        })
        return result.deleted_count > 0
    
    async def get_user_favorites(self, user_id: int) -> List[str]:
        """Get user's favorite coupon IDs"""
        cursor = self.favorites.find({"user_id": user_id})
        favorites = await cursor.to_list(length=None)
        return [fav["coupon_id"] for fav in favorites]
    
    async def is_favorite(self, user_id: int, coupon_id: str) -> bool:
        """Check if coupon is in user's favorites"""
        doc = await self.favorites.find_one({
            "user_id": user_id,
            "coupon_id": coupon_id
        })
        return doc is not None
    
    # Dispute Methods
    async def create_dispute(self, order_id: str, buyer_id: int, 
                           seller_id: int, reason: str) -> str:
        """Create dispute for order"""
        dispute_data = {
            "order_id": order_id,
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "reason": reason,
            "status": "open",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.disputes.insert_one(dispute_data)
        
        # Update order status
        from bson.objectid import ObjectId
        await self.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": "disputed"}}
        )
        
        return str(result.inserted_id)
    
    async def get_open_disputes(self) -> List[Dict[str, Any]]:
        """Get all open disputes for admins"""
        cursor = self.disputes.find({
            "status": "open"
        }).sort("created_at", ASCENDING)
        return await cursor.to_list(length=None)
    
    async def resolve_dispute(self, dispute_id: str, resolution: str,
                            refund_buyer: bool = False) -> bool:
        """Resolve dispute"""
        from bson.objectid import ObjectId
        result = await self.disputes.update_one(
            {"_id": ObjectId(dispute_id)},
            {
                "$set": {
                    "status": "resolved",
                    "resolution": resolution,
                    "refund_buyer": refund_buyer,
                    "resolved_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    # Payout Methods
    async def create_payout_request(self, seller_id: int, amount: float) -> str:
        """Create payout request"""
        payout_data = {
            "seller_id": seller_id,
            "amount": amount,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await self.payouts.insert_one(payout_data)
        return str(result.inserted_id)
    
    async def get_pending_payouts(self) -> List[Dict[str, Any]]:
        """Get pending payout requests"""
        cursor = self.payouts.find({
            "status": "pending"
        }).sort("created_at", ASCENDING)
        return await cursor.to_list(length=None)
    
    async def approve_payout(self, payout_id: str) -> bool:
        """Approve payout request"""
        from bson.objectid import ObjectId
        result = await self.payouts.update_one(
            {"_id": ObjectId(payout_id)},
            {
                "$set": {
                    "status": "approved",
                    "approved_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    # Statistics Methods
    async def get_seller_stats(self, seller_id: int) -> Dict[str, Any]:
        """Get seller statistics"""
        # Active coupons
        active_coupons = await self.coupons.count_documents({
            "seller_id": seller_id,
            "status": "active"
        })
        
        # Sales this month
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_sales = await self.orders.count_documents({
            "seller_id": seller_id,
            "created_at": {"$gte": month_start}
        })
        
        # Average rating
        avg_rating = await self.get_seller_average_rating(seller_id)
        
        # Dispute percentage
        total_orders = await self.orders.count_documents({"seller_id": seller_id})
        total_disputes = await self.disputes.count_documents({"seller_id": seller_id})
        dispute_pct = (total_disputes / total_orders * 100) if total_orders > 0 else 0
        
        return {
            "active_coupons": active_coupons,
            "monthly_sales": monthly_sales,
            "avg_rating": avg_rating,
            "dispute_percentage": round(dispute_pct, 1),
            "total_orders": total_orders
        }
    
    # Message/Chat Methods
    async def create_message(self, sender_id: int, recipient_id: int, 
                           message_text: str, order_id: Optional[str] = None) -> str:
        """Create message in anonymous chat"""
        message_data = {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message": message_text,
            "order_id": order_id,
            "read": False,
            "created_at": datetime.utcnow()
        }
        result = await self.messages.insert_one(message_data)
        return str(result.inserted_id)
    
    async def get_chat_messages(self, user1_id: int, user2_id: int) -> List[Dict[str, Any]]:
        """Get messages between two users"""
        cursor = self.messages.find({
            "$or": [
                {"sender_id": user1_id, "recipient_id": user2_id},
                {"sender_id": user2_id, "recipient_id": user1_id}
            ]
        }).sort("created_at", ASCENDING)
        return await cursor.to_list(length=None)
    
    async def get_user_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all chats for a user (unique conversations)"""
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"sender_id": user_id},
                        {"recipient_id": user_id}
                    ]
                }
            },
            {
                "$group": {
                    "_id": {
                        "$cond": [
                            {"$eq": ["$sender_id", user_id]},
                            "$recipient_id",
                            "$sender_id"
                        ]
                    },
                    "last_message": {"$last": "$message"},
                    "last_message_time": {"$last": "$created_at"}
                }
            },
            {"$sort": {"last_message_time": DESCENDING}}
        ]
        cursor = self.messages.aggregate(pipeline)
        return await cursor.to_list(length=None)


# Global database instance
db = Database()


async def _ensure_connected() -> None:
    """
    Backwards-compatible connection helper.

    Some parts of the codebase still import the `database` module and expect
    `get_*_collection()` helpers. Ensure the global `db` is connected first.
    """
    if db.client is None or db.db is None:
        await db.connect()


# ---- Backwards-compatible collection helpers (used across services/handlers) ----

async def get_users_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.users


async def get_coupons_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.coupons


async def get_orders_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.orders


async def get_payouts_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.payouts


async def get_disputes_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.disputes


async def get_escrow_transactions_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.escrow_transactions


async def get_escrow_logs_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.escrow_logs


async def get_payment_gateway_transactions_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.payment_gateway_transactions


async def get_saved_cards_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.saved_cards


async def get_payout_transactions_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.payout_transactions


async def get_daily_card_limits_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.daily_card_limits


async def get_seller_analytics_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.seller_analytics


async def get_seller_alert_settings_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.seller_alert_settings


async def get_scheduled_coupons_collection() -> AsyncIOMotorCollection:
    await _ensure_connected()
    return db.scheduled_coupons
