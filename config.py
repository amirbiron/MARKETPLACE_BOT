"""
קובץ הגדרות למערכת Marketplace Bot
"""
import os
from dotenv import load_dotenv
from typing import List

# טעינת משתני סביבה
load_dotenv()

class Config:
    """הגדרות כלליות למערכת"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "marketplace_bot")
    
    # Admin Configuration
    ADMIN_IDS: List[int] = [
        int(uid.strip()) 
        for uid in os.getenv("ADMIN_IDS", "").split(",") 
        if uid.strip()
    ]
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    
    # Marketplace Settings
    BUYER_COMMISSION: float = 0.02  # 2% עמלת קונה
    VERIFIED_SELLER_COMMISSION: float = 0.03  # 3% מוכר מאומת
    UNVERIFIED_SELLER_COMMISSION: float = 0.05  # 5% מוכר לא מאומת
    WITHDRAWAL_COMMISSION: float = 0.01  # 1% עמלת משיכה
    MIN_WITHDRAWAL_AMOUNT: int = 200  # מינימום 200₪ למשיכה
    BALANCE_FREEZE_HOURS: int = 24  # הקפאת כספים למוכר
    REPORT_WINDOW_HOURS: int = 12  # חלון דיווח לקונה
    DAILY_COUPON_LIMIT_UNVERIFIED: int = 10  # הגבלת קופונים ליום (לא מאומת)
    
    # Pagination
    ITEMS_PER_PAGE: int = 5  # פריטים לעמוד בדפדוף
    REVIEWS_PER_PAGE: int = 5  # ביקורות לעמוד
    
    @classmethod
    def validate(cls) -> bool:
        """בדיקת תקינות ההגדרות"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not cls.MONGODB_URI:
            raise ValueError("MONGODB_URI is required")
        return True


# וידוא תקינות ההגדרות בטעינה
Config.validate()
