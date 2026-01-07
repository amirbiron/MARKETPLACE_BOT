"""
שירות ניהול מועדפים (Favorites)
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class FavoritesService:
    """שירות לניהול מועדפים"""

    @staticmethod
    async def add_favorite(user_id: int, coupon_id: str) -> Optional[str]:
        """
        הוספת קופון למועדפים

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            # בדיקה שהקופון קיים
            coupon = await db.coupons.find_one({"_id": ObjectId(coupon_id)})

            if not coupon:
                return "❌ קופון לא נמצא"

            # בדיקה שלא כבר במועדפים
            existing = await db.favorites.find_one({
                "user_id": user_id,
                "coupon_id": ObjectId(coupon_id)
            })

            if existing:
                return "❌ הקופון כבר במועדפים"

            # הוספה
            await db.favorites.insert_one({
                "user_id": user_id,
                "coupon_id": ObjectId(coupon_id),
                "created_at": datetime.utcnow(),
                "last_price": coupon.get("sale_price", 0),
                "notified_price_drop": False
            })

            logger.info(f"Coupon {coupon_id} added to favorites by {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            return f"❌ שגיאה בהוספה למועדפים: {str(e)}"

    @staticmethod
    async def remove_favorite(user_id: int, coupon_id: str) -> Optional[str]:
        """
        הסרת קופון ממועדפים

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            result = await db.favorites.delete_one({
                "user_id": user_id,
                "coupon_id": ObjectId(coupon_id)
            })

            if result.deleted_count == 0:
                return "❌ הקופון לא נמצא במועדפים"

            logger.info(f"Coupon {coupon_id} removed from favorites by {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error removing favorite: {e}")
            return f"❌ שגיאה בהסרה ממועדפים: {str(e)}"

    @staticmethod
    async def is_favorite(user_id: int, coupon_id: str) -> bool:
        """בדיקה האם קופון במועדפים"""
        try:
            favorite = await db.favorites.find_one({
                "user_id": user_id,
                "coupon_id": ObjectId(coupon_id)
            })

            return favorite is not None

        except Exception as e:
            logger.error(f"Error checking favorite: {e}")
            return False

    @staticmethod
    async def get_user_favorites(user_id: int, page: int = 0) -> List[Dict[str, Any]]:
        """קבלת מועדפים של משתמש"""
        try:
            skip = page * Config.ITEMS_PER_PAGE

            cursor = db.favorites.find({
                "user_id": user_id
            }).sort("created_at", -1).skip(skip).limit(Config.ITEMS_PER_PAGE)

            favorites = await cursor.to_list(length=None)

            # הוספת מידע על הקופונים
            result = []
            for fav in favorites:
                coupon = await db.coupons.find_one({"_id": fav["coupon_id"]})

                if coupon:
                    # בדיקה אם היה שינוי מחיר
                    last_price = fav.get("last_price", 0)
                    current_price = coupon.get("sale_price", 0)

                    price_dropped = current_price < last_price

                    result.append({
                        "favorite": fav,
                        "coupon": coupon,
                        "price_dropped": price_dropped,
                        "price_change": last_price - current_price if price_dropped else 0
                    })

            return result

        except Exception as e:
            logger.error(f"Error getting user favorites: {e}")
            return []

    @staticmethod
    async def get_favorites_count(user_id: int) -> int:
        """קבלת מספר המועדפים"""
        try:
            count = await db.favorites.count_documents({"user_id": user_id})
            return count

        except Exception as e:
            logger.error(f"Error getting favorites count: {e}")
            return 0

    @staticmethod
    async def check_price_drops():
        """בדיקת ירידות מחיר במועדפים - לרוץ ב-background"""
        try:
            # קבלת כל המועדפים
            cursor = db.favorites.find({})
            favorites = await cursor.to_list(length=None)

            notified_count = 0

            for fav in favorites:
                # קבלת הקופון הנוכחי
                coupon = await db.coupons.find_one({"_id": fav["coupon_id"]})

                if not coupon or coupon.get("status") != "active":
                    continue

                last_price = fav.get("last_price", 0)
                current_price = coupon.get("sale_price", 0)

                # בדיקה אם המחיר ירד
                if current_price < last_price:
                    # התראה למשתמש
                    from services.notification_service import NotificationService
                    await NotificationService.notify_price_drop(
                        user_id=fav["user_id"],
                        coupon_id=str(fav["coupon_id"]),
                        coupon_title=coupon.get("title", "קופון"),
                        old_price=last_price,
                        new_price=current_price
                    )

                    # עדכון המחיר האחרון
                    await db.favorites.update_one(
                        {"_id": fav["_id"]},
                        {
                            "$set": {
                                "last_price": current_price,
                                "notified_price_drop": True,
                                "last_notified": datetime.utcnow()
                            }
                        }
                    )

                    notified_count += 1

            logger.info(f"Checked price drops, notified {notified_count} users")
            return notified_count

        except Exception as e:
            logger.error(f"Error checking price drops: {e}")
            return 0

    @staticmethod
    async def notify_similar_coupons():
        """התראה על קופונים דומים למועדפים - לרוץ ב-background"""
        try:
            # קבלת קופונים חדשים (24 שעות אחרונות)
            from datetime import timedelta
            recent_time = datetime.utcnow() - timedelta(hours=24)

            recent_coupons = await db.coupons.find({
                "created_at": {"$gte": recent_time},
                "status": "active"
            }).to_list(length=None)

            notified_count = 0

            for coupon in recent_coupons:
                category = coupon.get("category")

                if not category:
                    continue

                # מציאת משתמשים שיש להם מועדפים באותה קטגוריה
                pipeline = [
                    {
                        "$lookup": {
                            "from": "coupons",
                            "localField": "coupon_id",
                            "foreignField": "_id",
                            "as": "coupon"
                        }
                    },
                    {
                        "$match": {
                            "coupon.category": category,
                            "last_notified_similar": {"$not": {"$gte": recent_time}}
                        }
                    },
                    {
                        "$group": {
                            "_id": "$user_id"
                        }
                    }
                ]

                cursor = db.favorites.aggregate(pipeline)
                users = await cursor.to_list(length=None)

                # התראה לכל משתמש
                for user in users:
                    user_id = user["_id"]

                    from services.notification_service import NotificationService
                    await NotificationService.notify_similar_coupon(
                        user_id=user_id,
                        coupon_id=str(coupon["_id"]),
                        coupon_title=coupon.get("title", "קופון"),
                        category=category
                    )

                    # עדכון שהתראה נשלחה
                    await db.favorites.update_many(
                        {"user_id": user_id},
                        {"$set": {"last_notified_similar": datetime.utcnow()}}
                    )

                    notified_count += 1

            logger.info(f"Notified {notified_count} users about similar coupons")
            return notified_count

        except Exception as e:
            logger.error(f"Error notifying similar coupons: {e}")
            return 0

    @staticmethod
    async def cleanup_deleted_coupons():
        """ניקוי מועדפים של קופונים שנמחקו - לרוץ ב-background"""
        try:
            # מציאת כל המועדפים
            cursor = db.favorites.find({})
            favorites = await cursor.to_list(length=None)

            deleted_count = 0

            for fav in favorites:
                # בדיקה אם הקופון קיים
                coupon = await db.coupons.find_one({"_id": fav["coupon_id"]})

                if not coupon or coupon.get("status") in ["deleted", "sold"]:
                    await db.favorites.delete_one({"_id": fav["_id"]})
                    deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} favorites of deleted coupons")
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up favorites: {e}")
            return 0
