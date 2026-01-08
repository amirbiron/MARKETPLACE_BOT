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


async def main_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הצגת תפריט ראשי (לשימוש גם מכפתורי Inline 'main_menu')"""
    from services.user_service import UserService
    from models import UserRole

    user = update.effective_user
    db_user = await UserService.get_user(user.id)
    if not db_user:
        db_user = await UserService.create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            role=UserRole.BUYER,
        )

    keyboard = Keyboards.main_menu(db_user.role)
    text = "🏠 *תפריט ראשי*\n\nבחר פעולה:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תפריט הגדרות"""
    from services.user_service import UserService
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user_id = update.effective_user.id
    user = await UserService.get_user(user_id)
    
    # הצגת סטטוס נוכחי
    notifications_status = "🔔 פעיל" if user and getattr(user, 'notifications_enabled', True) else "🔕 כבוי"
    
    text = f"""
⚙️ *הגדרות*

👤 *פרטי משתמש:*
שם: {update.effective_user.first_name}
שם משתמש: @{update.effective_user.username or 'לא מוגדר'}
סוג חשבון: {'מוכר' if user and user.role.value in ['seller_verified', 'seller_unverified'] else 'קונה'}

🔔 *התראות:* {notifications_status}

📱 *פעולות זמינות:*
"""
    
    keyboard = [
        [InlineKeyboardButton("🔔 הפעל/כבה התראות", callback_data="settings_toggle_notifications")],
        [InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="settings_my_stats")],
        [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        text, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקולבקים של הגדרות"""
    from services.user_service import UserService
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    if action == "settings_toggle_notifications":
        # החלפת מצב התראות
        user = await UserService.get_user(user_id)
        current_status = getattr(user, 'notifications_enabled', True) if user else True
        new_status = not current_status
        
        await UserService.update_notifications_setting(user_id, new_status)
        
        status_text = "🔔 התראות הופעלו" if new_status else "🔕 התראות כובו"
        await query.edit_message_text(
            f"✅ {status_text}\n\nלחץ /start לחזרה לתפריט הראשי",
            parse_mode="Markdown"
        )
    
    elif action == "settings_my_stats":
        # הצגת סטטיסטיקות משתמש
        from services.order_service import OrderService
        from utils import format_price
        
        user = await UserService.get_user(user_id)
        orders = await OrderService.get_buyer_orders(user_id)
        
        total_purchases = len(orders) if orders else 0
        total_spent = sum(o.price_paid for o in orders) if orders else 0
        
        text = f"""
📊 *הסטטיסטיקות שלי*

🛒 סה"כ רכישות: {total_purchases}
💰 סה"כ הוצאות: {format_price(total_spent)}
📅 חבר מאז: {user.created_at.strftime('%d/%m/%Y') if user else 'לא ידוע'}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה להגדרות", callback_data="settings_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif action == "settings_back":
        # חזרה לתפריט הגדרות
        user = await UserService.get_user(user_id)
        notifications_status = "🔔 פעיל" if user and getattr(user, 'notifications_enabled', True) else "🔕 כבוי"
        
        text = f"""
⚙️ *הגדרות*

👤 *פרטי משתמש:*
שם: {update.effective_user.first_name}
שם משתמש: @{update.effective_user.username or 'לא מוגדר'}
סוג חשבון: {'מוכר' if user and user.role.value in ['seller_verified', 'seller_unverified'] else 'קונה'}

🔔 *התראות:* {notifications_status}

📱 *פעולות זמינות:*
"""
        
        keyboard = [
            [InlineKeyboardButton("🔔 הפעל/כבה התראות", callback_data="settings_toggle_notifications")],
            [InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="settings_my_stats")],
            [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def menu_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Router for ReplyKeyboard buttons (they arrive as plain text messages).
    Without this, pressing menu buttons does nothing unless the user types commands.
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # Buyer actions
    if text == "🛒 קניית קופונים":
        return await BuyerHandlers.browse_categories(update, context)
    if text == "📜 ההזמנות שלי":
        return await BuyerHandlers.show_my_orders(update, context)
    if text == "💰 יתרה והטענה":
        from handlers.payment_handlers import PaymentHandlers
        return await PaymentHandlers.my_balance(update, context)
    if text == "📋 תקנון":
        return await rules_command(update, context)
    if text == "💬 הצ'אטים שלי":
        from handlers.chat_handlers import ChatHandlers
        return await ChatHandlers.my_chats(update, context)

    # Seller actions
    if text == "📊 המכירות שלי":
        return await SellerHandlers.show_my_sales(update, context)
    if text == "📈 סטטיסטיקות":
        return await SellerHandlers.show_seller_statistics(update, context)
    if text == "💸 משיכת כספים":
        return await SellerHandlers.request_withdrawal(update, context)

    # Admin actions
    if text == "👨‍💼 פאנל אדמין":
        return await AdminHandlers.admin_menu(update, context)
    
    # Settings
    if text == "⚙️ הגדרות":
        return await settings_menu(update, context)

    # System management (admin only)
    if text == "🔧 ניהול מערכת":
        return await AdminHandlers.system_management_menu(update, context)

    # מועדפים
    if text == "⭐ המועדפים שלי":
        return await BuyerHandlers.show_my_favorites(update, context)

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
    application.add_handler(CommandHandler("menu", main_menu_command))
    
    # Buyer handlers
    application.add_handler(CommandHandler("buy", BuyerHandlers.browse_categories))
    application.add_handler(CommandHandler("myorders", BuyerHandlers.show_my_orders))
    application.add_handler(CommandHandler("filters", BuyerHandlers.show_search_filters))
    application.add_handler(CommandHandler("hot_coupons", BuyerHandlers.show_hot_coupons))

    # Buyer search conversation (/search or inline "search_free")
    async def _cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
        return ConversationHandler.END

    search_conv = ConversationHandler(
        entry_points=[
            CommandHandler("search", BuyerHandlers.start_search),
            CallbackQueryHandler(BuyerHandlers.start_search, pattern="^search_free$"),
        ],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, BuyerHandlers.process_search_query)],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conv)],
        allow_reentry=True,
    )
    application.add_handler(search_conv)
    
    # Seller registration conversation
    seller_register_conv = ConversationHandler(
        entry_points=[
            CommandHandler("register_seller", SellerHandlers.start_seller_registration),
            MessageHandler(filters.Regex(r"^🏪 הפוך למוכר$"), SellerHandlers.start_seller_registration),
        ],
        states={
            7: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_business_name)],
            8: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_phone)],
            9: [
                MessageHandler(filters.Regex(r"^/skip$"), SellerHandlers.receive_id_number),
                MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_id_number),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conv)],
        allow_reentry=True,
    )
    application.add_handler(seller_register_conv)

    # Seller coupon upload conversation
    coupon_upload_conv = ConversationHandler(
        entry_points=[
            CommandHandler("upload", SellerHandlers.start_coupon_upload),
            MessageHandler(filters.Regex(r"^📦 העלאת קופון$"), SellerHandlers.start_coupon_upload),
        ],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_coupon_title)],
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_coupon_category)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_original_price)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_sale_price)],
            4: [
                MessageHandler(filters.Regex(r"^/skip$"), SellerHandlers.receive_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_description),
            ],
            5: [
                MessageHandler(filters.Regex(r"^/skip$"), SellerHandlers.receive_digital_code),
                MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_digital_code),
            ],
            6: [
                MessageHandler(filters.Regex(r"^/skip$"), SellerHandlers.receive_expiry_date),
                MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_expiry_date),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conv)],
        allow_reentry=True,
    )
    application.add_handler(coupon_upload_conv)

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
    
    # Favorites handlers
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_my_favorites, pattern="^my_favorites$"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.add_to_favorites, pattern="^fav_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.remove_from_favorites, pattern="^unfav_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.favorites_pagination, pattern="^favorites_page_"))
    # Rating conversation (rate_ -> rating_ -> comment text)
    rating_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(BuyerHandlers.start_rating, pattern="^rate_")],
        states={
            3: [CallbackQueryHandler(BuyerHandlers.submit_rating_score, pattern="^rating_")],
            2: [
                MessageHandler(filters.Regex(r"^/skip$"), BuyerHandlers.process_rating_comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND, BuyerHandlers.process_rating_comment),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conv)],
        allow_reentry=True,
    )
    application.add_handler(rating_conv)
    
    # Admin callbacks
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_seller_requests, pattern="^admin_seller_requests$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_seller_request_details, pattern="^seller_req_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.approve_seller, pattern="^approve_seller_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.reject_seller, pattern="^reject_seller_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_payout_requests, pattern="^admin_payout_requests$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_disputes, pattern="^admin_disputes$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.add_balance_to_user, pattern="^admin_add_balance$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.show_system_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.view_pending_deposits, pattern="^admin_deposit_requests$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.admin_menu, pattern="^admin_menu$"))
    
    # System management callbacks (admin)
    application.add_handler(CallbackQueryHandler(AdminHandlers.manage_users, pattern="^sys_manage_users$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.manage_sellers, pattern="^sys_manage_sellers$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.manage_coupons, pattern="^sys_manage_coupons$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.view_user_details, pattern="^sys_user_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.block_user, pattern="^sys_block_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.unblock_user, pattern="^sys_unblock_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.view_coupon_details, pattern="^sys_coupon_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.delete_coupon, pattern="^sys_del_coupon_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.view_logs, pattern="^sys_view_logs$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.system_settings, pattern="^sys_settings$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.sys_back_handler, pattern="^sys_back$"))
    
    # Broadcast conversation
    from handlers.admin_handlers import BROADCAST_MESSAGE, ADD_BALANCE_AMOUNT
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(AdminHandlers.start_broadcast, pattern="^sys_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, AdminHandlers.process_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", AdminHandlers.cancel_admin_action)],
    )
    application.add_handler(broadcast_conv)
    
    # Add balance to user conversation
    add_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(AdminHandlers.start_add_balance_to_user, pattern="^sys_addbal_")],
        states={
            ADD_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, AdminHandlers.process_add_balance)]
        },
        fallbacks=[CommandHandler("cancel", AdminHandlers.cancel_admin_action)],
    )
    application.add_handler(add_balance_conv)
    
    # Send message to user conversation
    from handlers.admin_handlers import SEND_USER_MESSAGE
    send_msg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(AdminHandlers.start_send_user_message, pattern="^sys_msg_")],
        states={
            SEND_USER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, AdminHandlers.process_send_user_message)]
        },
        fallbacks=[CommandHandler("cancel", AdminHandlers.cancel_admin_action)],
    )
    application.add_handler(send_msg_conv)

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

    # Inline "back to main menu"
    application.add_handler(CallbackQueryHandler(main_menu_command, pattern="^main_menu$"))
    
    # Settings callbacks
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern="^settings_"))

    # ReplyKeyboard router (menu buttons) - register late so more specific
    # ConversationHandlers (support/upload) can match first.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text_router))

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
