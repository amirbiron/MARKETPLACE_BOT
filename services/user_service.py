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
    async def get_user(user_id: int) -> Optional[User]:
        """קבלת משתמש לפי ID"""
        users = await database.get_users_collection()
        user_data = await users.find_one({"user_id": user_id})
        
        if user_data:
            return User.from_dict(user_data)
        return None
    
    @staticmethod
    async def create_user(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        role: UserRole = UserRole.BUYER
    ) -> User:
        """יצירת משתמש חדש"""
        users = await database.get_users_collection()
        
        # בדיקה אם המשתמש כבר קיים
        existing = await users.find_one({"user_id": user_id})
        if existing:
            logger.info(f"User {user_id} already exists")
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
            {"user_id": user_id},
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
        user_data = await users.find_one({"user_id": user_id})
        
        if not user_data:
            return False
        
        available_balance = user_data.get("balance", 0) - user_data.get("frozen_balance", 0)
        
        if available_balance < amount:
            logger.warning(f"Insufficient balance for user {user_id}: {available_balance}₪ < {amount}₪")
            return False
        
        result = await users.update_one(
            {"user_id": user_id},
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
            {"user_id": user_id},
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
        id_number: Optional[str] = None
    ) -> bool:
        """עדכון פרטי מוכר"""
        users = await database.get_users_collection()
        
        update_data = {
            "business_name": business_name,
            "phone": phone,
        }
        
        # אם יש ת.ז, זה מוכר מאומת
        if id_number:
            update_data["id_number"] = id_number
            update_data["role"] = UserRole.SELLER_VERIFIED.value
            update_data["is_verified"] = True
        else:
            update_data["role"] = UserRole.SELLER_UNVERIFIED.value
            update_data["is_verified"] = False
        
        result = await users.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            verified_str = "verified" if id_number else "unverified"
            logger.info(f"Updated seller info for user {user_id} ({verified_str})")
            return True
        return False
    
    @staticmethod
    async def update_seller_rating(seller_id: int, new_rating: int) -> bool:
        """עדכון דירוג מוכר"""
        users = await database.get_users_collection()
        user_data = await users.find_one({"user_id": seller_id})
        
        if not user_data:
            return False
        
        current_avg = user_data.get("rating_average", 0.0)
        current_count = user_data.get("rating_count", 0)
        
        # חישוב ממוצע חדש
        new_count = current_count + 1
        new_avg = ((current_avg * current_count) + new_rating) / new_count
        
        result = await users.update_one(
            {"user_id": seller_id},
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
            {"user_id": user_id},
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
            {"user_id": user_id},
            {"$set": {"notifications_enabled": enabled}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated notifications for user {user_id}: {enabled}")
            return True
        return False
