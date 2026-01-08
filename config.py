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
    
    # === Escrow Settings ===
    
    ESCROW_RELEASE_HOURS: int = 24  # שעות המתנה לשחרור אוטומטי למוכר
    ESCROW_AUTO_RELEASE_ENABLED: bool = True  # האם לשחרר אוטומטית
    ESCROW_DISPUTE_EXTENSION_HOURS: int = 48  # הארכה במקרה של מחלוקת
    ESCROW_MIN_AMOUNT: float = 1.0  # מינימום סכום ל-escrow
    
    # === Anti-Fraud Settings ===
    
    # Trust Score Thresholds
    FRAUD_LOW_TRUST_SCORE_THRESHOLD: int = 20  # ניקוד אמינות מתחתיו נדלקת התראה
    
    # Dispute/Refund Rate Thresholds
    FRAUD_HIGH_DISPUTE_RATE_THRESHOLD: float = 20.0  # אחוז מחלוקות שמעליו זה חשוד
    FRAUD_HIGH_REFUND_RATE_THRESHOLD: float = 30.0  # אחוז החזרים חריג (כקונה)
    FRAUD_MIN_ORDERS_FOR_DISPUTE_CHECK: int = 5  # מינימום הזמנות לבדיקת אחוז מחלוקות
    FRAUD_MIN_ORDERS_FOR_REFUND_CHECK: int = 5  # מינימום רכישות לבדיקת אחוז החזרים
    
    # Rapid Activity Thresholds (per hour)
    FRAUD_RAPID_SALES_THRESHOLD: int = 20  # מכירות לשעה
    FRAUD_RAPID_COUPONS_THRESHOLD: int = 15  # קופונים חדשים לשעה
    FRAUD_RAPID_PURCHASES_THRESHOLD: int = 10  # רכישות לשעה
    
    # Pricing Thresholds
    FRAUD_MAX_DISCOUNT_PERCENTAGE: float = 90.0  # הנחה מקסימלית לפני התראה
    FRAUD_MIN_SALE_PRICE: float = 5.0  # מחיר מינימלי לקופון
    
    # Large Transaction Threshold
    FRAUD_LARGE_TRANSACTION_THRESHOLD: float = 500.0  # עסקה שדורשת אימות נוסף
    
    # New Seller Limits
    FRAUD_NEW_SELLER_DAYS: int = 30  # ימים שמוכר נחשב "חדש"
    FRAUD_NEW_SELLER_DAILY_LIMIT: int = 5  # הגבלת קופונים יומית למוכר חדש
    
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
