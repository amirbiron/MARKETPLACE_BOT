"""
שירות ניהול משיכות כספים (Payouts)
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
from database import db
from models import Payout, PayoutStatus
from config import Config
import logging

logger = logging.getLogger(__name__)


class PayoutService:
    """שירות לניהול משיכות כספים"""

    @staticmethod
    async def can_request_payout(seller_id: int, amount: float) -> Tuple[bool, Optional[str]]:
        """
        בדיקה האם מוכר יכול לבקש משיכה

        Returns:
            Tuple[can_request, error_message]
        """
        try:
            user = await db.users.find_one({"user_id": seller_id})

            if not user:
                return False, "❌ משתמש לא נמצא"

            # בדיקה שהמשתמש הוא מוכר
            if user.get("role") not in ["seller_verified", "seller_unverified"]:
                return False, "❌ רק מוכרים יכולים למשוך כספים"

            # בדיקת סכום מינימלי
            if amount < Config.MIN_PAYOUT_AMOUNT:
                return False, f"❌ סכום מינימלי למשיכה: {Config.MIN_PAYOUT_AMOUNT}₪"

            # בדיקת יתרה
            if user.get("balance", 0) < amount:
                return False, f"❌ אין מספיק יתרה. יתרה נוכחית: {user.get('balance', 0):.2f}₪"

            # בדיקה שאין בקשת משיכה ממתינה
            pending = await db.payouts.find_one({
                "seller_id": seller_id,
                "status": "pending"
            })

            if pending:
                return False, "❌ יש לך בקשת משיכה ממתינה. המתן לאישור"

            # בדיקת הגבלת זמן (לא יותר ממשיכה אחת ב-24 שעות)
            last_payout = await db.payouts.find_one(
                {"seller_id": seller_id},
                sort=[("created_at", -1)]
            )

            if last_payout:
                time_since_last = datetime.utcnow() - last_payout["created_at"]
                if time_since_last < timedelta(hours=24):
                    hours_left = 24 - int(time_since_last.total_seconds() // 3600)
                    return False, f"❌ ניתן למשוך פעם ב-24 שעות. נותרו {hours_left} שעות"

            return True, None

        except Exception as e:
            logger.error(f"Error checking payout eligibility: {e}")
            return False, f"❌ שגיאה בבדיקה: {str(e)}"

    @staticmethod
    async def request_payout(
        seller_id: int,
        amount: float,
        payment_details: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        בקשת משיכת כספים

        Returns:
            payout_id או הודעת שגיאה
        """
        try:
            # בדיקת זכאות
            can_request, error = await PayoutService.can_request_payout(seller_id, amount)
            if not can_request:
                return error

            # חישוב עמלה
            commission = amount * Config.SELLER_COMMISSION_RATE
            net_amount = amount - commission

            # יצירת בקשת משיכה
            payout = Payout(
                seller_id=seller_id,
                amount=amount,
                commission=commission,
                net_amount=net_amount
            )

            payout_dict = payout.to_dict()

            # הוספת פרטי תשלום
            if payment_details:
                payout_dict["payment_details"] = payment_details

            result = await db.payouts.insert_one(payout_dict)

            # הקפאת יתרה
            await db.users.update_one(
                {"user_id": seller_id},
                {
                    "$inc": {
                        "balance": -amount,
                        "frozen_balance": amount
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # התראה למוכר
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=seller_id,
                title="✅ בקשת משיכה נקלטה",
                message=f"בקשתך למשיכת {net_amount:.2f}₪ התקבלה וממתינה לאישור",
                notification_type="payout_requested"
            )

            # התראה לאדמינים
            admins = await db.users.find({"role": "admin"}).to_list(length=None)
            for admin in admins:
                await NotificationService.send_notification(
                    user_id=admin["user_id"],
                    title="💰 בקשת משיכה חדשה",
                    message=f"מוכר מבקש למשוך {net_amount:.2f}₪",
                    notification_type="payout_request_admin",
                    data={"payout_id": str(result.inserted_id)}
                )

            logger.info(f"Payout requested: {result.inserted_id} for {amount}₪ by seller {seller_id}")
            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error requesting payout: {e}")
            return f"❌ שגיאה בבקשת משיכה: {str(e)}"

    @staticmethod
    async def approve_payout(payout_id: str, admin_id: int, notes: Optional[str] = None) -> Optional[str]:
        """
        אישור משיכה על ידי אדמין

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            payout = await db.payouts.find_one({"_id": ObjectId(payout_id)})

            if not payout:
                return "❌ בקשת משיכה לא נמצאה"

            if payout["status"] != "pending":
                return "❌ בקשת המשיכה כבר עובדה"

            # עדכון סטטוס
            await db.payouts.update_one(
                {"_id": ObjectId(payout_id)},
                {
                    "$set": {
                        "status": "approved",
                        "approved_by": admin_id,
                        "approved_at": datetime.utcnow(),
                        "admin_notes": notes
                    }
                }
            )

            # שחרור יתרה קפואה (ניכוי מההקפאה)
            await db.users.update_one(
                {"user_id": payout["seller_id"]},
                {
                    "$inc": {"frozen_balance": -payout["amount"]},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # רישום טרנזקציה
            await db.transactions.insert_one({
                "user_id": payout["seller_id"],
                "type": "payout",
                "amount": -payout["amount"],
                "description": f"משיכת כספים (נטו: {payout['net_amount']:.2f}₪)",
                "reference_id": str(payout_id),
                "status": "completed",
                "created_at": datetime.utcnow()
            })

            # התראה למוכר
            from services.notification_service import NotificationService
            await NotificationService.notify_payout_approved(
                seller_id=payout["seller_id"],
                amount=payout["net_amount"]
            )

            logger.info(f"Payout approved: {payout_id} by admin {admin_id}")
            return None

        except Exception as e:
            logger.error(f"Error approving payout: {e}")
            return f"❌ שגיאה באישור משיכה: {str(e)}"

    @staticmethod
    async def reject_payout(payout_id: str, admin_id: int, reason: str) -> Optional[str]:
        """
        דחיית משיכה על ידי אדמין

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            payout = await db.payouts.find_one({"_id": ObjectId(payout_id)})

            if not payout:
                return "❌ בקשת משיכה לא נמצאה"

            if payout["status"] != "pending":
                return "❌ בקשת המשיכה כבר עובדה"

            # עדכון סטטוס
            await db.payouts.update_one(
                {"_id": ObjectId(payout_id)},
                {
                    "$set": {
                        "status": "rejected",
                        "rejected_by": admin_id,
                        "rejected_at": datetime.utcnow(),
                        "rejection_reason": reason
                    }
                }
            )

            # החזרת יתרה מהקפאה
            await db.users.update_one(
                {"user_id": payout["seller_id"]},
                {
                    "$inc": {
                        "balance": payout["amount"],
                        "frozen_balance": -payout["amount"]
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # התראה למוכר
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=payout["seller_id"],
                title="❌ בקשת משיכה נדחתה",
                message=f"בקשתך למשיכת {payout['amount']:.2f}₪ נדחתה\nסיבה: {reason}",
                notification_type="payout_rejected"
            )

            logger.info(f"Payout rejected: {payout_id} by admin {admin_id}")
            return None

        except Exception as e:
            logger.error(f"Error rejecting payout: {e}")
            return f"❌ שגיאה בדחיית משיכה: {str(e)}"

    @staticmethod
    async def get_pending_payouts() -> List[Dict[str, Any]]:
        """קבלת בקשות משיכה ממתינות (לאדמין)"""
        try:
            cursor = db.payouts.find({
                "status": "pending"
            }).sort("created_at", 1)

            payouts = await cursor.to_list(length=None)

            # הוספת מידע על המוכרים
            for payout in payouts:
                seller = await db.users.find_one({"user_id": payout["seller_id"]})
                if seller:
                    payout["seller_name"] = seller.get("business_name", "מוכר")
                    payout["seller_verified"] = seller.get("verified", False)
                else:
                    payout["seller_name"] = "מוכר"
                    payout["seller_verified"] = False

            return payouts

        except Exception as e:
            logger.error(f"Error getting pending payouts: {e}")
            return []

    @staticmethod
    async def get_seller_payouts(seller_id: int) -> List[Dict[str, Any]]:
        """קבלת משיכות של מוכר"""
        try:
            cursor = db.payouts.find({
                "seller_id": seller_id
            }).sort("created_at", -1)

            payouts = await cursor.to_list(length=None)
            return payouts

        except Exception as e:
            logger.error(f"Error getting seller payouts: {e}")
            return []

    @staticmethod
    async def get_payout_by_id(payout_id: str) -> Optional[Dict[str, Any]]:
        """קבלת משיכה לפי ID"""
        try:
            payout = await db.payouts.find_one({"_id": ObjectId(payout_id)})

            if payout:
                # הוספת מידע על המוכר
                seller = await db.users.find_one({"user_id": payout["seller_id"]})
                if seller:
                    payout["seller_name"] = seller.get("business_name", "מוכר")
                    payout["seller_verified"] = seller.get("verified", False)

            return payout

        except Exception as e:
            logger.error(f"Error getting payout: {e}")
            return None

    @staticmethod
    async def calculate_available_for_payout(seller_id: int) -> float:
        """חישוב סכום זמין למשיכה"""
        try:
            user = await db.users.find_one({"user_id": seller_id})

            if not user:
                return 0.0

            balance = user.get("balance", 0.0)

            # ניכוי יתרה קפואה
            frozen = user.get("frozen_balance", 0.0)

            available = balance

            # ניכוי עמלה
            commission = available * Config.SELLER_COMMISSION_RATE
            net_available = available - commission

            return max(0, net_available)

        except Exception as e:
            logger.error(f"Error calculating available payout: {e}")
            return 0.0

    @staticmethod
    async def get_payout_stats(seller_id: Optional[int] = None) -> Dict[str, Any]:
        """סטטיסטיקות משיכות"""
        try:
            query = {}
            if seller_id:
                query["seller_id"] = seller_id

            # סך כל משיכות
            total_payouts = await db.payouts.count_documents(query)

            # משיכות מאושרות
            approved = await db.payouts.count_documents({**query, "status": "approved"})

            # משיכות ממתינות
            pending = await db.payouts.count_documents({**query, "status": "pending"})

            # סכום כולל
            pipeline = [
                {"$match": {**query, "status": "approved"}},
                {"$group": {
                    "_id": None,
                    "total_amount": {"$sum": "$net_amount"}
                }}
            ]

            cursor = db.payouts.aggregate(pipeline)
            results = await cursor.to_list(length=1)
            total_amount = results[0]["total_amount"] if results else 0

            return {
                "total_payouts": total_payouts,
                "approved": approved,
                "pending": pending,
                "total_amount": total_amount
            }

        except Exception as e:
            logger.error(f"Error getting payout stats: {e}")
            return {
                "total_payouts": 0,
                "approved": 0,
                "pending": 0,
                "total_amount": 0
            }
