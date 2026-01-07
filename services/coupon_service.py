"""
שירות ניהול קופונים
"""
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import database
from models import Coupon, CouponStatus
from config import Config
import logging

logger = logging.getLogger(__name__)


class CouponService:
    """שירות לניהול קופונים"""
    
    # קטגוריות זמינות
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
    
    @staticmethod
    async def create_coupon(
        seller_id: int,
        title: str,
        category: str,
        original_price: float,
        sale_price: float,
        description: Optional[str] = None,
        digital_code: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ) -> Optional[Coupon]:
        """יצירת קופון חדש"""
        coupons = await database.get_coupons_collection()
        
        # בדיקת הגבלה יומית למוכרים לא מאומתים
        from services.user_service import UserService
        is_verified = await UserService.is_verified_seller(seller_id)
        
        if not is_verified:
            # ספירת קופונים שנוצרו היום
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await coupons.count_documents({
                "seller_id": seller_id,
                "created_at": {"$gte": today_start}
            })
            
            if today_count >= Config.DAILY_COUPON_LIMIT_UNVERIFIED:
                logger.warning(f"Seller {seller_id} reached daily coupon limit ({today_count})")
                return None
        
        coupon = Coupon(
            seller_id=seller_id,
            title=title,
            category=category,
            original_price=original_price,
            sale_price=sale_price,
            description=description,
            digital_code=digital_code,
            expires_at=expires_at
        )
        
        result = await coupons.insert_one(coupon.to_dict())
        coupon._id = result.inserted_id
        
        logger.info(f"Created coupon {coupon._id} by seller {seller_id}: {title}")
        return coupon
    
    @staticmethod
    async def get_coupon(coupon_id: ObjectId) -> Optional[Coupon]:
        """קבלת קופון לפי ID"""
        coupons = await database.get_coupons_collection()
        coupon_data = await coupons.find_one({"_id": coupon_id})
        
        if coupon_data:
            return Coupon.from_dict(coupon_data)
        return None
    
    @staticmethod
    async def get_coupons_by_category(
        category: str,
        page: int = 0,
        limit: int = Config.ITEMS_PER_PAGE
    ) -> Tuple[List[Coupon], int]:
        """קבלת קופונים לפי קטגוריה עם פגינציה"""
        coupons = await database.get_coupons_collection()
        
        query = {
            "category": category,
            "status": CouponStatus.ACTIVE.value
        }
        
        # ספירת סה"כ
        total = await coupons.count_documents(query)
        
        # קבלת קופונים עם פגינציה
        cursor = coupons.find(query).sort("created_at", -1).skip(page * limit).limit(limit)
        coupon_list = []
        
        async for coupon_data in cursor:
            coupon_list.append(Coupon.from_dict(coupon_data))
        
        return coupon_list, total
    
    @staticmethod
    async def search_coupons(
        query: str,
        page: int = 0,
        limit: int = Config.ITEMS_PER_PAGE
    ) -> Tuple[List[Coupon], int]:
        """חיפוש קופונים לפי טקסט חופשי"""
        coupons = await database.get_coupons_collection()
        
        search_query = {
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"category": {"$regex": query, "$options": "i"}}
            ],
            "status": CouponStatus.ACTIVE.value
        }
        
        total = await coupons.count_documents(search_query)
        
        cursor = coupons.find(search_query).sort("created_at", -1).skip(page * limit).limit(limit)
        coupon_list = []
        
        async for coupon_data in cursor:
            coupon_list.append(Coupon.from_dict(coupon_data))
        
        return coupon_list, total
    
    @staticmethod
    async def get_seller_coupons(
        seller_id: int,
        status: Optional[CouponStatus] = None
    ) -> List[Coupon]:
        """קבלת כל הקופונים של מוכר"""
        coupons = await database.get_coupons_collection()
        
        query = {"seller_id": seller_id}
        if status:
            query["status"] = status.value
        
        cursor = coupons.find(query).sort("created_at", -1)
        coupon_list = []
        
        async for coupon_data in cursor:
            coupon_list.append(Coupon.from_dict(coupon_data))
        
        return coupon_list
    
    @staticmethod
    async def mark_as_sold(coupon_id: ObjectId) -> bool:
        """סימון קופון כנמכר"""
        coupons = await database.get_coupons_collection()
        
        result = await coupons.update_one(
            {"_id": coupon_id},
            {"$set": {"status": CouponStatus.SOLD.value}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Marked coupon {coupon_id} as sold")
            return True
        return False
    
    @staticmethod
    async def delete_coupon(coupon_id: ObjectId) -> bool:
        """מחיקת קופון (סימון כמחוק)"""
        coupons = await database.get_coupons_collection()
        
        result = await coupons.update_one(
            {"_id": coupon_id},
            {"$set": {"status": CouponStatus.DELETED.value}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Deleted coupon {coupon_id}")
            return True
        return False
    
    @staticmethod
    async def get_sold_coupons_history(
        page: int = 0,
        limit: int = Config.ITEMS_PER_PAGE
    ) -> Tuple[List[dict], int]:
        """קבלת היסטוריית קופונים שנמכרו"""
        orders = await database.get_orders_collection()
        coupons = await database.get_coupons_collection()
        users = await database.get_users_collection()
        
        # אגרגציה לקבלת נתונים מלאים
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$sort": {"created_at": -1}},
            {"$skip": page * limit},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "coupons",
                    "localField": "coupon_id",
                    "foreignField": "_id",
                    "as": "coupon_info"
                }
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "buyer_id",
                    "foreignField": "user_id",
                    "as": "buyer_info"
                }
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "seller_id",
                    "foreignField": "user_id",
                    "as": "seller_info"
                }
            },
            {"$unwind": "$coupon_info"},
            {"$unwind": "$buyer_info"},
            {"$unwind": "$seller_info"},
        ]
        
        cursor = orders.aggregate(pipeline)
        history = []
        
        async for item in cursor:
            history.append({
                "buyer_name": item["buyer_info"].get("first_name", "לקוח"),
                "seller_name": item["seller_info"].get("business_name", "מוכר"),
                "coupon_title": item["coupon_info"].get("title", ""),
                "category": item["coupon_info"].get("category", ""),
                "original_price": item["coupon_info"].get("original_price", 0),
                "sale_price": item.get("price_paid", 0),
                "date": item.get("created_at", datetime.utcnow())
            })
        
        # ספירת סה"כ
        total = await orders.count_documents({"status": "completed"})
        
        return history, total
    
    @staticmethod
    async def get_hot_coupons(limit: int = 10) -> List[Coupon]:
        """קבלת הקופונים הנמכרים ביותר"""
        orders = await database.get_orders_collection()
        coupons = await database.get_coupons_collection()
        
        # אגרגציה למציאת הקופונים הפופולריים
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$group": {"_id": "$coupon_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        cursor = orders.aggregate(pipeline)
        popular_ids = []
        
        async for item in cursor:
            popular_ids.append(item["_id"])
        
        # קבלת פרטי הקופונים
        hot_coupons = []
        for coupon_id in popular_ids:
            coupon_data = await coupons.find_one({"_id": coupon_id, "status": CouponStatus.ACTIVE.value})
            if coupon_data:
                hot_coupons.append(Coupon.from_dict(coupon_data))
        
        return hot_coupons
    
    @staticmethod
    async def advanced_search(
        search_text: Optional[str] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,  # אחוז הנחה מינימלי
        min_seller_rating: Optional[float] = None,
        page: int = 0,
        limit: int = Config.ITEMS_PER_PAGE
    ) -> Tuple[List[Coupon], int]:
        """חיפוש מתקדם עם פילטרים"""
        coupons = await database.get_coupons_collection()
        users = await database.get_users_collection()

        # בניית query
        query = {"status": CouponStatus.ACTIVE.value}

        # חיפוש טקסט חופשי
        if search_text:
            query["$or"] = [
                {"title": {"$regex": search_text, "$options": "i"}},
                {"description": {"$regex": search_text, "$options": "i"}}
            ]

        # פילטר קטגוריה
        if category:
            query["category"] = category

        # פילטר טווח מחיר
        if min_price is not None:
            query["sale_price"] = query.get("sale_price", {})
            query["sale_price"]["$gte"] = min_price

        if max_price is not None:
            query["sale_price"] = query.get("sale_price", {})
            query["sale_price"]["$lte"] = max_price

        # פילטר אחוז הנחה
        if min_discount is not None:
            # נצטרך לחשב את זה בצד הקליינט או להשתמש באגרגציה
            pass

        # שלב 1: קבלת קופונים
        cursor = coupons.find(query).skip(page * limit).limit(limit)

        results = []
        async for coupon_data in cursor:
            coupon = Coupon.from_dict(coupon_data)

            # פילטר אחוז הנחה
            if min_discount is not None:
                discount_pct = ((coupon.original_price - coupon.sale_price) / coupon.original_price) * 100
                if discount_pct < min_discount:
                    continue

            # פילטר דירוג מוכר
            if min_seller_rating is not None:
                seller = await users.find_one({"user_id": coupon.seller_id})
                if not seller or seller.get("rating_average", 0) < min_seller_rating:
                    continue

            results.append(coupon)

        # ספירת סה"כ תוצאות
        total = await coupons.count_documents(query)

        return results, total

    @staticmethod
    async def check_expiration() -> int:
        """בדיקה וסימון קופונים שפג תוקפם"""
        coupons = await database.get_coupons_collection()
        now = datetime.utcnow()

        result = await coupons.update_many(
            {
                "status": CouponStatus.ACTIVE.value,
                "expires_at": {"$lte": now}
            },
            {"$set": {"status": CouponStatus.EXPIRED.value}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Marked {result.modified_count} coupons as expired")
        
        return result.modified_count
