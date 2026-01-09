"""
שירות קרדיט שירות למוכרים - מודל לוח מודעות (Classifieds)

קרדיט השירות הוא Non-Refundable ומשמש לתשלום עמלות בלבד.
"""
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
from bson import ObjectId
import database
from models import ServiceCreditTopup, TopupPaymentMethod, User
from config import Config
import logging
import random
import string

logger = logging.getLogger(__name__)


class ServiceCreditService:
    """שירות לניהול קרדיט שירות למוכרים"""
    
    @staticmethod
    def _generate_reference_code() -> str:
        """יצירת קוד ייחודי לזיהוי טעינה"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    @staticmethod
    def calculate_credit_with_bonus(
        amount_paid: float, 
        payment_method: TopupPaymentMethod
    ) -> Tuple[float, float, float]:
        """
        חישוב קרדיט עם בונוס לפי אמצעי תשלום
        
        Returns:
            Tuple[credit_received, platform_fee, our_net_revenue]
        """
        # בונוס לפי אמצעי תשלום
        if payment_method == TopupPaymentMethod.TELEGRAM_STARS:
            bonus_rate = Config.TOPUP_BONUS_STARS
            platform_fee_rate = 0.30  # 30% עמלת טלגרם
        elif payment_method == TopupPaymentMethod.CRYPTO:
            bonus_rate = Config.TOPUP_BONUS_CRYPTO
            platform_fee_rate = 0.0  # אפס עמלות
        elif payment_method == TopupPaymentMethod.EXTERNAL_LINK:
            bonus_rate = Config.TOPUP_BONUS_EXTERNAL_LINK
            platform_fee_rate = 0.03  # 3% עמלת משולם
        else:
            bonus_rate = 0.0
            platform_fee_rate = 0.02
        
        # חישוב קרדיט עם בונוס
        credit_received = amount_paid * (1 + bonus_rate)
        platform_fee = amount_paid * platform_fee_rate
        our_net_revenue = amount_paid - platform_fee
        
        return round(credit_received, 2), round(platform_fee, 2), round(our_net_revenue, 2)
    
    @staticmethod
    async def get_seller_credit_balance(seller_id: int) -> float:
        """קבלת יתרת קרדיט שירות של מוכר"""
        users = await database.get_users_collection()
        user = await users.find_one({"user_id": seller_id})
        
        if user:
            return user.get("service_credit_balance", 0.0)
        return 0.0
    
    @staticmethod
    async def can_seller_publish(seller_id: int) -> Tuple[bool, str]:
        """
        בדיקה האם מוכר יכול לפרסם קופון
        
        Returns:
            Tuple[can_publish, error_message]
        """
        balance = await ServiceCreditService.get_seller_credit_balance(seller_id)
        
        if balance < Config.SELLER_MIN_BALANCE_FOR_PUBLISH:
            return False, (
                f"❌ נקודות הקרדיט שלך נמוכות מדי!\n\n"
                f"💰 יתרה נוכחית: {balance:.2f} נקודות\n"
                f"📌 מינימום נדרש: {Config.SELLER_MIN_BALANCE_FOR_PUBLISH:.2f} נקודות\n\n"
                f"⚠️ יש לטעון קרדיט שירות כדי להמשיך לפרסם."
            )
        
        return True, ""
    
    @staticmethod
    async def create_topup_request(
        seller_id: int,
        amount_paid: float,
        payment_method: TopupPaymentMethod,
        payment_proof_image: Optional[str] = None
    ) -> Tuple[Optional[ServiceCreditTopup], Optional[str]]:
        """
        יצירת בקשת טעינת קרדיט
        
        Returns:
            Tuple[topup, error_message]
        """
        try:
            # חישוב קרדיט עם בונוס
            credit_received, platform_fee, our_net_revenue = (
                ServiceCreditService.calculate_credit_with_bonus(amount_paid, payment_method)
            )
            
            # יצירת קוד ייחודי
            ref_code = ServiceCreditService._generate_reference_code()
            
            topup = ServiceCreditTopup(
                seller_id=seller_id,
                amount_paid_ils=amount_paid,
                credit_received=credit_received,
                payment_method=payment_method,
                platform_fee=platform_fee,
                our_net_revenue=our_net_revenue,
                reference_code=ref_code,
                payment_proof_image=payment_proof_image,
                status="pending"
            )
            
            topups_col = await database.get_service_credit_topups_collection()
            result = await topups_col.insert_one(topup.to_dict())
            topup._id = result.inserted_id
            
            logger.info(f"Created topup request {topup._id} for seller {seller_id}, amount={amount_paid}₪")
            
            return topup, None
            
        except Exception as e:
            logger.error(f"Failed to create topup request for seller {seller_id}: {e}")
            return None, f"❌ שגיאה ביצירת בקשת טעינה: {e}"
    
    @staticmethod
    async def approve_topup(
        topup_id: ObjectId,
        admin_id: int
    ) -> Tuple[bool, str]:
        """
        אישור בקשת טעינה והוספת קרדיט למוכר
        
        Returns:
            Tuple[success, message]
        """
        try:
            topups_col = await database.get_service_credit_topups_collection()
            topup_data = await topups_col.find_one({"_id": topup_id})
            
            if not topup_data:
                return False, "❌ בקשת טעינה לא נמצאה"
            
            if topup_data.get("status") != "pending":
                return False, f"❌ הבקשה כבר טופלה (סטטוס: {topup_data.get('status')})"
            
            seller_id = topup_data["seller_id"]
            credit_to_add = topup_data["credit_received"]
            
            # עדכון יתרת קרדיט המוכר
            users = await database.get_users_collection()
            result = await users.update_one(
                {"user_id": seller_id},
                {
                    "$inc": {"service_credit_balance": credit_to_add},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count == 0:
                return False, "❌ שגיאה בעדכון יתרת המוכר"
            
            # עדכון סטטוס הטעינה
            await topups_col.update_one(
                {"_id": topup_id},
                {
                    "$set": {
                        "status": "approved",
                        "approved_by": admin_id,
                        "processed_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Approved topup {topup_id}, added {credit_to_add} credit to seller {seller_id}")
            
            return True, f"✅ אושר! נוספו {credit_to_add:.2f} נקודות קרדיט למוכר"
            
        except Exception as e:
            logger.error(f"Failed to approve topup {topup_id}: {e}")
            return False, f"❌ שגיאה באישור: {e}"
    
    @staticmethod
    async def reject_topup(
        topup_id: ObjectId,
        admin_id: int,
        reason: str = ""
    ) -> Tuple[bool, str]:
        """דחיית בקשת טעינה"""
        try:
            topups_col = await database.get_service_credit_topups_collection()
            
            result = await topups_col.update_one(
                {"_id": topup_id, "status": "pending"},
                {
                    "$set": {
                        "status": "rejected",
                        "approved_by": admin_id,
                        "processed_at": datetime.utcnow(),
                        "rejection_reason": reason
                    }
                }
            )
            
            if result.modified_count == 0:
                return False, "❌ לא נמצאה בקשה פתוחה"
            
            logger.info(f"Rejected topup {topup_id}")
            return True, "✅ הבקשה נדחתה"
            
        except Exception as e:
            logger.error(f"Failed to reject topup {topup_id}: {e}")
            return False, f"❌ שגיאה: {e}"
    
    @staticmethod
    async def deduct_commission(
        seller_id: int,
        sale_price: float,
        order_id: ObjectId
    ) -> Tuple[bool, float, str]:
        """
        ניכוי עמלה מקרדיט המוכר אחרי מכירה מוצלחת
        
        Returns:
            Tuple[success, commission_amount, message]
        """
        try:
            commission = sale_price * Config.SELLER_COMMISSION_RATE_P2P
            commission = round(commission, 2)
            
            users = await database.get_users_collection()
            
            # בדיקת יתרה
            user = await users.find_one({"user_id": seller_id})
            if not user:
                return False, 0, "❌ מוכר לא נמצא"
            
            current_balance = user.get("service_credit_balance", 0.0)
            
            # גם אם היתרה תרד לשלילי, מאפשרים מכירה אבל חוסמים פרסום חדש
            new_balance = current_balance - commission
            
            # עדכון יתרה וסטטיסטיקות
            result = await users.update_one(
                {"user_id": seller_id},
                {
                    "$inc": {
                        "service_credit_balance": -commission,
                        "total_commissions_paid": commission,
                        "total_earned_real_money": sale_price,
                        "sales_count": 1
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count == 0:
                return False, 0, "❌ שגיאה בעדכון יתרה"
            
            logger.info(f"Deducted {commission}₪ commission from seller {seller_id} for order {order_id}")
            
            # הודעה על יתרה נמוכה
            message = f"✅ נוכו {commission:.2f} נקודות עמלה"
            if new_balance < Config.SELLER_MIN_BALANCE_FOR_PUBLISH:
                message += f"\n\n⚠️ שים לב: נקודות הקרדיט שלך ({new_balance:.2f}) נמוכות מהמינימום לפרסום ({Config.SELLER_MIN_BALANCE_FOR_PUBLISH:.2f})"
            
            return True, commission, message
            
        except Exception as e:
            logger.error(f"Failed to deduct commission from seller {seller_id}: {e}")
            return False, 0, f"❌ שגיאה: {e}"
    
    @staticmethod
    async def apply_timeout_penalty(seller_id: int) -> Tuple[bool, str]:
        """
        החלת קנס למוכר שלא ענה בזמן (12 שעות)
        
        Returns:
            Tuple[success, message]
        """
        try:
            penalty = Config.SELLER_TIMEOUT_PENALTY
            
            users = await database.get_users_collection()
            
            result = await users.update_one(
                {"user_id": seller_id},
                {
                    "$inc": {
                        "service_credit_balance": -penalty,
                        "timeout_violations": 1
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count == 0:
                return False, "❌ שגיאה בהחלת קנס"
            
            # בדיקה אם צריך להשעות
            user = await users.find_one({"user_id": seller_id})
            violations = user.get("timeout_violations", 0)
            
            message = f"⚠️ קנס של {penalty:.2f} נקודות הוחל עקב אי-מענה בזמן"
            
            if violations >= Config.SELLER_MAX_TIMEOUT_VIOLATIONS:
                # השעיית המוכר
                await users.update_one(
                    {"user_id": seller_id},
                    {"$set": {"seller_status": "blocked"}}
                )
                message += "\n\n🚫 חשבונך הושעה עקב הפרות חוזרות. פנה לתמיכה."
            
            logger.info(f"Applied timeout penalty to seller {seller_id}, violations: {violations}")
            
            return True, message
            
        except Exception as e:
            logger.error(f"Failed to apply timeout penalty to seller {seller_id}: {e}")
            return False, f"❌ שגיאה: {e}"
    
    @staticmethod
    async def get_seller_topup_history(
        seller_id: int,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """קבלת היסטוריית טעינות של מוכר"""
        topups_col = await database.get_service_credit_topups_collection()
        
        cursor = topups_col.find(
            {"seller_id": seller_id}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    @staticmethod
    async def get_pending_topups() -> List[Dict[str, Any]]:
        """קבלת כל בקשות הטעינה הממתינות (לאדמין)"""
        topups_col = await database.get_service_credit_topups_collection()
        
        cursor = topups_col.find(
            {"status": "pending"}
        ).sort("created_at", 1)
        
        return await cursor.to_list(length=None)
    
    @staticmethod
    async def get_credit_stats(seller_id: int) -> Dict[str, Any]:
        """קבלת סטטיסטיקות קרדיט של מוכר"""
        users = await database.get_users_collection()
        user = await users.find_one({"user_id": seller_id})
        
        if not user:
            return {}
        
        balance = user.get("service_credit_balance", 0.0)
        total_commissions = user.get("total_commissions_paid", 0.0)
        total_earned = user.get("total_earned_real_money", 0.0)
        sales_count = user.get("sales_count", 0)
        
        # חישוב כמה מכירות נותרו
        avg_commission = total_commissions / sales_count if sales_count > 0 else 5.0  # ברירת מחדל ₪5
        remaining_sales = int(balance / avg_commission) if avg_commission > 0 else 0
        
        return {
            "balance": balance,
            "total_commissions_paid": total_commissions,
            "total_earned_real_money": total_earned,
            "sales_count": sales_count,
            "avg_commission_per_sale": round(avg_commission, 2),
            "estimated_remaining_sales": remaining_sales,
            "min_balance_required": Config.SELLER_MIN_BALANCE_FOR_PUBLISH,
            "can_publish": balance >= Config.SELLER_MIN_BALANCE_FOR_PUBLISH
        }
    
    @staticmethod
    async def update_payment_methods(
        seller_id: int,
        bit_phone: Optional[str] = None,
        paybox_link: Optional[str] = None
    ) -> Tuple[bool, str]:
        """עדכון אמצעי תשלום של מוכר"""
        try:
            payment_methods = {}
            if bit_phone:
                payment_methods["bit"] = bit_phone
            if paybox_link:
                payment_methods["paybox"] = paybox_link
            
            if not payment_methods:
                return False, "❌ יש להגדיר לפחות אמצעי תשלום אחד"
            
            users = await database.get_users_collection()
            result = await users.update_one(
                {"user_id": seller_id},
                {
                    "$set": {
                        "payment_methods": payment_methods,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count == 0:
                return False, "❌ שגיאה בעדכון"
            
            return True, "✅ אמצעי התשלום עודכנו בהצלחה"
            
        except Exception as e:
            logger.error(f"Failed to update payment methods for seller {seller_id}: {e}")
            return False, f"❌ שגיאה: {e}"
    
    @staticmethod
    async def get_seller_payment_methods(seller_id: int) -> Dict[str, str]:
        """קבלת אמצעי תשלום של מוכר"""
        users = await database.get_users_collection()
        user = await users.find_one({"user_id": seller_id})
        
        if user:
            return user.get("payment_methods", {})
        return {}
