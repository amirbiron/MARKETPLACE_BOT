"""
שירות ניהול משתמשים
"""
from typing import Optional
from bson import ObjectId
import database
from models import User, UserRole
import logging

logger = logging.getLogger(__name__)


class UserService:
    """שירות לניהול משתמשים"""

    @staticmethod
    async def _find_user_doc(user_id: int) -> Optional[dict]:
        """
        מציאת מסמך משתמש בצורה תואמת לאחור.

        בקוד הנוכחי המפתח הראשי הוא `user_id` (Telegram ID).
        בגרסאות ישנות ייתכן שהמפתח נשמר בשדה `telegram_id`.
        """
        users = await database.get_users_collection()
        user_data = await users.find_one({"user_id": user_id})
        if user_data:
            return user_data
        # Backward compatibility (legacy schema)
        return await users.find_one({"telegram_id": user_id})

    @staticmethod
    def _user_selector(user_id: int) -> dict:
        """Selector that matches both new and legacy schemas."""
        return {"$or": [{"user_id": user_id}, {"telegram_id": user_id}]}

    @staticmethod
    def _normalize_role_from_doc(doc: Optional[dict]) -> UserRole:
        """Normalize any legacy role strings to current UserRole."""
        if not doc:
            return UserRole.BUYER

        role_val = doc.get("role", UserRole.BUYER.value)
        try:
            return UserRole(role_val)
        except Exception:
            # legacy mapping
            if role_val == "seller":
                is_verified = bool(doc.get("is_verified")) or bool(doc.get("verified")) or bool(doc.get("id_number"))
                return UserRole.SELLER_VERIFIED if is_verified else UserRole.SELLER_UNVERIFIED
            if str(role_val).lower() in {"admin", "administrator"}:
                return UserRole.ADMIN
            return UserRole.BUYER

    @staticmethod
    def _role_priority(role: UserRole) -> int:
        """Higher means more privileges/should win in merges."""
        return {
            UserRole.BUYER: 0,
            UserRole.SELLER_UNVERIFIED: 10,
            UserRole.SELLER_VERIFIED: 20,
            UserRole.ADMIN: 100,
        }.get(role, 0)
    
    @staticmethod
    async def get_user(user_id: int) -> Optional[User]:
        """קבלת משתמש לפי ID"""
        users = await database.get_users_collection()
        primary = await users.find_one({"user_id": user_id})
        legacy = await users.find_one({"telegram_id": user_id})

        if not primary and not legacy:
            return None

        # If we only have legacy, try to migrate it to the primary key.
        if not primary and legacy:
            legacy_updates = {"user_id": user_id}
            if "verified" in legacy and "is_verified" not in legacy:
                legacy_updates["is_verified"] = bool(legacy.get("verified"))
            if legacy.get("role") == "seller":
                norm = UserService._normalize_role_from_doc(legacy)
                legacy_updates["role"] = norm.value
            try:
                await users.update_one({"_id": legacy["_id"]}, {"$set": legacy_updates})
            except Exception:
                pass
            primary = await users.find_one({"user_id": user_id})

        # If we have both (duplicate docs), reconcile so user doesn't "fall back" to buyer.
        if primary and legacy and legacy.get("_id") != primary.get("_id"):
            updates: dict = {}

            primary_role = UserService._normalize_role_from_doc(primary)
            legacy_role = UserService._normalize_role_from_doc(legacy)

            # Ensure higher privilege role wins (e.g. seller shouldn't become buyer).
            if UserService._role_priority(legacy_role) > UserService._role_priority(primary_role):
                updates["role"] = legacy_role.value

            # Verification should not be lost if either doc indicates it.
            primary_verified = bool(primary.get("is_verified")) or bool(primary.get("verified")) or bool(primary.get("id_number"))
            legacy_verified = bool(legacy.get("is_verified")) or bool(legacy.get("verified")) or bool(legacy.get("id_number"))
            if legacy_verified and not primary_verified:
                updates["is_verified"] = True
                if legacy.get("id_number") and not primary.get("id_number"):
                    updates["id_number"] = legacy.get("id_number")
                # If we became verified, ensure role reflects it (unless admin).
                merged_role = UserService._normalize_role_from_doc({**primary, **updates})
                if merged_role != UserRole.ADMIN and merged_role == UserRole.SELLER_UNVERIFIED:
                    updates["role"] = UserRole.SELLER_VERIFIED.value

            # Copy seller identity fields if missing in primary (helps menus/profile)
            for field in ("business_name", "commercial_name", "phone", "seller_status"):
                if not primary.get(field) and legacy.get(field):
                    updates[field] = legacy.get(field)

            # Keep the higher rating count if legacy has more
            try:
                if int(legacy.get("rating_count", 0) or 0) > int(primary.get("rating_count", 0) or 0):
                    updates["rating_count"] = legacy.get("rating_count", 0)
                    updates["rating_average"] = legacy.get("rating_average", primary.get("rating_average", 0.0))
            except Exception:
                pass

            if updates:
                try:
                    await users.update_one({"_id": primary["_id"]}, {"$set": updates})
                    primary = await users.find_one({"_id": primary["_id"]}) or primary
                except Exception:
                    pass

        user_data = primary or legacy
        return User.from_dict(user_data)
    
    @staticmethod
    async def create_user(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        role: UserRole = UserRole.BUYER
    ) -> User:
        """יצירת משתמש חדש"""
        users = await database.get_users_collection()
        
        # בדיקה אם המשתמש כבר קיים (תואם לאחור גם ל-telegram_id)
        existing = await UserService._find_user_doc(user_id)
        if existing:
            logger.info(f"User {user_id} already exists")
            # Best-effort migrate legacy telegram_id->user_id
            if existing.get("telegram_id") == user_id and not existing.get("user_id"):
                try:
                    await users.update_one({"_id": existing["_id"]}, {"$set": {"user_id": user_id}})
                    existing = await users.find_one({"user_id": user_id}) or existing
                except Exception:
                    pass
            return User.from_dict(existing)
        
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            role=role
        )
        
        result = await users.insert_one(user.to_dict())
        user._id = result.inserted_id
        
        logger.info(f"Created new user: {user_id} ({role.value})")
        return user
    
    @staticmethod
    async def update_user_balance(user_id: int, amount: float) -> bool:
        """עדכון יתרת משתמש"""
        users = await database.get_users_collection()
        
        result = await users.update_one(
            UserService._user_selector(user_id),
            {"$inc": {"balance": amount}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated balance for user {user_id}: {amount:+.2f}₪")
            return True
        return False
    
    @staticmethod
    async def freeze_balance(user_id: int, amount: float) -> bool:
        """הקפאת יתרה (למכרזים)"""
        users = await database.get_users_collection()
        user_data = await users.find_one(UserService._user_selector(user_id))
        
        if not user_data:
            return False
        
        available_balance = user_data.get("balance", 0) - user_data.get("frozen_balance", 0)
        
        if available_balance < amount:
            logger.warning(f"Insufficient balance for user {user_id}: {available_balance}₪ < {amount}₪")
            return False
        
        result = await users.update_one(
            UserService._user_selector(user_id),
            {"$inc": {"frozen_balance": amount}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Frozen {amount}₪ for user {user_id}")
            return True
        return False
    
    @staticmethod
    async def unfreeze_balance(user_id: int, amount: float) -> bool:
        """שחרור יתרה מוקפאת"""
        users = await database.get_users_collection()
        
        result = await users.update_one(
            UserService._user_selector(user_id),
            {"$inc": {"frozen_balance": -amount}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Unfroze {amount}₪ for user {user_id}")
            return True
        return False
    
    @staticmethod
    async def get_available_balance(user_id: int) -> float:
        """קבלת יתרה זמינה (לא כולל קפואה)"""
        user = await UserService.get_user(user_id)
        if user:
            return user.balance - user.frozen_balance
        return 0.0
    
    @staticmethod
    async def update_seller_info(
        user_id: int,
        business_name: str,
        phone: str,
        id_number: Optional[str] = None,
        commercial_name: Optional[str] = None,
        seller_status: Optional[str] = None
    ) -> bool:
        """עדכון פרטי מוכר"""
        users = await database.get_users_collection()

        # Load current user to avoid accidentally downgrading verified sellers
        current = await UserService._find_user_doc(user_id)
        
        update_data = {
            "business_name": business_name,
            "phone": phone,
        }
        
        # שם מסחרי
        if commercial_name:
            update_data["commercial_name"] = commercial_name
        
        # סטטוס אישור מוכר
        if seller_status:
            update_data["seller_status"] = seller_status
        
        # קביעת סטטוס אימות בצורה שלא "תדרוס" מוכר מאומת קיימת:
        # - אם נשלחה ת.ז כעת -> מאומת
        # - אחרת, אם קיימת ת.ז/אימות כבר במסד -> נשמור מאומת
        # - אחרת -> לא מאומת
        has_existing_id = bool(current.get("id_number")) if current else False
        has_existing_verified = bool(current.get("is_verified")) if current else False

        if id_number:
            update_data["id_number"] = id_number
            update_data["is_verified"] = True
            update_data["role"] = UserRole.SELLER_VERIFIED.value
        elif has_existing_id or has_existing_verified:
            # Preserve verified seller state if already verified
            update_data["is_verified"] = True
            update_data["role"] = UserRole.SELLER_VERIFIED.value
        else:
            update_data["is_verified"] = False
            update_data["role"] = UserRole.SELLER_UNVERIFIED.value
        
        result = await users.update_one(UserService._user_selector(user_id), {"$set": update_data})
        
        if result.modified_count > 0:
            verified_str = "verified" if id_number else "unverified"
            logger.info(f"Updated seller info for user {user_id} ({verified_str})")
            return True
        return False
    
    @staticmethod
    async def approve_seller(user_id: int) -> bool:
        """אישור מוכר על ידי אדמין"""
        users = await database.get_users_collection()

        user_data = await users.find_one(UserService._user_selector(user_id))
        if not user_data:
            return False

        # קבע role אם המשתמש עדיין "buyer" (תאימות לאחור לנתונים ישנים)
        current_role = user_data.get("role", UserRole.BUYER.value)
        is_admin = current_role == UserRole.ADMIN.value
        is_verified = bool(user_data.get("is_verified")) or bool(user_data.get("id_number"))

        update_set = {"seller_status": "approved"}
        if not is_admin and current_role not in [UserRole.SELLER_VERIFIED.value, UserRole.SELLER_UNVERIFIED.value]:
            update_set["role"] = UserRole.SELLER_VERIFIED.value if is_verified else UserRole.SELLER_UNVERIFIED.value

        result = await users.update_one(UserService._user_selector(user_id), {"$set": update_set})

        if result.matched_count == 0:
            return False

        # גם אם לא שונה דבר (כבר אושר), נחשב הצלחה כדי לא "להפיל" את ה-flow.
        if result.modified_count > 0:
            logger.info(f"Approved seller {user_id}")
        else:
            logger.info(f"Seller {user_id} already approved (no changes)")
        return True
    
    @staticmethod
    async def reject_seller(user_id: int) -> bool:
        """דחיית בקשת מוכר על ידי אדמין"""
        # Backward compatible alias: "reject" == "block seller registration"
        return await UserService.block_seller(user_id)

    @staticmethod
    async def block_seller(user_id: int) -> bool:
        """חסימת בקשת מוכר (השבתה לרול buyer + סטטוס blocked)"""
        users = await database.get_users_collection()
        
        # החזרת המשתמש לסטטוס קונה רגיל
        result = await users.update_one(
            UserService._user_selector(user_id),
            {
                "$set": {
                    "seller_status": "blocked",
                    "role": UserRole.BUYER.value,
                    "is_verified": False,
                }
                # לא מוחקים פרטי עסק/טלפון כדי לשמור שקיפות לאדמינים (Audit).
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Blocked seller request {user_id}")
            return True
        return False
    
    @staticmethod
    async def get_pending_sellers() -> list:
        """קבלת רשימת מוכרים ממתינים לאישור"""
        users = await database.get_users_collection()
        
        cursor = users.find({
            "seller_status": "pending",
            "role": {"$in": [UserRole.SELLER_VERIFIED.value, UserRole.SELLER_UNVERIFIED.value]}
        }).sort("created_at", -1)
        
        return await cursor.to_list(length=None)
    
    @staticmethod
    async def update_seller_rating(seller_id: int, new_rating: int) -> bool:
        """עדכון דירוג מוכר"""
        users = await database.get_users_collection()
        user_data = await users.find_one(UserService._user_selector(seller_id))
        
        if not user_data:
            return False
        
        current_avg = user_data.get("rating_average", 0.0)
        current_count = user_data.get("rating_count", 0)
        
        # חישוב ממוצע חדש
        new_count = current_count + 1
        new_avg = ((current_avg * current_count) + new_rating) / new_count
        
        result = await users.update_one(
            UserService._user_selector(seller_id),
            {
                "$set": {
                    "rating_average": round(new_avg, 2),
                    "rating_count": new_count
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated rating for seller {seller_id}: {new_avg:.2f} ({new_count} reviews)")
            return True
        return False
    
    @staticmethod
    async def is_seller(user_id: int) -> bool:
        """בדיקה האם המשתמש הוא מוכר"""
        user = await UserService.get_user(user_id)
        if user:
            return user.role in [UserRole.SELLER_VERIFIED, UserRole.SELLER_UNVERIFIED]
        return False
    
    @staticmethod
    async def is_verified_seller(user_id: int) -> bool:
        """בדיקה האם המוכר מאומת"""
        user = await UserService.get_user(user_id)
        if user:
            return user.role == UserRole.SELLER_VERIFIED
        return False
    
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """בדיקה האם המשתמש הוא אדמין"""
        user = await UserService.get_user(user_id)
        if user:
            return user.role == UserRole.ADMIN
        return False
    
    @staticmethod
    async def set_admin(user_id: int) -> bool:
        """הגדרת משתמש כאדמין"""
        users = await database.get_users_collection()
        
        result = await users.update_one(
            UserService._user_selector(user_id),
            {"$set": {"role": UserRole.ADMIN.value}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Set user {user_id} as admin")
            return True
        return False
    
    @staticmethod
    async def update_notifications_setting(user_id: int, enabled: bool) -> bool:
        """עדכון הגדרת התראות"""
        users = await database.get_users_collection()
        
        result = await users.update_one(
            UserService._user_selector(user_id),
            {"$set": {"notifications_enabled": enabled}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated notifications for user {user_id}: {enabled}")
            return True
        return False
    
    # === Trust Score Methods ===
    
    @staticmethod
    async def get_trust_score(user_id: int) -> int:
        """קבלת ניקוד אמינות של משתמש"""
        from services.fraud_detection_service import FraudDetectionService
        return await FraudDetectionService.get_trust_score(user_id)
    
    @staticmethod
    async def update_trust_score(user_id: int) -> int:
        """עדכון וחישוב מחדש של ניקוד אמינות"""
        from services.fraud_detection_service import FraudDetectionService
        return await FraudDetectionService.calculate_trust_score(user_id)
    
    @staticmethod
    async def is_blocked(user_id: int) -> bool:
        """בדיקה האם המשתמש חסום"""
        users = await database.get_users_collection()
        user = await users.find_one({"user_id": user_id})
        
        if user:
            return user.get("blocked", False)
        return False
    
    @staticmethod
    async def block_user(user_id: int, reason: str = None, auto: bool = False) -> bool:
        """חסימת משתמש"""
        users = await database.get_users_collection()
        
        update_data = {
            "blocked": True,
            "blocked_at": database.datetime.utcnow() if hasattr(database, 'datetime') else __import__('datetime').datetime.utcnow(),
            "auto_blocked": auto
        }
        if reason:
            update_data["blocked_reason"] = reason
        
        result = await users.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"Blocked user {user_id} (auto={auto}): {reason}")
            return True
        return False
    
    @staticmethod
    async def unblock_user(user_id: int) -> bool:
        """ביטול חסימת משתמש"""
        users = await database.get_users_collection()
        
        result = await users.update_one(
            {"user_id": user_id},
            {
                "$set": {"blocked": False},
                "$unset": {"blocked_at": "", "blocked_reason": "", "auto_blocked": ""}
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Unblocked user {user_id}")
            return True
        return False
    
    @staticmethod
    async def get_blocked_users(limit: int = 50) -> list:
        """קבלת רשימת משתמשים חסומים"""
        users = await database.get_users_collection()
        
        cursor = users.find({"blocked": True}).sort("blocked_at", -1).limit(limit)
        return await cursor.to_list(length=None)
