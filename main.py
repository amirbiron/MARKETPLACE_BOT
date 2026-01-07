"""
Marketplace Telegram Bot - Main Entry Point
"""
import logging
import os
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from config import Config
from database import Database
from keyboards import Keyboards

# Import handlers
from handlers.buyer_handlers import BuyerHandlers
from handlers.seller_handlers import SellerHandlers
from handlers.admin_handlers import AdminHandlers
from handlers.auction_handlers import get_auction_handlers
from handlers.chat_handlers import get_chat_handlers
from handlers.dispute_handlers import get_dispute_handlers
from handlers.payment_handlers import get_payment_handlers
from handlers.support_handlers import get_support_handlers
from services.health_server import start_health_server
from services.service_lock import LockSettings, MongoServiceLock

# הגדרת לוגינג
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO if not Config.DEBUG else logging.DEBUG
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /start - התחלה"""
    from services.user_service import UserService
    from models import UserRole
    
    user = update.effective_user
    
    # יצירת/קבלת משתמש
    db_user = await UserService.get_user(user.id)
    if not db_user:
        db_user = await UserService.create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            role=UserRole.BUYER
        )
    
    welcome_text = f"""
🎉 ברוך הבא ל-Marketplace Bot!

👋 שלום {user.first_name}!

זהו מרקטפלייס לקניה ומכירת קופונים וכרטיסים.

📊 התפריט הראשי:
🛒 קניית קופונים
💼 מכירת קופונים (למוכרים)
📜 ההזמנות שלי
⚙️ הגדרות
📋 תקנון ומדיניות

בחר פעולה מהתפריט למטה:
"""
    
    keyboard = Keyboards.main_menu(db_user.role)
    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /help - עזרה"""
    help_text = """
📖 עזרה ומידע על הבוט

**פקודות זמינות:**

👥 כל המשתמשים:
/start - התחל שימוש בבוט
/buy - קניית קופונים וכרטיסים
/myorders - צפייה בהזמנות שלי
/balance - בדיקת יתרה
/rules - תקנון ומדיניות
/support - פנייה לתמיכה

💼 מוכרים:
/register_seller - רישום כמוכר
/upload - העלאת קופון
/mysales - המכירות שלי
/withdraw - בקשת משיכת כספים
/stats - סטטיסטיקות

⚙️ אדמינים:
/admin - פאנל ניהול
/sellers - אישור מוכרים
/payouts - משיכות ממתינות
/disputes - מחלוקות

💡 טיפים:
• קנייה מתבצעת רק דרך יתרה שטענת לבוט
• לך 12 שעות לדווח על בעיה אחרי קנייה
• מוכרים מאומתים זוכים לדמי עמלה נמוכים יותר

❓ שאלות? /support
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """בדיקת יתרה"""
    from services.user_service import UserService
    from utils import format_price
    
    user_id = update.effective_user.id
    user = await UserService.get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ משתמש לא נמצא.")
        return
    
    available = user.balance - user.frozen_balance
    
    text = f"""
💰 *היתרה שלך*

✅ זמינה: {format_price(available)}
🔒 מוקפאת: {format_price(user.frozen_balance)}
💳 סה"כ: {format_price(user.balance)}
"""
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תקנון ומדיניות"""
    rules_text = """
📋 *תקנון ומדיניות*

**1. כללי שימוש**
• הבוט מיועד לקניה ומכירה של קופונים וכרטיסים דיגיטליים
• אסור להעלות קופונים מזויפים או לא תקינים
• אסור לבצע עסקאות מחוץ למערכת

**2. עמלות**
• קונה: 2% מערך העסקה
• מוכר מאומת: 3%
• מוכר לא מאומת: 5%
• משיכה: 1%

**3. מדיניות החזרים**
• יש 12 שעות לדווח על בעיה
• אחרי 12 שעות העסקה נסגרת אוטומטית
• החזרים בכפוף לאישור אדמין

**4. אחריות**
• המערכת אינה אחראית לקופונים לא תקינים
• הקונה אחראי לבדוק את הקופון מיד
• המוכר אחראי לספק קופון תקין

**5. משיכות**
• מינימום 200₪
• עמלה 1%
• הכספים מועברים תוך 1-3 ימי עסקים
• ניתן למשוך רק אחרי 24 שעות מקבלת התשלום

**6. חסימות**
• המערכת שומרת הזכות לחסום משתמשים
• חסימה בגין קופונים מזויפים
• חסימה בגין התנהגות לא הולמת

לשאלות: /support
"""
    
    await update.message.reply_text(rules_text, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בשגיאות"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ אירעה שגיאה. אנא נסה שוב מאוחר יותר."
            )
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")


async def post_init(application: Application) -> None:
    """אתחול לאחר הרצת הבוט"""
    from database import db
    from services.background_scheduler import scheduler

    # חיבור למסד נתונים
    await db.connect()
    logger.info("Database connected successfully")

    # הפעלת background scheduler
    await scheduler.start()
    logger.info("Background scheduler started")

    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application) -> None:
    """ניקוי לפני סגירת הבוט"""
    from database import db
    from services.background_scheduler import scheduler

    # עצירת scheduler
    await scheduler.stop()
    logger.info("Background scheduler stopped")

    # ניתוק ממסד נתונים
    await db.close()
    logger.info("Database connection closed")

    logger.info("Bot shutdown complete")


def main():
    """הרצת הבוט"""
    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("rules", rules_command))
    
    # Buyer handlers
    application.add_handler(CommandHandler("buy", BuyerHandlers.browse_categories))
    application.add_handler(CommandHandler("myorders", BuyerHandlers.show_my_orders))
    application.add_handler(CommandHandler("search", BuyerHandlers.start_search))
    application.add_handler(CommandHandler("filters", BuyerHandlers.show_search_filters))
    application.add_handler(CommandHandler("hot_coupons", BuyerHandlers.show_hot_coupons))
    
    # Seller handlers
    application.add_handler(CommandHandler("upload", SellerHandlers.start_coupon_upload))
    application.add_handler(CommandHandler("mysales", SellerHandlers.show_my_sales))
    application.add_handler(CommandHandler("stats", SellerHandlers.show_seller_statistics))
    application.add_handler(CommandHandler("withdraw", SellerHandlers.request_withdrawal))
    
    # Admin handlers
    application.add_handler(CommandHandler("admin", AdminHandlers.admin_menu))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_category_coupons, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_coupon_details, pattern="^coupon_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.initiate_purchase, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.confirm_purchase, pattern="^confirm_buy_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_order_details, pattern="^order_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.confirm_order_received, pattern="^confirm_order_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.start_rating, pattern="^rate_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.submit_rating_score, pattern="^rating_"))
    
    # Admin callbacks
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_seller_requests, pattern="^admin_seller_requests$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_seller_request_details, pattern="^seller_req_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.approve_seller, pattern="^approve_seller_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.reject_seller, pattern="^reject_seller_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_payout_requests, pattern="^admin_payout_requests$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_disputes, pattern="^admin_disputes$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.add_balance_to_user, pattern="^admin_add_balance$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_system_stats, pattern="^admin_stats$"))

    # Auction handlers
    for handler in get_auction_handlers():
        application.add_handler(handler)

    # Chat handlers
    for handler in get_chat_handlers():
        application.add_handler(handler)

    # Dispute handlers
    for handler in get_dispute_handlers():
        application.add_handler(handler)

    # Payment handlers
    for handler in get_payment_handlers():
        application.add_handler(handler)

    # Support handlers
    for handler in get_support_handlers():
        application.add_handler(handler)

    # Error handler
    application.add_error_handler(error_handler)
    
    # הרצת הבוט
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Start tiny HTTP server for Render health checks (only if PORT is set).
    # Keep it alive even while waiting for the distributed lock.
    lock: MongoServiceLock | None = None
    try:
        settings = LockSettings.from_env(default_service_id="marketplace-bot")
        lock = MongoServiceLock(Config.MONGODB_URI, Config.DATABASE_NAME, settings)
        start_health_server(lock)

        # Block here until we hold the lease, so only one instance polls Telegram.
        lock.wait_until_acquired()

        main()
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Fatal startup error: {e}", exc_info=True)
        # Exit non-zero so the platform can restart if desired.
        sys.exit(1)
