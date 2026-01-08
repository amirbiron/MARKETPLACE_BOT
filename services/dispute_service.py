"""
שירות ניהול מחלוקות (Disputes)
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId
from database import db
from models import Dispute, DisputeStatus
from config import Config
import logging

logger = logging.getLogger(__name__)


class DisputeService:
    """שירות לניהול מחלוקות"""

    @staticmethod
    async def can_open_dispute(buyer_id: int, order_id: str) -> Tuple[bool, Optional[str]]:
        """
        בדיקה האם ניתן לפתוח מחלוקת

        Returns:
            Tuple[can_open, error_message]
        """
        try:
            order = await db.orders.find_one({"_id": ObjectId(order_id)})

            if not order:
                return False, "❌ הזמנה לא נמצאה"

            if order["buyer_id"] != buyer_id:
                return False, "❌ זו לא ההזמנה שלך"

            if order["status"] == "disputed":
                return False, "❌ כבר קיימת מחלוקת על הזמנה זו"

            if order["status"] == "refunded":
                return False, "❌ ההזמנה כבר זוכתה"

            # בדיקת חלון זמן לדיווח
            if "dispute_deadline" in order:
                if datetime.utcnow() > order["dispute_deadline"]:
                    return False, "❌ חלון הזמן לדיווח על בעיה עבר"

            return True, None

        except Exception as e:
            logger.error(f"Error checking dispute eligibility: {e}")
            return False, f"❌ שגיאה בבדיקה: {str(e)}"

    @staticmethod
    async def open_dispute(buyer_id: int, order_id: str, reason: str) -> Optional[str]:
        """
        פתיחת מחלוקת

        Returns:
            dispute_id או הודעת שגיאה
        """
        try:
            # בדיקת זכאות
            can_open, error = await DisputeService.can_open_dispute(buyer_id, order_id)
            if not can_open:
                return error

            order = await db.orders.find_one({"_id": ObjectId(order_id)})

            # יצירת מחלוקת
            dispute = Dispute(
                order_id=ObjectId(order_id),
                buyer_id=buyer_id,
                seller_id=order["seller_id"],
                reason=reason
            )

            result = await db.disputes.insert_one(dispute.to_dict())

            # עדכון סטטוס הזמנה
            await db.orders.update_one(
                {"_id": ObjectId(order_id)},
                {
                    "$set": {
                        "status": "disputed",
                        "disputed_at": datetime.utcnow()
                    }
                }
            )

            # התראה למוכר
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=order["seller_id"],
                title="⚠️ מחלוקת נפתחה",
                message=f"נפתחה מחלוקת על אחת מההזמנות שלך",
                notification_type="dispute_opened",
                data={"dispute_id": str(result.inserted_id)}
            )

            logger.info(f"Dispute created: {result.inserted_id} for order {order_id}")
            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error opening dispute: {e}")
            return f"❌ שגיאה בפתיחת מחלוקת: {str(e)}"

    @staticmethod
    async def add_dispute_message(dispute_id: str, sender_id: int, message: str) -> Optional[str]:
        """
        הוספת הודעה למחלוקת

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            dispute = await db.disputes.find_one({"_id": ObjectId(dispute_id)})

            if not dispute:
                return "❌ מחלוקת לא נמצאה"

            # בדיקה שהשולח קשור למחלוקת
            if sender_id not in [dispute["buyer_id"], dispute["seller_id"]]:
                # בדיקה אם הוא אדמין
                user = await db.users.find_one({"user_id": sender_id})
                if not user or user.get("role") != "admin":
                    return "❌ אין לך הרשאה למחלוקת זו"

            # שמירת ההודעה
            await db.dispute_messages.insert_one({
                "dispute_id": ObjectId(dispute_id),
                "sender_id": sender_id,
                "message": message,
                "created_at": datetime.utcnow()
            })

            # עדכון זמן פעילות אחרונה
            await db.disputes.update_one(
                {"_id": ObjectId(dispute_id)},
                {"$set": {"last_activity": datetime.utcnow()}}
            )

            logger.info(f"Message added to dispute {dispute_id} by {sender_id}")
            return None

        except Exception as e:
            logger.error(f"Error adding dispute message: {e}")
            return f"❌ שגיאה בהוספת הודעה: {str(e)}"

    @staticmethod
    async def get_dispute_messages(dispute_id: str) -> List[Dict[str, Any]]:
        """קבלת הודעות מחלוקת"""
        try:
            cursor = db.dispute_messages.find({
                "dispute_id": ObjectId(dispute_id)
            }).sort("created_at", 1)

            messages = await cursor.to_list(length=None)

            # הוספת שמות משתמשים
            for msg in messages:
                user = await db.users.find_one({"user_id": msg["sender_id"]})
                if user:
                    msg["sender_name"] = user.get("first_name") or user.get("business_name", "משתמש")
                else:
                    msg["sender_name"] = "משתמש"

            return messages

        except Exception as e:
            logger.error(f"Error getting dispute messages: {e}")
            return []

    @staticmethod
    async def resolve_dispute(
        dispute_id: str,
        admin_id: int,
        resolution: str,
        refund_buyer: bool = False,
        refund_amount: Optional[float] = None
    ) -> Optional[str]:
        """
        פתרון מחלוקת על ידי אדמין

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            dispute = await db.disputes.find_one({"_id": ObjectId(dispute_id)})

            if not dispute:
                return "❌ מחלוקת לא נמצאה"

            if dispute["status"] != "open":
                return "❌ המחלוקת כבר נפתרה"

            order = await db.orders.find_one({"_id": dispute["order_id"]})

            if not order:
                return "❌ הזמנה לא נמצאה"

            # קביעת סטטוס
            new_status = DisputeStatus.RESOLVED_REFUND if refund_buyer else DisputeStatus.RESOLVED_NO_REFUND

            # עדכון מחלוקת
            await db.disputes.update_one(
                {"_id": ObjectId(dispute_id)},
                {
                    "$set": {
                        "status": new_status.value,
                        "resolution": resolution,
                        "resolved_at": datetime.utcnow(),
                        "resolved_by": admin_id
                    }
                }
            )

            # אם החלטנו להחזיר כסף
            if refund_buyer:
                amount = refund_amount if refund_amount else order["price_paid"]

                # החזרת כסף לקונה
                await db.users.update_one(
                    {"user_id": dispute["buyer_id"]},
                    {"$inc": {"balance": amount}}
                )

                # ניכוי מהמוכר
                await db.users.update_one(
                    {"user_id": dispute["seller_id"]},
                    {"$inc": {"balance": -amount}}
                )

                # עדכון סטטוס הזמנה
                await db.orders.update_one(
                    {"_id": dispute["order_id"]},
                    {"$set": {"status": "refunded", "refunded_at": datetime.utcnow()}}
                )

                # רישום טרנזקציות
                await db.transactions.insert_one({
                    "user_id": dispute["buyer_id"],
                    "type": "refund",
                    "amount": amount,
                    "description": f"החזר כספי - מחלוקת",
                    "reference_id": str(dispute["order_id"]),
                    "created_at": datetime.utcnow()
                })

                await db.transactions.insert_one({
                    "user_id": dispute["seller_id"],
                    "type": "chargeback",
                    "amount": -amount,
                    "description": f"ניכוי - מחלוקת",
                    "reference_id": str(dispute["order_id"]),
                    "created_at": datetime.utcnow()
                })

            else:
                # סגירת המחלוקת ללא החזר
                await db.orders.update_one(
                    {"_id": dispute["order_id"]},
                    {"$set": {"status": "completed"}}
                )

            # התראות
            from services.notification_service import NotificationService

            await NotificationService.notify_dispute_resolved(
                user_id=dispute["buyer_id"],
                order_id=str(dispute["order_id"]),
                resolution=resolution
            )

            await NotificationService.notify_dispute_resolved(
                user_id=dispute["seller_id"],
                order_id=str(dispute["order_id"]),
                resolution=resolution
            )

            logger.info(f"Dispute {dispute_id} resolved by admin {admin_id}, refund: {refund_buyer}")
            return None

        except Exception as e:
            logger.error(f"Error resolving dispute: {e}")
            return f"❌ שגיאה בפתרון מחלוקת: {str(e)}"

    @staticmethod
    async def get_open_disputes() -> List[Dict[str, Any]]:
        """קבלת מחלוקות פתוחות (לאדמין)"""
        try:
            cursor = db.disputes.find({
                "status": "open"
            }).sort("created_at", 1)

            disputes = await cursor.to_list(length=None)

            # הוספת מידע על הזמנות ומשתמשים
            for dispute in disputes:
                order = await db.orders.find_one({"_id": dispute["order_id"]})
                if order:
                    dispute["order"] = order

                    # קופון
                    coupon = await db.coupons.find_one({"_id": ObjectId(order["coupon_id"])})
                    if coupon:
                        dispute["coupon"] = coupon

                buyer = await db.users.find_one({"user_id": dispute["buyer_id"]})
                if buyer:
                    dispute["buyer_name"] = buyer.get("first_name", "קונה")

                seller = await db.users.find_one({"user_id": dispute["seller_id"]})
                if seller:
                    dispute["seller_name"] = seller.get("business_name", "מוכר")

            return disputes

        except Exception as e:
            logger.error(f"Error getting open disputes: {e}")
            return []

    @staticmethod
    async def get_user_disputes(user_id: int, as_buyer: bool = True) -> List[Dict[str, Any]]:
        """קבלת מחלוקות של משתמש"""
        try:
            field = "buyer_id" if as_buyer else "seller_id"

            cursor = db.disputes.find({
                field: user_id
            }).sort("created_at", -1)

            disputes = await cursor.to_list(length=None)

            # הוספת מידע על הזמנות
            for dispute in disputes:
                order = await db.orders.find_one({"_id": dispute["order_id"]})
                if order:
                    dispute["order"] = order

                    coupon = await db.coupons.find_one({"_id": ObjectId(order["coupon_id"])})
                    if coupon:
                        dispute["coupon"] = coupon

            return disputes

        except Exception as e:
            logger.error(f"Error getting user disputes: {e}")
            return []

    @staticmethod
    async def get_dispute_by_id(dispute_id: str) -> Optional[Dict[str, Any]]:
        """קבלת מחלוקת לפי ID"""
        try:
            dispute = await db.disputes.find_one({"_id": ObjectId(dispute_id)})

            if dispute:
                # הוספת מידע על ההזמנה
                order = await db.orders.find_one({"_id": dispute["order_id"]})
                if order:
                    dispute["order"] = order

                    coupon = await db.coupons.find_one({"_id": ObjectId(order["coupon_id"])})
                    if coupon:
                        dispute["coupon"] = coupon

                # מידע על קונה ומוכר
                buyer = await db.users.find_one({"user_id": dispute["buyer_id"]})
                if buyer:
                    dispute["buyer_name"] = buyer.get("first_name", "קונה")

                seller = await db.users.find_one({"user_id": dispute["seller_id"]})
                if seller:
                    dispute["seller_name"] = seller.get("business_name", "מוכר")

            return dispute

        except Exception as e:
            logger.error(f"Error getting dispute: {e}")
            return None

    @staticmethod
    async def escalate_dispute(dispute_id: str) -> Optional[str]:
        """
        העלאת מחלוקת לאדמין

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            dispute = await db.disputes.find_one({"_id": ObjectId(dispute_id)})

            if not dispute:
                return "❌ מחלוקת לא נמצאה"

            await db.disputes.update_one(
                {"_id": ObjectId(dispute_id)},
                {
                    "$set": {
                        "status": "in_progress",
                        "escalated": True,
                        "escalated_at": datetime.utcnow()
                    }
                }
            )

            logger.info(f"Dispute {dispute_id} escalated to admin")
            return None

        except Exception as e:
            logger.error(f"Error escalating dispute: {e}")
            return f"❌ שגיאה בהעלאת מחלוקת: {str(e)}"

    @staticmethod
    async def get_dispute_stats() -> Dict[str, Any]:
        """סטטיסטיקות מחלוקות (לאדמין)"""
        try:
            total = await db.disputes.count_documents({})
            open_count = await db.disputes.count_documents({"status": "open"})
            resolved_refund = await db.disputes.count_documents({"status": "resolved_refund"})
            resolved_no_refund = await db.disputes.count_documents({"status": "resolved_no_refund"})

            # אחוז החזרים
            total_resolved = resolved_refund + resolved_no_refund
            refund_rate = (resolved_refund / total_resolved * 100) if total_resolved > 0 else 0

            return {
                "total": total,
                "open": open_count,
                "resolved_refund": resolved_refund,
                "resolved_no_refund": resolved_no_refund,
                "refund_rate": round(refund_rate, 1)
            }

        except Exception as e:
            logger.error(f"Error getting dispute stats: {e}")
            return {
                "total": 0,
                "open": 0,
                "resolved_refund": 0,
                "resolved_no_refund": 0,
                "refund_rate": 0
            }
