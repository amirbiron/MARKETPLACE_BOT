"""
שירות ניהול משיכות כספים (Payouts)
תמיכה במשיכות אוטומטיות לבנק, PayPal, Payoneer
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import aiohttp
import json
import base64

from database import db
import database
from models import (
    Payout, PayoutStatus, PayoutMethod, PayoutTransaction,
    PayoutTransactionStatus
)
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

    # ==================== Automated Payouts ====================

    @staticmethod
    async def request_automated_payout(
        seller_id: int,
        amount: float,
        method: PayoutMethod,
        payout_details: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        בקשת משיכה אוטומטית
        
        Args:
            seller_id: מזהה המוכר
            amount: סכום המשיכה
            method: שיטת המשיכה
            payout_details: פרטי המשיכה (בנק/פייפאל/וכו')
        
        Returns:
            Tuple[payout_id, error_message]
        """
        try:
            # בדיקת זכאות
            can_request, error = await PayoutService.can_request_payout(seller_id, amount)
            if not can_request:
                return None, error
            
            # חישוב עמלה
            fee = amount * Config.PAYOUT_COMMISSION
            net_amount = amount - fee
            
            # יצירת עסקת משיכה
            payout_col = await database.get_payout_transactions_collection()
            
            payout = PayoutTransaction(
                seller_id=seller_id,
                amount=amount,
                fee=fee,
                net_amount=net_amount,
                method=method,
                payout_details=payout_details
            )
            
            result = await payout_col.insert_one(payout.to_dict())
            payout_id = str(result.inserted_id)
            
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
                message=f"בקשתך למשיכת {net_amount:.2f}₪ ב{PayoutService._get_method_name(method)} התקבלה.\n"
                        f"זמן עיבוד משוער: {Config.PAYOUT_PROCESSING_DAYS} ימי עסקים",
                notification_type="payout_requested"
            )
            
            # התראה לאדמינים
            for admin_id in Config.ADMIN_IDS:
                await NotificationService.send_notification(
                    user_id=admin_id,
                    title="💰 בקשת משיכה אוטומטית",
                    message=f"מוכר {seller_id} מבקש למשוך {net_amount:.2f}₪\n"
                            f"שיטה: {PayoutService._get_method_name(method)}",
                    notification_type="payout_request_admin",
                    data={"payout_id": payout_id}
                )
            
            logger.info(f"Automated payout requested: {payout_id} for {amount}₪")
            return payout_id, None
            
        except Exception as e:
            logger.error(f"Error requesting automated payout: {e}")
            return None, f"שגיאה בבקשת משיכה: {str(e)}"
    
    @staticmethod
    async def process_automated_payout(payout_id: str, admin_id: int) -> Tuple[bool, Optional[str]]:
        """
        עיבוד משיכה אוטומטית
        
        Returns:
            Tuple[success, error_message]
        """
        try:
            payout_col = await database.get_payout_transactions_collection()
            payout_data = await payout_col.find_one({"_id": ObjectId(payout_id)})
            
            if not payout_data:
                return False, "משיכה לא נמצאה"
            
            if payout_data["status"] != PayoutTransactionStatus.PENDING.value:
                return False, "המשיכה כבר עובדה"
            
            method = PayoutMethod(payout_data["method"])
            
            # עדכון סטטוס לעיבוד
            await payout_col.update_one(
                {"_id": ObjectId(payout_id)},
                {
                    "$set": {
                        "status": PayoutTransactionStatus.PROCESSING.value,
                        "processed_by": admin_id,
                        "processed_at": datetime.utcnow()
                    }
                }
            )
            
            # ביצוע המשיכה לפי השיטה
            if method == PayoutMethod.PAYPAL:
                success, reference = await PayoutService._process_paypal_payout(payout_data)
            elif method == PayoutMethod.PAYONEER:
                success, reference = await PayoutService._process_payoneer_payout(payout_data)
            elif method == PayoutMethod.BANK_TRANSFER:
                # העברה בנקאית - ידנית, רק סימון
                success, reference = True, f"BANK_{payout_id[:8]}"
            elif method == PayoutMethod.BIT:
                # ביט - ידני
                success, reference = True, f"BIT_{payout_id[:8]}"
            else:
                success, reference = False, None
            
            if success:
                # עדכון הצלחה
                await payout_col.update_one(
                    {"_id": ObjectId(payout_id)},
                    {
                        "$set": {
                            "status": PayoutTransactionStatus.COMPLETED.value,
                            "gateway_reference": reference,
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                # שחרור יתרה קפואה
                await db.users.update_one(
                    {"user_id": payout_data["seller_id"]},
                    {
                        "$inc": {"frozen_balance": -payout_data["amount"]},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                
                # רישום טרנזקציה
                await db.transactions.insert_one({
                    "user_id": payout_data["seller_id"],
                    "type": "automated_payout",
                    "amount": -payout_data["amount"],
                    "description": f"משיכה אוטומטית - {PayoutService._get_method_name(method)}",
                    "reference_id": payout_id,
                    "gateway_reference": reference,
                    "status": "completed",
                    "created_at": datetime.utcnow()
                })
                
                # התראה למוכר
                from services.notification_service import NotificationService
                await NotificationService.send_notification(
                    user_id=payout_data["seller_id"],
                    title="✅ המשיכה אושרה והועברה",
                    message=f"הועברו {payout_data['net_amount']:.2f}₪ ל{PayoutService._get_method_name(method)}.\n"
                            f"מזהה: {reference}",
                    notification_type="payout_completed"
                )
                
                logger.info(f"Payout completed: {payout_id}, reference: {reference}")
                return True, None
            else:
                # כישלון
                await payout_col.update_one(
                    {"_id": ObjectId(payout_id)},
                    {
                        "$set": {
                            "status": PayoutTransactionStatus.FAILED.value,
                            "notes": "Failed to process payout"
                        }
                    }
                )
                
                # החזרת יתרה
                await db.users.update_one(
                    {"user_id": payout_data["seller_id"]},
                    {
                        "$inc": {
                            "balance": payout_data["amount"],
                            "frozen_balance": -payout_data["amount"]
                        },
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                
                return False, "שגיאה בעיבוד המשיכה"
                
        except Exception as e:
            logger.error(f"Error processing automated payout: {e}")
            return False, str(e)
    
    @staticmethod
    async def _process_paypal_payout(payout_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """עיבוד משיכת PayPal"""
        try:
            if not Config.PAYPAL_CLIENT_ID or not Config.PAYPAL_CLIENT_SECRET:
                logger.warning("PayPal credentials not configured")
                # Return success for manual processing
                return True, f"MANUAL_PAYPAL_{payout_data['_id']}"
            
            # קבלת access token
            auth_url = "https://api.sandbox.paypal.com/v1/oauth2/token" if Config.PAYPAL_MODE == "sandbox" \
                else "https://api.paypal.com/v1/oauth2/token"
            
            auth_header = base64.b64encode(
                f"{Config.PAYPAL_CLIENT_ID}:{Config.PAYPAL_CLIENT_SECRET}".encode()
            ).decode()
            
            async with aiohttp.ClientSession() as session:
                # Get access token
                async with session.post(
                    auth_url,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data="grant_type=client_credentials"
                ) as auth_response:
                    auth_result = await auth_response.json()
                    
                    if "access_token" not in auth_result:
                        logger.error(f"Failed to get PayPal token: {auth_result}")
                        return False, None
                    
                    access_token = auth_result["access_token"]
                
                # Create payout
                payout_url = "https://api.sandbox.paypal.com/v1/payments/payouts" if Config.PAYPAL_MODE == "sandbox" \
                    else "https://api.paypal.com/v1/payments/payouts"
                
                payout_details = payout_data.get("payout_details", {})
                receiver_email = payout_details.get("paypal_email")
                
                if not receiver_email:
                    logger.error("No PayPal email provided")
                    return False, None
                
                payout_payload = {
                    "sender_batch_header": {
                        "sender_batch_id": str(payout_data["_id"]),
                        "email_subject": "Marketplace Payout",
                        "email_message": "You have received a payout from Marketplace"
                    },
                    "items": [{
                        "recipient_type": "EMAIL",
                        "amount": {
                            "value": str(payout_data["net_amount"]),
                            "currency": "ILS"
                        },
                        "receiver": receiver_email,
                        "note": "Marketplace seller payout"
                    }]
                }
                
                async with session.post(
                    payout_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=payout_payload
                ) as payout_response:
                    result = await payout_response.json()
                    
                    if "batch_header" in result:
                        return True, result["batch_header"]["payout_batch_id"]
                    else:
                        logger.error(f"PayPal payout failed: {result}")
                        return False, None
                        
        except Exception as e:
            logger.error(f"Error processing PayPal payout: {e}")
            return False, None
    
    @staticmethod
    async def _process_payoneer_payout(payout_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """עיבוד משיכת Payoneer"""
        try:
            if not Config.PAYONEER_API_KEY or not Config.PAYONEER_PROGRAM_ID:
                logger.warning("Payoneer credentials not configured")
                return True, f"MANUAL_PAYONEER_{payout_data['_id']}"
            
            payout_details = payout_data.get("payout_details", {})
            payee_id = payout_details.get("payoneer_id")
            
            if not payee_id:
                logger.error("No Payoneer ID provided")
                return False, None
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "payee_id": payee_id,
                    "amount": payout_data["net_amount"],
                    "currency": "ILS",
                    "description": "Marketplace payout",
                    "client_reference_id": str(payout_data["_id"])
                }
                
                async with session.post(
                    f"{Config.PAYONEER_API_URL}/programs/{Config.PAYONEER_PROGRAM_ID}/payouts",
                    headers={
                        "Authorization": f"Bearer {Config.PAYONEER_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        return True, result.get("payout_id")
                    else:
                        logger.error(f"Payoneer payout failed: {result}")
                        return False, None
                        
        except Exception as e:
            logger.error(f"Error processing Payoneer payout: {e}")
            return False, None
    
    @staticmethod
    async def get_automated_payouts(
        seller_id: Optional[int] = None,
        status: Optional[PayoutTransactionStatus] = None,
        limit: int = 50
    ) -> List[PayoutTransaction]:
        """קבלת משיכות אוטומטיות"""
        try:
            payout_col = await database.get_payout_transactions_collection()
            
            query = {}
            if seller_id:
                query["seller_id"] = seller_id
            if status:
                query["status"] = status.value
            
            cursor = payout_col.find(query).sort("created_at", -1).limit(limit)
            
            payouts = []
            async for data in cursor:
                payouts.append(PayoutTransaction.from_dict(data))
            
            return payouts
            
        except Exception as e:
            logger.error(f"Error getting automated payouts: {e}")
            return []
    
    @staticmethod
    async def get_pending_automated_payouts() -> List[PayoutTransaction]:
        """קבלת משיכות אוטומטיות ממתינות"""
        return await PayoutService.get_automated_payouts(
            status=PayoutTransactionStatus.PENDING
        )
    
    @staticmethod
    async def reject_automated_payout(
        payout_id: str,
        admin_id: int,
        reason: str
    ) -> Tuple[bool, Optional[str]]:
        """דחיית משיכה אוטומטית"""
        try:
            payout_col = await database.get_payout_transactions_collection()
            payout_data = await payout_col.find_one({"_id": ObjectId(payout_id)})
            
            if not payout_data:
                return False, "משיכה לא נמצאה"
            
            if payout_data["status"] not in [
                PayoutTransactionStatus.PENDING.value,
                PayoutTransactionStatus.PROCESSING.value
            ]:
                return False, "לא ניתן לדחות משיכה זו"
            
            # עדכון סטטוס
            await payout_col.update_one(
                {"_id": ObjectId(payout_id)},
                {
                    "$set": {
                        "status": PayoutTransactionStatus.REJECTED.value,
                        "processed_by": admin_id,
                        "processed_at": datetime.utcnow(),
                        "notes": reason
                    }
                }
            )
            
            # החזרת יתרה
            await db.users.update_one(
                {"user_id": payout_data["seller_id"]},
                {
                    "$inc": {
                        "balance": payout_data["amount"],
                        "frozen_balance": -payout_data["amount"]
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            # התראה למוכר
            from services.notification_service import NotificationService
            await NotificationService.send_notification(
                user_id=payout_data["seller_id"],
                title="❌ בקשת משיכה נדחתה",
                message=f"בקשתך למשיכת {payout_data['amount']:.2f}₪ נדחתה.\n"
                        f"סיבה: {reason}\n\n"
                        f"היתרה הוחזרה לחשבונך.",
                notification_type="payout_rejected"
            )
            
            logger.info(f"Automated payout rejected: {payout_id}")
            return True, None
            
        except Exception as e:
            logger.error(f"Error rejecting automated payout: {e}")
            return False, str(e)
    
    @staticmethod
    async def save_payout_details(
        seller_id: int,
        method: PayoutMethod,
        details: Dict[str, Any]
    ) -> bool:
        """שמירת פרטי משיכה למוכר"""
        try:
            field_name = f"payout_{method.value}_details"
            
            await db.users.update_one(
                {"user_id": seller_id},
                {
                    "$set": {
                        field_name: details,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving payout details: {e}")
            return False
    
    @staticmethod
    async def get_saved_payout_details(
        seller_id: int,
        method: PayoutMethod
    ) -> Optional[Dict[str, Any]]:
        """קבלת פרטי משיכה שמורים"""
        try:
            user = await db.users.find_one({"user_id": seller_id})
            if not user:
                return None
            
            field_name = f"payout_{method.value}_details"
            return user.get(field_name)
            
        except Exception as e:
            logger.error(f"Error getting payout details: {e}")
            return None
    
    @staticmethod
    def _get_method_name(method: PayoutMethod) -> str:
        """קבלת שם שיטת המשיכה בעברית"""
        names = {
            PayoutMethod.BANK_TRANSFER: "העברה בנקאית",
            PayoutMethod.PAYPAL: "PayPal",
            PayoutMethod.PAYONEER: "Payoneer",
            PayoutMethod.BIT: "ביט"
        }
        return names.get(method, str(method.value))
    
    @staticmethod
    async def get_automated_payout_stats() -> Dict[str, Any]:
        """סטטיסטיקות משיכות אוטומטיות"""
        try:
            payout_col = await database.get_payout_transactions_collection()
            
            # סטטוס משיכות
            pipeline = [
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total": {"$sum": "$net_amount"}
                }}
            ]
            
            cursor = payout_col.aggregate(pipeline)
            by_status = await cursor.to_list(None)
            
            # לפי שיטה
            method_pipeline = [
                {"$match": {"status": PayoutTransactionStatus.COMPLETED.value}},
                {"$group": {
                    "_id": "$method",
                    "count": {"$sum": 1},
                    "total": {"$sum": "$net_amount"}
                }}
            ]
            
            cursor = payout_col.aggregate(method_pipeline)
            by_method = await cursor.to_list(None)
            
            return {
                "by_status": {s["_id"]: {"count": s["count"], "total": s["total"]} for s in by_status},
                "by_method": {m["_id"]: {"count": m["count"], "total": m["total"]} for m in by_method}
            }
            
        except Exception as e:
            logger.error(f"Error getting automated payout stats: {e}")
            return {"by_status": {}, "by_method": {}}
