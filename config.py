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
    BUYER_COMMISSION_RATE: float = 0.02  # 2% עמלת קונה
    BUYER_COMMISSION: float = 0.02  # Alias for BUYER_COMMISSION_RATE
    VERIFIED_SELLER_COMMISSION_RATE: float = 0.03  # 3% מוכר מאומת
    VERIFIED_SELLER_COMMISSION: float = 0.03  # Alias
    UNVERIFIED_SELLER_COMMISSION_RATE: float = 0.05  # 5% מוכר לא מאומת
    UNVERIFIED_SELLER_COMMISSION: float = 0.05  # Alias
    SELLER_COMMISSION_RATE: float = 0.04  # 4% עמלה כללית למוכר
    WITHDRAWAL_COMMISSION: float = 0.01  # 1% עמלת משיכה
    MIN_WITHDRAWAL_AMOUNT: int = 200  # מינימום 200₪ למשיכה
    MIN_PAYOUT_AMOUNT: int = 200  # מינימום למשיכה
    BALANCE_FREEZE_HOURS: int = 24  # הקפאת כספים למוכר
    REPORT_WINDOW_HOURS: int = 12  # חלון דיווח לקונה
    DISPUTE_WINDOW_HOURS: int = 12  # חלון זמן לפתיחת מחלוקת
    DAILY_COUPON_LIMIT_UNVERIFIED: int = 10  # הגבלת קופונים ליום (לא מאומת)

    # Auction Settings
    MIN_BID_INCREMENT: float = 5.0  # תוספת מינימלית להצעה במכרז

    # Pagination
    ITEMS_PER_PAGE: int = 5  # פריטים לעמוד בדפדוף
    REVIEWS_PER_PAGE: int = 5  # ביקורות לעמוד

    # Database
    DATABASE_NAME: str = MONGODB_DB_NAME
    
    # Payment Details - הגדרת פרטי תשלום
    MIN_DEPOSIT_AMOUNT: int = int(os.getenv("MIN_DEPOSIT_AMOUNT", "50"))  # מינימום הטענה
    BIT_PHONE: str = os.getenv("BIT_PHONE", "")  # מספר טלפון לביט
    PAYBOX_LINK: str = os.getenv("PAYBOX_LINK", "")  # לינק לפייבוקס
    BANK_NAME: str = os.getenv("BANK_NAME", "")  # שם הבנק
    BANK_BRANCH: str = os.getenv("BANK_BRANCH", "")  # מספר סניף
    BANK_ACCOUNT: str = os.getenv("BANK_ACCOUNT", "")  # מספר חשבון
    BANK_OWNER: str = os.getenv("BANK_OWNER", "")  # שם בעל החשבון
    
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
