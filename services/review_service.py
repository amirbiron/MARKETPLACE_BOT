"""
שירות ניהול דירוגים וביקורות (Reviews)
"""
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from bson import ObjectId
from database import db
from models import Review
from config import Config
import logging

logger = logging.getLogger(__name__)


class ReviewService:
    """שירות לניהול דירוגים וביקורות"""

    @staticmethod
    async def can_review_seller(buyer_id: int, seller_id: int, order_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        בדיקה האם קונה יכול לדרג מוכר

        Returns:
            Tuple[can_review, error_message]
        """
        try:
            # בדיקה שהקונה והמוכר שונים
            if buyer_id == seller_id:
                return False, "❌ לא ניתן לדרג את עצמך"

            # אם נשלח order_id ספציפי
            if order_id:
                order = await db.orders.find_one({"_id": ObjectId(order_id)})

                if not order:
                    return False, "❌ הזמנה לא נמצאה"

                if order["buyer_id"] != buyer_id:
                    return False, "❌ זו לא ההזמנה שלך"

                if order["seller_id"] != seller_id:
                    return False, "❌ המוכר לא תואם להזמנה"

                if order["status"] not in ["completed", "confirmed"]:
                    return False, "❌ ניתן לדרג רק הזמנות שהושלמו"

                # בדיקה אם כבר דורג בגלל הזמנה זו
                existing = await db.reviews.find_one({
                    "buyer_id": buyer_id,
                    "order_id": ObjectId(order_id)
                })

                if existing:
                    return False, "❌ כבר דירגת הזמנה זו"

            else:
                # בדיקה כללית - האם יש הזמנה שהושלמה מהמוכר
                order = await db.orders.find_one({
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]}
                })

                if not order:
                    return False, "❌ לא ביצעת רכישה מהמוכר הזה"

                # בדיקה אם כבר דירג את המוכר (ביקורת אחת למוכר)
                existing = await db.reviews.find_one({
                    "buyer_id": buyer_id,
                    "seller_id": seller_id
                })

                if existing:
                    return False, "❌ כבר דירגת את המוכר הזה"

            return True, None

        except Exception as e:
            logger.error(f"Error checking review eligibility: {e}")
            return False, f"❌ שגיאה בבדיקת הזכאות לדירוג: {str(e)}"

    @staticmethod
    async def create_review(
        buyer_id: int,
        seller_id: int,
        order_id: str,
        rating: int,
        comment: Optional[str] = None
    ) -> Optional[str]:
        """
        יצירת ביקורת למוכר

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            # ולידציה של דירוג
            if rating < 1 or rating > 5:
                return "❌ דירוג חייב להיות בין 1 ל-5"

            # ולידציה של הערה
            if comment:
                comment = comment.strip()
                if len(comment) > 15:
                    comment = comment[:15]
                if len(comment) < 3:
                    comment = None

            # בדיקת זכאות
            can_review, error = await ReviewService.can_review_seller(buyer_id, seller_id, order_id)
            if not can_review:
                return error

            # יצירת הביקורת
            review = Review(
                buyer_id=buyer_id,
                seller_id=seller_id,
                order_id=ObjectId(order_id),
                rating=rating,
                comment=comment
            )

            result = await db.reviews.insert_one(review.to_dict())

            # עדכון דירוג ממוצע של המוכר
            await ReviewService._update_seller_rating(seller_id)

            # עדכון שההזמנה דורגה
            await db.orders.update_one(
                {"_id": ObjectId(order_id)},
                {"$set": {"reviewed": True, "reviewed_at": datetime.utcnow()}}
            )

            logger.info(f"Review created: {result.inserted_id} for seller {seller_id}")
            return None

        except Exception as e:
            logger.error(f"Error creating review: {e}")
            return f"❌ שגיאה ביצירת ביקורת: {str(e)}"

    @staticmethod
    async def _update_seller_rating(seller_id: int):
        """עדכון דירוג ממוצע של מוכר (פונקציה פנימית)"""
        try:
            # חישוב ממוצע דירוג
            pipeline = [
                {"$match": {"seller_id": seller_id}},
                {"$group": {
                    "_id": None,
                    "avg_rating": {"$avg": "$rating"},
                    "count": {"$sum": 1}
                }}
            ]

            cursor = db.reviews.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if results:
                avg_rating = round(results[0]["avg_rating"], 2)
                count = results[0]["count"]

                # עדכון במשתמש
                await db.users.update_one(
                    {"user_id": seller_id},
                    {
                        "$set": {
                            "rating_average": avg_rating,
                            "rating_count": count
                        }
                    }
                )

                logger.info(f"Updated seller {seller_id} rating: {avg_rating} ({count} reviews)")

        except Exception as e:
            logger.error(f"Error updating seller rating: {e}")

    @staticmethod
    async def get_seller_reviews(seller_id: int, page: int = 0) -> List[Dict[str, Any]]:
        """קבלת ביקורות של מוכר עם פגינציה"""
        try:
            skip = page * Config.REVIEWS_PER_PAGE

            cursor = db.reviews.find({
                "seller_id": seller_id
            }).sort("created_at", -1).skip(skip).limit(Config.REVIEWS_PER_PAGE)

            reviews = await cursor.to_list(length=None)

            # הוספת שם המשתמש לכל ביקורת (אופציונלי)
            for review in reviews:
                buyer = await db.users.find_one({"user_id": review["buyer_id"]})
                if buyer:
                    review["buyer_name"] = buyer.get("first_name", "קונה")
                else:
                    review["buyer_name"] = "קונה"

            return reviews

        except Exception as e:
            logger.error(f"Error getting seller reviews: {e}")
            return []

    @staticmethod
    async def get_seller_rating_stats(seller_id: int) -> Dict[str, Any]:
        """קבלת סטטיסטיקות דירוג של מוכר"""
        try:
            # דירוג ממוצע וכמות ביקורות
            user = await db.users.find_one({"user_id": seller_id})

            if not user:
                return {
                    "average": 0.0,
                    "count": 0,
                    "stars_distribution": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
                }

            avg_rating = user.get("rating_average", 0.0)
            count = user.get("rating_count", 0)

            # התפלגות כוכבים
            distribution = {}
            for stars in range(1, 6):
                star_count = await db.reviews.count_documents({
                    "seller_id": seller_id,
                    "rating": stars
                })
                distribution[stars] = star_count

            return {
                "average": avg_rating,
                "count": count,
                "stars_distribution": distribution
            }

        except Exception as e:
            logger.error(f"Error getting seller rating stats: {e}")
            return {
                "average": 0.0,
                "count": 0,
                "stars_distribution": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
            }

    @staticmethod
    async def get_review_by_order(order_id: str) -> Optional[Dict[str, Any]]:
        """קבלת ביקורת לפי הזמנה"""
        try:
            review = await db.reviews.find_one({"order_id": ObjectId(order_id)})
            return review

        except Exception as e:
            logger.error(f"Error getting review by order: {e}")
            return None

    @staticmethod
    async def delete_review(review_id: str, user_id: int, is_admin: bool = False) -> Optional[str]:
        """
        מחיקת ביקורת

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            review = await db.reviews.find_one({"_id": ObjectId(review_id)})

            if not review:
                return "❌ ביקורת לא נמצאה"

            # בדיקת הרשאות
            if not is_admin and review["buyer_id"] != user_id:
                return "❌ אין לך הרשאה למחוק ביקורת זו"

            seller_id = review["seller_id"]

            # מחיקת הביקורת
            await db.reviews.delete_one({"_id": ObjectId(review_id)})

            # עדכון דירוג המוכר
            await ReviewService._update_seller_rating(seller_id)

            # עדכון שההזמנה לא דורגה
            if review.get("order_id"):
                await db.orders.update_one(
                    {"_id": review["order_id"]},
                    {"$set": {"reviewed": False}, "$unset": {"reviewed_at": ""}}
                )

            logger.info(f"Review {review_id} deleted by {'admin' if is_admin else user_id}")
            return None

        except Exception as e:
            logger.error(f"Error deleting review: {e}")
            return f"❌ שגיאה במחיקת ביקורת: {str(e)}"

    @staticmethod
    async def get_buyer_reviews(buyer_id: int) -> List[Dict[str, Any]]:
        """קבלת כל הביקורות שכתב קונה"""
        try:
            cursor = db.reviews.find({
                "buyer_id": buyer_id
            }).sort("created_at", -1)

            reviews = await cursor.to_list(length=None)

            # הוספת מידע על המוכרים
            for review in reviews:
                seller = await db.users.find_one({"user_id": review["seller_id"]})
                if seller:
                    review["seller_name"] = seller.get("business_name", "מוכר")
                else:
                    review["seller_name"] = "מוכר"

            return reviews

        except Exception as e:
            logger.error(f"Error getting buyer reviews: {e}")
            return []

    @staticmethod
    async def format_rating_display(rating: float, count: int) -> str:
        """
        פורמט תצוגת דירוג

        Returns:
            מחרוזת מעוצבת של דירוג, לדוגמה: "⭐⭐⭐⭐⭐ 4.8 (23)"
        """
        if count == 0:
            return "⭐ ללא דירוג"

        # כוכבים מלאים ריקים
        full_stars = int(rating)
        empty_stars = 5 - full_stars

        stars = "⭐" * full_stars + "☆" * empty_stars

        return f"{stars} {rating:.1f} ({count})"

    @staticmethod
    async def get_top_rated_sellers(limit: int = 10) -> List[Dict[str, Any]]:
        """קבלת המוכרים בעלי הדירוג הגבוה ביותר"""
        try:
            cursor = db.users.find({
                "role": {"$in": ["seller_verified", "seller_unverified"]},
                "rating_count": {"$gte": 3}  # לפחות 3 דירוגים
            }).sort([
                ("rating_average", -1),
                ("rating_count", -1)
            ]).limit(limit)

            sellers = await cursor.to_list(length=None)

            return sellers

        except Exception as e:
            logger.error(f"Error getting top rated sellers: {e}")
            return []

    @staticmethod
    async def report_review(review_id: str, reporter_id: int, reason: str) -> Optional[str]:
        """
        דיווח על ביקורת פוגענית

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            review = await db.reviews.find_one({"_id": ObjectId(review_id)})

            if not review:
                return "❌ ביקורת לא נמצאה"

            # שמירת דיווח
            await db.review_reports.insert_one({
                "review_id": ObjectId(review_id),
                "reporter_id": reporter_id,
                "reason": reason,
                "status": "pending",
                "created_at": datetime.utcnow()
            })

            # סימון הביקורת כמדווחת
            await db.reviews.update_one(
                {"_id": ObjectId(review_id)},
                {"$set": {"reported": True, "report_count": review.get("report_count", 0) + 1}}
            )

            logger.info(f"Review {review_id} reported by {reporter_id}")
            return None

        except Exception as e:
            logger.error(f"Error reporting review: {e}")
            return f"❌ שגיאה בדיווח על ביקורת: {str(e)}"

    @staticmethod
    async def get_reported_reviews() -> List[Dict[str, Any]]:
        """קבלת ביקורות מדווחות (לאדמין)"""
        try:
            cursor = db.review_reports.find({
                "status": "pending"
            }).sort("created_at", 1)

            reports = await cursor.to_list(length=None)

            # הוספת מידע על הביקורות
            for report in reports:
                review = await db.reviews.find_one({"_id": report["review_id"]})
                if review:
                    report["review"] = review

            return reports

        except Exception as e:
            logger.error(f"Error getting reported reviews: {e}")
            return []
