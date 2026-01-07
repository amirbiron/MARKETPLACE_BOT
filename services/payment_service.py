"""
שירות ניהול תשלומים (Payments)
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class PaymentService:
    """שירות לניהול תשלומים"""

    @staticmethod
    async def add_balance(
        user_id: int,
        amount: float,
        payment_method: str = "manual",
        reference: Optional[str] = None
    ) -> Optional[str]:
        """
        הוספת יתרה למשתמש

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            if amount <= 0:
                return "❌ סכום לא תקין"

            # עדכון יתרה
            await db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$inc": {"balance": amount},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # רישום טרנזקציה
            await db.transactions.insert_one({
                "user_id": user_id,
                "type": "deposit",
                "amount": amount,
                "payment_method": payment_method,
                "reference": reference,
                "description": f"הוספת יתרה - {payment_method}",
                "status": "completed",
                "created_at": datetime.utcnow()
            })

            # התראה
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=user_id,
                title="💰 יתרה נוספה",
                message=f"נוספו {amount:.2f}₪ ליתרתך",
                notification_type="balance_added"
            )

            logger.info(f"Balance added: {amount}₪ to user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error adding balance: {e}")
            return f"❌ שגיאה בהוספת יתרה: {str(e)}"

    @staticmethod
    async def process_payment(
        buyer_id: int,
        seller_id: int,
        amount: float,
        description: str,
        reference_id: Optional[str] = None
    ) -> Optional[str]:
        """
        עיבוד תשלום בין משתמשים

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            buyer = await db.users.find_one({"telegram_id": buyer_id})

            if not buyer:
                return "❌ קונה לא נמצא"

            if buyer["balance"] < amount:
                return f"❌ אין מספיק יתרה. יתרה נוכחית: {buyer['balance']:.2f}₪"

            # ניכוי מהקונה
            await db.users.update_one(
                {"telegram_id": buyer_id},
                {
                    "$inc": {"balance": -amount},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # הוספה למוכר
            await db.users.update_one(
                {"telegram_id": seller_id},
                {
                    "$inc": {"balance": amount},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # רישום טרנזקציות
            await db.transactions.insert_one({
                "user_id": buyer_id,
                "type": "payment",
                "amount": -amount,
                "description": f"תשלום - {description}",
                "reference_id": reference_id,
                "recipient_id": seller_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })

            await db.transactions.insert_one({
                "user_id": seller_id,
                "type": "receipt",
                "amount": amount,
                "description": f"קבלה - {description}",
                "reference_id": reference_id,
                "sender_id": buyer_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })

            logger.info(f"Payment processed: {amount}₪ from {buyer_id} to {seller_id}")
            return None

        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            return f"❌ שגיאה בעיבוד תשלום: {str(e)}"

    @staticmethod
    async def freeze_balance(user_id: int, amount: float) -> Optional[str]:
        """
        הקפאת יתרה (למכרזים)

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            user = await db.users.find_one({"telegram_id": user_id})

            if not user:
                return "❌ משתמש לא נמצא"

            if user["balance"] < amount:
                return f"❌ אין מספיק יתרה. יתרה נוכחית: {user['balance']:.2f}₪"

            # העברה מיתרה רגילה ליתרה קפואה
            await db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$inc": {
                        "balance": -amount,
                        "frozen_balance": amount
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            logger.info(f"Balance frozen: {amount}₪ for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error freezing balance: {e}")
            return f"❌ שגיאה בהקפאת יתרה: {str(e)}"

    @staticmethod
    async def unfreeze_balance(user_id: int, amount: float) -> Optional[str]:
        """
        שחרור יתרה קפואה

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            user = await db.users.find_one({"telegram_id": user_id})

            if not user:
                return "❌ משתמש לא נמצא"

            if user.get("frozen_balance", 0) < amount:
                return "❌ אין מספיק יתרה קפואה"

            # החזרה מיתרה קפואה ליתרה רגילה
            await db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$inc": {
                        "balance": amount,
                        "frozen_balance": -amount
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            logger.info(f"Balance unfrozen: {amount}₪ for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error unfreezing balance: {e}")
            return f"❌ שגיאה בשחרור יתרה: {str(e)}"

    @staticmethod
    async def get_user_balance(user_id: int) -> Tuple[float, float]:
        """
        קבלת יתרה של משתמש

        Returns:
            Tuple[balance, frozen_balance]
        """
        try:
            user = await db.users.find_one({"telegram_id": user_id})

            if not user:
                return 0.0, 0.0

            return user.get("balance", 0.0), user.get("frozen_balance", 0.0)

        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            return 0.0, 0.0

    @staticmethod
    async def get_transaction_history(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """קבלת היסטוריית טרנזקציות"""
        try:
            cursor = db.transactions.find({
                "user_id": user_id
            }).sort("created_at", -1).limit(limit)

            transactions = await cursor.to_list(length=None)
            return transactions

        except Exception as e:
            logger.error(f"Error getting transaction history: {e}")
            return []

    @staticmethod
    async def create_payment_request(
        user_id: int,
        amount: float,
        description: str
    ) -> Optional[str]:
        """
        יצירת בקשת תשלום (לשילוב עם ספק תשלומים חיצוני)

        Returns:
            payment_request_id או None
        """
        try:
            payment_request = {
                "user_id": user_id,
                "amount": amount,
                "description": description,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=30)
            }

            result = await db.payment_requests.insert_one(payment_request)

            # כאן אפשר להוסיף אינטגרציה עם ספק תשלומים (PayPal, Stripe, וכו')

            logger.info(f"Payment request created: {result.inserted_id}")
            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error creating payment request: {e}")
            return None

    @staticmethod
    async def complete_payment_request(payment_request_id: str, external_ref: str) -> Optional[str]:
        """
        השלמת בקשת תשלום

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            payment_request = await db.payment_requests.find_one({"_id": ObjectId(payment_request_id)})

            if not payment_request:
                return "❌ בקשת תשלום לא נמצאה"

            if payment_request["status"] != "pending":
                return "❌ בקשת התשלום כבר עובדה"

            # בדיקה שלא פקעה
            if payment_request["expires_at"] < datetime.utcnow():
                return "❌ בקשת התשלום פגה"

            # הוספת יתרה
            error = await PaymentService.add_balance(
                user_id=payment_request["user_id"],
                amount=payment_request["amount"],
                payment_method="online",
                reference=external_ref
            )

            if error:
                return error

            # עדכון סטטוס
            await db.payment_requests.update_one(
                {"_id": ObjectId(payment_request_id)},
                {
                    "$set": {
                        "status": "completed",
                        "external_ref": external_ref,
                        "completed_at": datetime.utcnow()
                    }
                }
            )

            logger.info(f"Payment request completed: {payment_request_id}")
            return None

        except Exception as e:
            logger.error(f"Error completing payment request: {e}")
            return f"❌ שגיאה בהשלמת תשלום: {str(e)}"

    @staticmethod
    async def refund_payment(
        user_id: int,
        amount: float,
        description: str,
        reference_id: Optional[str] = None
    ) -> Optional[str]:
        """
        החזר כספי למשתמש

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            if amount <= 0:
                return "❌ סכום לא תקין"

            # הוספת יתרה
            await db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$inc": {"balance": amount},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # רישום טרנזקציה
            await db.transactions.insert_one({
                "user_id": user_id,
                "type": "refund",
                "amount": amount,
                "description": f"החזר - {description}",
                "reference_id": reference_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })

            # התראה
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=user_id,
                title="💸 החזר כספי",
                message=f"קיבלת החזר של {amount:.2f}₪",
                notification_type="refund"
            )

            logger.info(f"Refund processed: {amount}₪ to user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error processing refund: {e}")
            return f"❌ שגיאה בהחזר כספי: {str(e)}"

    @staticmethod
    async def get_payment_stats() -> Dict[str, Any]:
        """סטטיסטיקות תשלומים (לאדמין)"""
        try:
            from datetime import timedelta

            # תשלומים היום
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            today_deposits = await db.transactions.count_documents({
                "type": "deposit",
                "created_at": {"$gte": today_start}
            })

            # סכום כולל של הפקדות היום
            pipeline = [
                {"$match": {
                    "type": "deposit",
                    "created_at": {"$gte": today_start}
                }},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": "$amount"}
                }}
            ]

            cursor = db.transactions.aggregate(pipeline)
            results = await cursor.to_list(length=1)
            today_deposits_amount = results[0]["total"] if results else 0

            # סך הכל יתרה במערכת
            pipeline = [
                {"$group": {
                    "_id": None,
                    "total_balance": {"$sum": "$balance"},
                    "total_frozen": {"$sum": "$frozen_balance"}
                }}
            ]

            cursor = db.users.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if results:
                total_balance = results[0].get("total_balance", 0)
                total_frozen = results[0].get("total_frozen", 0)
            else:
                total_balance = 0
                total_frozen = 0

            return {
                "today_deposits": today_deposits,
                "today_deposits_amount": today_deposits_amount,
                "total_balance": total_balance,
                "total_frozen": total_frozen,
                "total_in_system": total_balance + total_frozen
            }

        except Exception as e:
            logger.error(f"Error getting payment stats: {e}")
            return {
                "today_deposits": 0,
                "today_deposits_amount": 0,
                "total_balance": 0,
                "total_frozen": 0,
                "total_in_system": 0
            }

    @staticmethod
    async def validate_transaction(transaction_id: str) -> bool:
        """אימות טרנזקציה"""
        try:
            transaction = await db.transactions.find_one({"_id": ObjectId(transaction_id)})
            return transaction is not None and transaction.get("status") == "completed"

        except Exception as e:
            logger.error(f"Error validating transaction: {e}")
            return False
