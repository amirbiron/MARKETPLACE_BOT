"""
שירות זיהוי ומניעת הונאות אוטומטי (Anti-Fraud)

מזהה דפוסים חשודים ומפעיל פעולות אוטומטיות:
- זיהוי קופונים כפולים
- זיהוי מוכרים עם אחוז מחלוקות גבוה
- זיהוי קונים עם דפוס החזרים חריג
- זיהוי מחירים חריגים
- זיהוי פעילות מהירה מדי
- חישוב ניקוד אמינות (Trust Score)
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
from enum import Enum
import database
from config import Config
import logging

logger = logging.getLogger(__name__)


class FraudEventType(str, Enum):
    """סוגי אירועי הונאה"""
    DUPLICATE_COUPON = "duplicate_coupon"  # קופון כפול
    HIGH_DISPUTE_RATE = "high_dispute_rate"  # אחוז מחלוקות גבוה
    HIGH_REFUND_RATE = "high_refund_rate"  # אחוז החזרים חריג
    SUSPICIOUS_PRICING = "suspicious_pricing"  # מחיר חשוד
    RAPID_ACTIVITY = "rapid_activity"  # פעילות מהירה מדי
    AUTO_BLOCK = "auto_block"  # חסימה אוטומטית
    MANUAL_REVIEW = "manual_review"  # סימון לבדיקה ידנית
    LARGE_TRANSACTION = "large_transaction"  # עסקה גדולה
    NEW_SELLER_LIMIT = "new_seller_limit"  # הגבלת מוכר חדש
    LOW_TRUST_SCORE = "low_trust_score"  # ניקוד אמינות נמוך
    SUSPICIOUS_PATTERN = "suspicious_pattern"  # דפוס חשוד כללי


class FraudRiskLevel(str, Enum):
    """רמות סיכון"""
    LOW = "low"  # נמוך
    MEDIUM = "medium"  # בינוני
    HIGH = "high"  # גבוה
    CRITICAL = "critical"  # קריטי


class FraudDetectionService:
    """שירות זיהוי ומניעת הונאות"""

    # === חישוב ניקוד אמינות (Trust Score) ===

    @staticmethod
    async def calculate_trust_score(user_id: int) -> int:
        """
        חישוב ניקוד אמינות למוכר (0-100)
        
        מבוסס על:
        - גיל חשבון (עד 15 נקודות)
        - מספר עסקאות מוצלחות (עד 25 נקודות)
        - אחוז מחלוקות (עד 25 נקודות)
        - אימות (10 נקודות)
        - דירוג ממוצע (עד 25 נקודות)
        """
        try:
            users = await database.get_users_collection()
            orders = await database.get_orders_collection()
            disputes = await database.get_disputes_collection()
            
            user = await users.find_one({"user_id": user_id})
            if not user:
                return 0
            
            score = 0
            
            # 1. גיל חשבון (עד 15 נקודות)
            created_at = user.get("created_at", datetime.utcnow())
            account_age_days = (datetime.utcnow() - created_at).days
            
            if account_age_days >= 365:  # שנה ומעלה
                score += 15
            elif account_age_days >= 180:  # חצי שנה
                score += 12
            elif account_age_days >= 90:  # 3 חודשים
                score += 8
            elif account_age_days >= 30:  # חודש
                score += 5
            elif account_age_days >= 7:  # שבוע
                score += 2
            
            # 2. מספר עסקאות מוצלחות (עד 25 נקודות)
            successful_orders = await orders.count_documents({
                "seller_id": user_id,
                "status": {"$in": ["completed", "confirmed"]}
            })
            
            if successful_orders >= 100:
                score += 25
            elif successful_orders >= 50:
                score += 20
            elif successful_orders >= 20:
                score += 15
            elif successful_orders >= 10:
                score += 10
            elif successful_orders >= 5:
                score += 5
            elif successful_orders >= 1:
                score += 2
            
            # 3. אחוז מחלוקות (עד 25 נקודות, פחות = יותר טוב)
            total_orders = await orders.count_documents({"seller_id": user_id})
            total_disputes = await disputes.count_documents({"seller_id": user_id})
            
            if total_orders > 0:
                dispute_rate = (total_disputes / total_orders) * 100
                
                if dispute_rate == 0:
                    score += 25
                elif dispute_rate <= 2:
                    score += 20
                elif dispute_rate <= 5:
                    score += 15
                elif dispute_rate <= 10:
                    score += 10
                elif dispute_rate <= 15:
                    score += 5
                # מעל 15% = 0 נקודות
            else:
                # אין עסקאות עדיין - נקודות בסיסיות
                score += 10
            
            # 4. אימות (10 נקודות)
            if user.get("is_verified", False):
                score += 10
            elif user.get("role") == "seller_verified":
                score += 10
            
            # 5. דירוג ממוצע (עד 25 נקודות)
            rating_avg = user.get("rating_average", 0)
            rating_count = user.get("rating_count", 0)
            
            if rating_count >= 5:  # לפחות 5 דירוגים
                if rating_avg >= 4.5:
                    score += 25
                elif rating_avg >= 4.0:
                    score += 20
                elif rating_avg >= 3.5:
                    score += 15
                elif rating_avg >= 3.0:
                    score += 10
                elif rating_avg >= 2.5:
                    score += 5
                # מתחת ל-2.5 = 0 נקודות
            elif rating_count >= 1:
                # מעט דירוגים - ניקוד חלקי
                score += min(int(rating_avg * 3), 12)
            
            # וודא שהניקוד בטווח 0-100
            final_score = max(0, min(100, score))
            
            # שמירת הניקוד במסד הנתונים
            await users.update_one(
                {"user_id": user_id},
                {"$set": {"trust_score": final_score, "trust_score_updated_at": datetime.utcnow()}}
            )
            
            logger.debug(f"Calculated trust score for user {user_id}: {final_score}")
            return final_score
            
        except Exception as e:
            logger.error(f"Error calculating trust score for user {user_id}: {e}")
            return 0

    @staticmethod
    async def get_trust_score(user_id: int) -> int:
        """קבלת ניקוד אמינות (מהמטמון או חישוב חדש)"""
        try:
            users = await database.get_users_collection()
            user = await users.find_one({"user_id": user_id})
            
            if not user:
                return 0
            
            trust_score = user.get("trust_score")
            last_update = user.get("trust_score_updated_at")
            
            # עדכון אם הניקוד ישן מ-24 שעות או לא קיים
            if trust_score is None or last_update is None or \
               (datetime.utcnow() - last_update) > timedelta(hours=24):
                return await FraudDetectionService.calculate_trust_score(user_id)
            
            return trust_score
            
        except Exception as e:
            logger.error(f"Error getting trust score for user {user_id}: {e}")
            return 0

    @staticmethod
    def get_trust_score_level(score: int) -> Tuple[str, str]:
        """
        קבלת רמת אמינות לפי ניקוד
        Returns: (emoji, description)
        """
        if score >= 80:
            return "🏆", "מוכר אמין מאוד"
        elif score >= 60:
            return "✅", "מוכר אמין"
        elif score >= 40:
            return "⚠️", "מוכר סביר"
        elif score >= 20:
            return "⚡", "מוכר חדש/בהתפתחות"
        else:
            return "🔴", "דורש תשומת לב"

    @staticmethod
    def get_commission_discount(trust_score: int) -> float:
        """
        הנחה בעמלות למוכרים עם ניקוד גבוה
        Returns: אחוז הנחה (0.0 - 0.5)
        """
        if trust_score >= 90:
            return 0.50  # 50% הנחה
        elif trust_score >= 80:
            return 0.30  # 30% הנחה
        elif trust_score >= 70:
            return 0.15  # 15% הנחה
        elif trust_score >= 60:
            return 0.10  # 10% הנחה
        return 0.0  # אין הנחה

    # === זיהוי דפוסים חשודים ===

    @staticmethod
    async def detect_suspicious_activity(user_id: int) -> List[Dict[str, Any]]:
        """
        זיהוי פעילות חשודה של משתמש
        Returns: רשימת דגלים אדומים
        """
        red_flags = []
        
        try:
            # 1. בדיקת אחוז מחלוקות גבוה
            dispute_check = await FraudDetectionService._check_high_dispute_rate(user_id)
            if dispute_check:
                red_flags.append(dispute_check)
            
            # 2. בדיקת אחוז החזרים חריג (כקונה)
            refund_check = await FraudDetectionService._check_high_refund_rate(user_id)
            if refund_check:
                red_flags.append(refund_check)
            
            # 3. בדיקת פעילות מהירה מדי
            rapid_check = await FraudDetectionService._check_rapid_activity(user_id)
            if rapid_check:
                red_flags.append(rapid_check)
            
            # 4. בדיקת ניקוד אמינות נמוך
            trust_check = await FraudDetectionService._check_low_trust_score(user_id)
            if trust_check:
                red_flags.append(trust_check)
            
            return red_flags
            
        except Exception as e:
            logger.error(f"Error detecting suspicious activity for user {user_id}: {e}")
            return []

    @staticmethod
    async def _check_high_dispute_rate(user_id: int) -> Optional[Dict[str, Any]]:
        """בדיקת אחוז מחלוקות גבוה (מעל 20%)"""
        try:
            orders = await database.get_orders_collection()
            disputes = await database.get_disputes_collection()
            
            total_orders = await orders.count_documents({"seller_id": user_id})
            if total_orders < Config.FRAUD_MIN_ORDERS_FOR_DISPUTE_CHECK:
                return None
            
            total_disputes = await disputes.count_documents({"seller_id": user_id})
            dispute_rate = (total_disputes / total_orders) * 100
            
            if dispute_rate > Config.FRAUD_HIGH_DISPUTE_RATE_THRESHOLD:
                return {
                    "type": FraudEventType.HIGH_DISPUTE_RATE.value,
                    "risk_level": FraudRiskLevel.HIGH.value if dispute_rate > 30 else FraudRiskLevel.MEDIUM.value,
                    "details": {
                        "dispute_rate": round(dispute_rate, 2),
                        "total_orders": total_orders,
                        "total_disputes": total_disputes
                    },
                    "message": f"אחוז מחלוקות גבוה: {dispute_rate:.1f}%"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking dispute rate for user {user_id}: {e}")
            return None

    @staticmethod
    async def _check_high_refund_rate(user_id: int) -> Optional[Dict[str, Any]]:
        """בדיקת אחוז החזרים חריג (כקונה)"""
        try:
            orders = await database.get_orders_collection()
            
            total_purchases = await orders.count_documents({"buyer_id": user_id})
            if total_purchases < Config.FRAUD_MIN_ORDERS_FOR_REFUND_CHECK:
                return None
            
            refunded_orders = await orders.count_documents({
                "buyer_id": user_id,
                "status": "refunded"
            })
            
            refund_rate = (refunded_orders / total_purchases) * 100
            
            if refund_rate > Config.FRAUD_HIGH_REFUND_RATE_THRESHOLD:
                return {
                    "type": FraudEventType.HIGH_REFUND_RATE.value,
                    "risk_level": FraudRiskLevel.MEDIUM.value,
                    "details": {
                        "refund_rate": round(refund_rate, 2),
                        "total_purchases": total_purchases,
                        "refunded_orders": refunded_orders
                    },
                    "message": f"אחוז החזרים חריג: {refund_rate:.1f}%"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking refund rate for user {user_id}: {e}")
            return None

    @staticmethod
    async def _check_rapid_activity(user_id: int) -> Optional[Dict[str, Any]]:
        """בדיקת פעילות מהירה מדי (הרבה עסקאות בזמן קצר)"""
        try:
            orders = await database.get_orders_collection()
            coupons = await database.get_coupons_collection()
            
            time_window = datetime.utcnow() - timedelta(hours=1)
            
            # בדיקת עסקאות כמוכר
            recent_sales = await orders.count_documents({
                "seller_id": user_id,
                "created_at": {"$gte": time_window}
            })
            
            # בדיקת קופונים שהועלו
            recent_coupons = await coupons.count_documents({
                "seller_id": user_id,
                "created_at": {"$gte": time_window}
            })
            
            # בדיקת עסקאות כקונה
            recent_purchases = await orders.count_documents({
                "buyer_id": user_id,
                "created_at": {"$gte": time_window}
            })
            
            if recent_sales > Config.FRAUD_RAPID_SALES_THRESHOLD or \
               recent_coupons > Config.FRAUD_RAPID_COUPONS_THRESHOLD or \
               recent_purchases > Config.FRAUD_RAPID_PURCHASES_THRESHOLD:
                return {
                    "type": FraudEventType.RAPID_ACTIVITY.value,
                    "risk_level": FraudRiskLevel.MEDIUM.value,
                    "details": {
                        "recent_sales": recent_sales,
                        "recent_coupons": recent_coupons,
                        "recent_purchases": recent_purchases,
                        "time_window_hours": 1
                    },
                    "message": f"פעילות מהירה מדי: {recent_sales} מכירות, {recent_coupons} קופונים, {recent_purchases} רכישות בשעה"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking rapid activity for user {user_id}: {e}")
            return None

    @staticmethod
    async def _check_low_trust_score(user_id: int) -> Optional[Dict[str, Any]]:
        """בדיקת ניקוד אמינות נמוך"""
        try:
            trust_score = await FraudDetectionService.get_trust_score(user_id)
            
            if trust_score < Config.FRAUD_LOW_TRUST_SCORE_THRESHOLD:
                return {
                    "type": FraudEventType.LOW_TRUST_SCORE.value,
                    "risk_level": FraudRiskLevel.LOW.value if trust_score >= 10 else FraudRiskLevel.MEDIUM.value,
                    "details": {
                        "trust_score": trust_score
                    },
                    "message": f"ניקוד אמינות נמוך: {trust_score}"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking trust score for user {user_id}: {e}")
            return None

    # === בדיקות קופונים ===

    @staticmethod
    async def check_duplicate_coupon(digital_code: str, seller_id: int, exclude_coupon_id: ObjectId = None) -> Optional[Dict[str, Any]]:
        """בדיקת קופון כפול (אותו קוד דיגיטלי)"""
        try:
            coupons = await database.get_coupons_collection()
            
            query = {
                "digital_code": digital_code,
                "status": {"$in": ["active", "sold"]}
            }
            
            if exclude_coupon_id:
                query["_id"] = {"$ne": exclude_coupon_id}
            
            existing = await coupons.find_one(query)
            
            if existing:
                return {
                    "type": FraudEventType.DUPLICATE_COUPON.value,
                    "risk_level": FraudRiskLevel.HIGH.value,
                    "details": {
                        "existing_coupon_id": str(existing["_id"]),
                        "existing_seller_id": existing["seller_id"],
                        "new_seller_id": seller_id
                    },
                    "message": "קוד קופון כפול - ייתכן שהקופון כבר נמכר או שמישהו מנסה למכור אותו שוב"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking duplicate coupon: {e}")
            return None

    @staticmethod
    async def check_suspicious_pricing(
        original_price: float, 
        sale_price: float, 
        category: str
    ) -> Optional[Dict[str, Any]]:
        """בדיקת מחיר חשוד (הנחה גבוהה מדי או מחיר נמוך מדי)"""
        try:
            # חישוב אחוז הנחה
            if original_price <= 0:
                return {
                    "type": FraudEventType.SUSPICIOUS_PRICING.value,
                    "risk_level": FraudRiskLevel.HIGH.value,
                    "details": {"original_price": original_price},
                    "message": "מחיר מקורי לא תקין"
                }
            
            discount_pct = ((original_price - sale_price) / original_price) * 100
            
            # הנחה גבוהה מדי (מעל 90%)
            if discount_pct > Config.FRAUD_MAX_DISCOUNT_PERCENTAGE:
                return {
                    "type": FraudEventType.SUSPICIOUS_PRICING.value,
                    "risk_level": FraudRiskLevel.MEDIUM.value,
                    "details": {
                        "original_price": original_price,
                        "sale_price": sale_price,
                        "discount_percentage": round(discount_pct, 2)
                    },
                    "message": f"הנחה חשודה: {discount_pct:.0f}%"
                }
            
            # מחיר נמוך מדי (פחות מ-5 ש"ח)
            if sale_price < Config.FRAUD_MIN_SALE_PRICE:
                return {
                    "type": FraudEventType.SUSPICIOUS_PRICING.value,
                    "risk_level": FraudRiskLevel.LOW.value,
                    "details": {
                        "sale_price": sale_price,
                        "min_price": Config.FRAUD_MIN_SALE_PRICE
                    },
                    "message": f"מחיר נמוך מדי: {sale_price}₪"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking suspicious pricing: {e}")
            return None

    @staticmethod
    async def check_large_transaction(amount: float) -> Optional[Dict[str, Any]]:
        """בדיקת עסקה גדולה (מעל 500₪)"""
        if amount > Config.FRAUD_LARGE_TRANSACTION_THRESHOLD:
            return {
                "type": FraudEventType.LARGE_TRANSACTION.value,
                "risk_level": FraudRiskLevel.LOW.value,
                "details": {
                    "amount": amount,
                    "threshold": Config.FRAUD_LARGE_TRANSACTION_THRESHOLD
                },
                "message": f"עסקה גדולה: {amount:.2f}₪ - דורש אימות נוסף"
            }
        return None

    @staticmethod
    async def check_new_seller_rate_limit(seller_id: int) -> Optional[Dict[str, Any]]:
        """בדיקת הגבלת קצב למוכרים חדשים"""
        try:
            users = await database.get_users_collection()
            coupons = await database.get_coupons_collection()
            
            user = await users.find_one({"user_id": seller_id})
            if not user:
                return None
            
            created_at = user.get("created_at", datetime.utcnow())
            account_age_days = (datetime.utcnow() - created_at).days
            
            # מוכר חדש = פחות מ-30 יום
            if account_age_days >= Config.FRAUD_NEW_SELLER_DAYS:
                return None
            
            # ספירת קופונים היום
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_coupons = await coupons.count_documents({
                "seller_id": seller_id,
                "created_at": {"$gte": today_start}
            })
            
            if today_coupons >= Config.FRAUD_NEW_SELLER_DAILY_LIMIT:
                return {
                    "type": FraudEventType.NEW_SELLER_LIMIT.value,
                    "risk_level": FraudRiskLevel.LOW.value,
                    "details": {
                        "account_age_days": account_age_days,
                        "today_coupons": today_coupons,
                        "daily_limit": Config.FRAUD_NEW_SELLER_DAILY_LIMIT
                    },
                    "message": f"הגבלת מוכר חדש: {today_coupons}/{Config.FRAUD_NEW_SELLER_DAILY_LIMIT} קופונים היום"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking new seller rate limit: {e}")
            return None

    # === פעולות אוטומטיות ===

    @staticmethod
    async def auto_block_if_needed(user_id: int) -> bool:
        """
        חסימה אוטומטית אם מתקיימים תנאים
        Returns: True אם המשתמש נחסם
        """
        try:
            red_flags = await FraudDetectionService.detect_suspicious_activity(user_id)
            
            # ספירת דגלים קריטיים וגבוהים
            critical_count = sum(1 for f in red_flags if f.get("risk_level") == FraudRiskLevel.CRITICAL.value)
            high_count = sum(1 for f in red_flags if f.get("risk_level") == FraudRiskLevel.HIGH.value)
            
            should_block = critical_count > 0 or high_count >= 2
            
            if should_block:
                users = await database.get_users_collection()
                result = await users.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "blocked": True,
                            "blocked_at": datetime.utcnow(),
                            "blocked_reason": "auto_fraud_detection",
                            "auto_blocked": True
                        }
                    }
                )
                
                if result.modified_count > 0:
                    # לוג האירוע
                    await FraudDetectionService.log_fraud_event(
                        user_id=user_id,
                        event_type=FraudEventType.AUTO_BLOCK,
                        details={"red_flags": red_flags},
                        risk_level=FraudRiskLevel.CRITICAL
                    )
                    
                    # התראה לאדמינים
                    await FraudDetectionService.alert_admins(
                        title="🚨 חסימה אוטומטית",
                        message=f"משתמש {user_id} נחסם אוטומטית עקב פעילות חשודה",
                        user_id=user_id,
                        red_flags=red_flags
                    )
                    
                    logger.warning(f"Auto-blocked user {user_id} due to fraud detection")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in auto_block_if_needed for user {user_id}: {e}")
            return False

    @staticmethod
    async def log_fraud_event(
        user_id: int,
        event_type: FraudEventType,
        details: Dict[str, Any],
        risk_level: FraudRiskLevel = FraudRiskLevel.LOW
    ) -> Optional[str]:
        """שמירת לוג אירוע הונאה"""
        try:
            await database._ensure_connected()
            fraud_logs = database.db.fraud_logs
            
            log_data = {
                "user_id": user_id,
                "event_type": event_type.value if isinstance(event_type, FraudEventType) else event_type,
                "risk_level": risk_level.value if isinstance(risk_level, FraudRiskLevel) else risk_level,
                "details": details,
                "created_at": datetime.utcnow(),
                "reviewed": False,
                "reviewed_by": None,
                "reviewed_at": None
            }
            
            result = await fraud_logs.insert_one(log_data)
            logger.info(f"Fraud event logged: {event_type} for user {user_id}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error logging fraud event: {e}")
            return None

    @staticmethod
    async def alert_admins(
        title: str,
        message: str,
        user_id: int,
        red_flags: List[Dict[str, Any]] = None
    ):
        """שליחת התראה לאדמינים על פעילות חשודה"""
        try:
            from telegram import Bot
            bot = Bot(Config.BOT_TOKEN)
            
            # יצירת טקסט ההתראה
            flags_text = ""
            if red_flags:
                flags_text = "\n\n*דגלים אדומים:*\n"
                for flag in red_flags:
                    risk_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                        flag.get("risk_level", "low"), "⚪"
                    )
                    flags_text += f"{risk_emoji} {flag.get('message', 'לא ידוע')}\n"
            
            full_message = f"🔔 *{title}*\n\n{message}\n\n👤 User ID: `{user_id}`{flags_text}"
            
            for admin_id in Config.ADMIN_IDS:
                try:
                    from keyboards import Keyboards
                    keyboard = Keyboards.fraud_alert_keyboard(user_id)
                    await bot.send_message(
                        admin_id,
                        full_message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.warning(f"Failed to send fraud alert to admin {admin_id}: {e}")
            
            logger.info(f"Fraud alert sent to admins about user {user_id}")
            
        except Exception as e:
            logger.error(f"Error alerting admins: {e}")

    # === דוחות וסטטיסטיקות ===

    @staticmethod
    async def get_fraud_stats() -> Dict[str, Any]:
        """קבלת סטטיסטיקות הונאה"""
        try:
            await database._ensure_connected()
            fraud_logs = database.db.fraud_logs
            users = await database.get_users_collection()
            
            # סטטיסטיקות כלליות
            total_events = await fraud_logs.count_documents({})
            unreviewed_events = await fraud_logs.count_documents({"reviewed": False})
            blocked_users = await users.count_documents({"blocked": True, "auto_blocked": True})
            
            # אירועים לפי סוג
            pipeline = [
                {"$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1}
                }}
            ]
            events_by_type = {}
            async for doc in fraud_logs.aggregate(pipeline):
                events_by_type[doc["_id"]] = doc["count"]
            
            # אירועים לפי רמת סיכון
            pipeline = [
                {"$group": {
                    "_id": "$risk_level",
                    "count": {"$sum": 1}
                }}
            ]
            events_by_risk = {}
            async for doc in fraud_logs.aggregate(pipeline):
                events_by_risk[doc["_id"]] = doc["count"]
            
            # אירועים ב-24 שעות אחרונות
            recent_time = datetime.utcnow() - timedelta(hours=24)
            recent_events = await fraud_logs.count_documents({
                "created_at": {"$gte": recent_time}
            })
            
            return {
                "total_events": total_events,
                "unreviewed_events": unreviewed_events,
                "blocked_users": blocked_users,
                "events_by_type": events_by_type,
                "events_by_risk": events_by_risk,
                "recent_events_24h": recent_events
            }
            
        except Exception as e:
            logger.error(f"Error getting fraud stats: {e}")
            return {}

    @staticmethod
    async def get_pending_reviews(limit: int = 20) -> List[Dict[str, Any]]:
        """קבלת אירועים הממתינים לבדיקה"""
        try:
            await database._ensure_connected()
            fraud_logs = database.db.fraud_logs
            
            cursor = fraud_logs.find({
                "reviewed": False
            }).sort([
                ("risk_level", -1),  # קריטי קודם
                ("created_at", -1)   # חדש קודם
            ]).limit(limit)
            
            return await cursor.to_list(length=None)
            
        except Exception as e:
            logger.error(f"Error getting pending reviews: {e}")
            return []

    @staticmethod
    async def mark_as_reviewed(
        log_id: str,
        admin_id: int,
        notes: Optional[str] = None
    ) -> bool:
        """סימון אירוע כנבדק"""
        try:
            await database._ensure_connected()
            fraud_logs = database.db.fraud_logs
            
            result = await fraud_logs.update_one(
                {"_id": ObjectId(log_id)},
                {
                    "$set": {
                        "reviewed": True,
                        "reviewed_by": admin_id,
                        "reviewed_at": datetime.utcnow(),
                        "review_notes": notes
                    }
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error marking fraud log as reviewed: {e}")
            return False

    @staticmethod
    async def get_user_fraud_history(user_id: int) -> List[Dict[str, Any]]:
        """קבלת היסטוריית אירועי הונאה של משתמש"""
        try:
            await database._ensure_connected()
            fraud_logs = database.db.fraud_logs
            
            cursor = fraud_logs.find({
                "user_id": user_id
            }).sort("created_at", -1).limit(50)
            
            return await cursor.to_list(length=None)
            
        except Exception as e:
            logger.error(f"Error getting fraud history for user {user_id}: {e}")
            return []

    # === בדיקות תקופתיות ===

    @staticmethod
    async def run_periodic_checks():
        """הרצת בדיקות תקופתיות על כל המוכרים הפעילים"""
        try:
            users = await database.get_users_collection()
            
            # מציאת מוכרים פעילים
            sellers = await users.find({
                "role": {"$in": ["seller_verified", "seller_unverified"]},
                "blocked": {"$ne": True}
            }).to_list(length=None)
            
            checked = 0
            flagged = 0
            blocked = 0
            
            for seller in sellers:
                user_id = seller["user_id"]
                
                # עדכון ניקוד אמינות
                await FraudDetectionService.calculate_trust_score(user_id)
                
                # בדיקת פעילות חשודה
                red_flags = await FraudDetectionService.detect_suspicious_activity(user_id)
                
                if red_flags:
                    flagged += 1
                    
                    # לוג אירוע
                    for flag in red_flags:
                        await FraudDetectionService.log_fraud_event(
                            user_id=user_id,
                            event_type=FraudEventType(flag["type"]),
                            details=flag.get("details", {}),
                            risk_level=FraudRiskLevel(flag.get("risk_level", "low"))
                        )
                    
                    # בדיקה אם צריך לחסום
                    if await FraudDetectionService.auto_block_if_needed(user_id):
                        blocked += 1
                
                checked += 1
            
            logger.info(f"Periodic fraud check completed: {checked} checked, {flagged} flagged, {blocked} blocked")
            
            return {
                "checked": checked,
                "flagged": flagged,
                "blocked": blocked
            }
            
        except Exception as e:
            logger.error(f"Error in periodic fraud checks: {e}")
            return {"error": str(e)}

    @staticmethod
    async def check_all_duplicate_coupons():
        """בדיקת קופונים כפולים במערכת"""
        try:
            coupons = await database.get_coupons_collection()
            
            # מציאת קודים כפולים
            pipeline = [
                {"$match": {"status": {"$in": ["active", "sold"]}, "digital_code": {"$exists": True, "$ne": None}}},
                {"$group": {
                    "_id": "$digital_code",
                    "count": {"$sum": 1},
                    "coupons": {"$push": {"id": "$_id", "seller_id": "$seller_id", "title": "$title"}}
                }},
                {"$match": {"count": {"$gt": 1}}}
            ]
            
            duplicates = await coupons.aggregate(pipeline).to_list(length=None)
            
            for dup in duplicates:
                for coupon_info in dup["coupons"]:
                    await FraudDetectionService.log_fraud_event(
                        user_id=coupon_info["seller_id"],
                        event_type=FraudEventType.DUPLICATE_COUPON,
                        details={
                            "digital_code": dup["_id"],
                            "coupon_id": str(coupon_info["id"]),
                            "duplicate_count": dup["count"]
                        },
                        risk_level=FraudRiskLevel.HIGH
                    )
            
            logger.info(f"Duplicate coupon check completed: {len(duplicates)} duplicates found")
            return len(duplicates)
            
        except Exception as e:
            logger.error(f"Error checking duplicate coupons: {e}")
            return 0
