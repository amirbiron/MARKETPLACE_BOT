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

    # === Admin Forum (Topics) Mirror for Buyer/Seller Chats ===
    # Optional: set to the forum group chat_id (usually starts with -100...)
    # When enabled, every buyer/seller message is mirrored to a dedicated topic,
    # and admins can reply from that topic and choose where the reply goes.
    ADMIN_FORUM_CHAT_ID: int = int(os.getenv("ADMIN_FORUM_CHAT_ID", "0") or "0")
    _ADMIN_FORUM_ENABLED_ENV = os.getenv("ADMIN_FORUM_ENABLED")
    ADMIN_FORUM_ENABLED: bool = (
        _ADMIN_FORUM_ENABLED_ENV.lower() == "true"
        if _ADMIN_FORUM_ENABLED_ENV is not None and _ADMIN_FORUM_ENABLED_ENV != ""
        else ADMIN_FORUM_CHAT_ID != 0
    )
    
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
    
    # === Payment Gateway Settings ===
    
    # Active payment gateway (tranzila, cardcom, payplus, meshulam)
    PAYMENT_GATEWAY: str = os.getenv("PAYMENT_GATEWAY", "tranzila")
    PAYMENT_GATEWAY_ENABLED: bool = os.getenv("PAYMENT_GATEWAY_ENABLED", "false").lower() == "true"
    
    # Tranzila Settings
    TRANZILA_TERMINAL: str = os.getenv("TRANZILA_TERMINAL", "")
    TRANZILA_PASSWORD: str = os.getenv("TRANZILA_PASSWORD", "")
    TRANZILA_API_URL: str = os.getenv("TRANZILA_API_URL", "https://secure5.tranzila.com/cgi-bin/tranzila71.cgi")
    
    # CardCom Settings
    CARDCOM_TERMINAL: str = os.getenv("CARDCOM_TERMINAL", "")
    CARDCOM_USERNAME: str = os.getenv("CARDCOM_USERNAME", "")
    CARDCOM_API_KEY: str = os.getenv("CARDCOM_API_KEY", "")
    CARDCOM_API_URL: str = os.getenv("CARDCOM_API_URL", "https://secure.cardcom.solutions/interface/ChargeToken.aspx")
    
    # PayPlus Settings
    PAYPLUS_API_KEY: str = os.getenv("PAYPLUS_API_KEY", "")
    PAYPLUS_SECRET_KEY: str = os.getenv("PAYPLUS_SECRET_KEY", "")
    PAYPLUS_TERMINAL_UID: str = os.getenv("PAYPLUS_TERMINAL_UID", "")
    PAYPLUS_API_URL: str = os.getenv("PAYPLUS_API_URL", "https://restapidev.payplus.co.il/api/v1.0")
    
    # Meshulam Settings
    MESHULAM_PAGE_CODE: str = os.getenv("MESHULAM_PAGE_CODE", "")
    MESHULAM_USER_ID: str = os.getenv("MESHULAM_USER_ID", "")
    MESHULAM_API_KEY: str = os.getenv("MESHULAM_API_KEY", "")
    MESHULAM_API_URL: str = os.getenv("MESHULAM_API_URL", "https://secure.meshulam.co.il/api")
    
    # Webhook Settings
    WEBHOOK_BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "")  # URL for payment callbacks
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")  # Secret for verifying webhooks
    
    # Payment Security Settings
    PAYMENT_3D_SECURE_ENABLED: bool = os.getenv("PAYMENT_3D_SECURE_ENABLED", "true").lower() == "true"
    DAILY_CARD_LIMIT: float = float(os.getenv("DAILY_CARD_LIMIT", "5000"))  # מקסימום יומי לכרטיס
    MAX_TRANSACTION_AMOUNT: float = float(os.getenv("MAX_TRANSACTION_AMOUNT", "2000"))  # מקסימום לעסקה בודדת
    MIN_CARD_PAYMENT: float = float(os.getenv("MIN_CARD_PAYMENT", "10"))  # מינימום תשלום בכרטיס
    PAYMENT_TIMEOUT_MINUTES: int = int(os.getenv("PAYMENT_TIMEOUT_MINUTES", "30"))  # זמן לתשלום
    
    # Saved Cards Settings
    ALLOW_SAVE_CARD: bool = os.getenv("ALLOW_SAVE_CARD", "true").lower() == "true"
    MAX_SAVED_CARDS_PER_USER: int = int(os.getenv("MAX_SAVED_CARDS_PER_USER", "5"))
    
    # Payout Settings (Automated Seller Payouts)
    AUTO_PAYOUT_ENABLED: bool = os.getenv("AUTO_PAYOUT_ENABLED", "false").lower() == "true"
    PAYOUT_COMMISSION: float = float(os.getenv("PAYOUT_COMMISSION", "0.01"))  # 1% עמלת משיכה
    MIN_AUTO_PAYOUT_AMOUNT: float = float(os.getenv("MIN_AUTO_PAYOUT_AMOUNT", "200"))
    PAYOUT_PROCESSING_DAYS: int = int(os.getenv("PAYOUT_PROCESSING_DAYS", "3"))  # ימי עסקים
    
    # PayPal Payout Settings (Optional)
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_MODE: str = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live
    
    # Payoneer Payout Settings (Optional)
    PAYONEER_PROGRAM_ID: str = os.getenv("PAYONEER_PROGRAM_ID", "")
    PAYONEER_API_KEY: str = os.getenv("PAYONEER_API_KEY", "")
    PAYONEER_API_URL: str = os.getenv("PAYONEER_API_URL", "https://api.sandbox.payoneer.com")
    
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
    
    # === Seller Dashboard Settings ===
    
    # Analytics
    DASHBOARD_DEFAULT_PERIOD: str = "month"  # תקופת ברירת מחדל לסטטיסטיקות
    DASHBOARD_MAX_TOP_PRODUCTS: int = 10  # מספר מוצרים מובילים להצגה
    DASHBOARD_GRAPH_POINTS: int = 30  # נקודות נתונים לגרף
    
    # Reports
    REPORTS_ENABLED: bool = True  # הפעלת דוחות
    REPORT_MAX_ROWS: int = 1000  # מקסימום שורות בדוח
    
    # Alerts
    SELLER_ALERTS_ENABLED: bool = True  # הפעלת התראות למוכרים
    DEFAULT_SALES_THRESHOLD: int = 10  # סף מכירות ברירת מחדל להתראה
    
    # Bulk Operations
    BULK_EDIT_MAX_ITEMS: int = 50  # מקסימום פריטים לעריכה מרובה
    BULK_PRICE_UPDATE_ENABLED: bool = True  # הפעלת עדכון מחיר מרובה
    
    # Scheduled Coupons
    SCHEDULED_COUPONS_ENABLED: bool = True  # הפעלת תזמון קופונים
    MAX_SCHEDULED_COUPONS: int = 20  # מקסימום קופונים מתוזמנים למוכר
    MIN_SCHEDULE_AHEAD_MINUTES: int = 30  # מינימום זמן לתזמון
    
    # Coupon Duplication
    COUPON_DUPLICATE_ENABLED: bool = True  # הפעלת שכפול קופונים
    
    # === Classifieds Model Settings (P2P / לוח מודעות) ===
    
    # מודל הרווח החדש - מוכרים בלבד מחזיקים קרדיט שירות
    CLASSIFIEDS_MODEL_ENABLED: bool = True  # הפעלת המודל החדש
    
    # קרדיט שירות למוכרים
    SELLER_MIN_BALANCE_FOR_PUBLISH: float = 10.0  # מינימום קרדיט לפרסום קופון
    SELLER_INITIAL_CREDIT_REQUIRED: float = 20.0  # קרדיט ראשוני נדרש להרשמה
    SELLER_COMMISSION_RATE_P2P: float = 0.05  # 5% עמלה על מכירות (מנוכה מקרדיט המוכר)
    
    # בונוסי טעינת קרדיט (לפי אמצעי תשלום)
    TOPUP_BONUS_EXTERNAL_LINK: float = 0.25  # 25% בונוס לתשלום חיצוני (משולם/Upay)
    TOPUP_BONUS_CRYPTO: float = 0.50  # 50% בונוס לתשלום קריפטו
    TOPUP_BONUS_STARS: float = 0.0  # אין בונוס ל-Telegram Stars (עמלה גבוהה)
    
    # חבילות קרדיט משתלמות
    TOPUP_PACKAGES: dict = {
        50: 55,   # ₪50 → ₪55 קרדיט (10% בונוס)
        100: 120,  # ₪100 → ₪120 קרדיט (20% בונוס)
        200: 260,  # ₪200 → ₪260 קרדיט (30% בונוס)
    }
    
    # תהליך P2P
    SELLER_CONFIRMATION_TIMEOUT_HOURS: int = 12  # שעות לאישור מוכר
    SELLER_TIMEOUT_PENALTY: float = 10.0  # קנס למוכר שלא עונה בזמן (₪10 מהקרדיט)
    SELLER_MAX_TIMEOUT_VIOLATIONS: int = 3  # מקסימום הפרות לפני השעייה
    
    # תגים למוכרים
    SELLER_VERIFIED_BADGE_MIN_SALES: int = 10  # מינימום מכירות לתג "מאומת ✓"
    SELLER_EXCELLENT_BADGE_MIN_SALES: int = 50  # מינימום מכירות לתג "מצטיין ⭐"
    SELLER_EXCELLENT_BADGE_MIN_RATING: float = 4.8  # מינימום דירוג לתג "מצטיין"
    
    # הגבלות ואזהרות
    SELLER_LOW_RATING_WARNING: float = 3.5  # אזהרה אם דירוג מתחת
    SELLER_LOW_RATING_BLOCK: float = 2.5  # חסימה זמנית אם דירוג מתחת
    SELLER_REPORT_THRESHOLD_REVIEW: int = 3  # מספר דיווחים לבדיקה ידנית
    SELLER_REPORT_THRESHOLD_BLOCK: int = 5  # מספר דיווחים לחסימה אוטומטית
    
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
