"""
Marketplace Telegram Bot - Main Entry Point
"""
import logging
import os
import sys
from enum import Enum
from telegram import Update, ReplyKeyboardRemove
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
from handlers.admin_forum_chat_handlers import get_admin_forum_chat_handlers
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

# Silence noisy HTTP client logs (python-telegram-bot uses httpx under the hood)
# These logs can include the bot token inside the request URL.
if not Config.DEBUG:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /start - התחלה"""
    from services.user_service import UserService
    from models import UserRole
    
    user = update.effective_user
    
    # יצירת/קבלת משתמש
    db_user = await UserService.get_user(user.id)
    if not db_user:
        desired_role = UserRole.ADMIN if user.id in Config.ADMIN_IDS else UserRole.BUYER
        db_user = await UserService.create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            role=desired_role
        )
    else:
        # קידום אוטומטי לאדמין לפי ADMIN_IDS (כדי שתפריט אדמין יוצג)
        if user.id in Config.ADMIN_IDS and db_user.role != UserRole.ADMIN:
            await UserService.set_admin(user.id)
            db_user = await UserService.get_user(user.id) or db_user
    
    welcome_text = f"""
🎉 *ברוך הבא ל-Marketplace Bot!*

👋 שלום {user.first_name}!

זהו מרקטפלייס לקניה ומכירת קופונים וכרטיסים.

📊 *התפריט הראשי:*
🛒 קניית קופונים
💼 מכירת קופונים (למוכרים)
📜 ההזמנות שלי
⚙️ הגדרות
📋 תקנון ומדיניות

בחר פעולה מהכפתורים:
"""
    
    # הסרת מקלדת ראשית ישנה (אם קיימת) והצגת כפתורי אינליין
    # העבר גם seller_status לתפריט כדי להבטיח שמוכרים מאושרים יראו כפתורי מוכר
    seller_status = getattr(db_user, 'seller_status', None)
    if isinstance(seller_status, Enum):
        seller_status = seller_status.value
    keyboard = Keyboards.main_menu(db_user.role, seller_status)
    # First remove any existing reply keyboard, then show inline menu
    remove_msg = await update.message.reply_text("⏳ טוען תפריט...", reply_markup=ReplyKeyboardRemove())
    await remove_msg.delete()
    await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /help - עזרה"""
    help_text = """
📖 עזרה ומידע על הבוט

**פקודות זמינות:**

👥 כל המשתמשים:
/start - התחל שימוש בבוט
/menu - תפריט ראשי
/buy - קניית קופונים וכרטיסים
/myorders - צפייה בהזמנות שלי
/balance - בדיקת יתרה
/my\\_deposits - ההפקדות שלי
/rules - תקנון ומדיניות
/support - פנייה לתמיכה
/chats - הצ'אטים שלי

💼 מוכרים:
/register\\_seller - רישום כמוכר
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
        desired_role = UserRole.ADMIN if user.id in Config.ADMIN_IDS else UserRole.BUYER
        db_user = await UserService.create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            role=desired_role,
        )
    else:
        # קידום אוטומטי לאדמין לפי ADMIN_IDS (כדי שתפריט אדמין יוצג גם מ-/menu)
        if user.id in Config.ADMIN_IDS and db_user.role != UserRole.ADMIN:
            await UserService.set_admin(user.id)
            db_user = await UserService.get_user(user.id) or db_user

    # העבר גם seller_status לתפריט כדי להבטיח שמוכרים מאושרים יראו כפתורי מוכר
    seller_status = getattr(db_user, 'seller_status', None)
    if isinstance(seller_status, Enum):
        seller_status = seller_status.value
    keyboard = Keyboards.main_menu(db_user.role, seller_status)
    text = "🏠 *תפריט ראשי*\n\nבחר פעולה מהכפתורים:"

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            # If message can't be edited (e.g., same content), send new message
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    else:
        # הסרת מקלדת ראשית ישנה (אם קיימת)
        remove_msg = await update.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await remove_msg.delete()
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


async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקולבקים של התפריט הראשי"""
    from services.user_service import UserService
    from handlers.payment_handlers import PaymentHandlers
    from handlers.chat_handlers import ChatHandlers
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    query = update.callback_query
    action = query.data
    
    # קניית קופונים
    if action == "menu_buy_coupons":
        await query.answer()
        return await BuyerHandlers.browse_categories(update, context)
    
    # יתרה והטענה
    if action == "menu_balance":
        await query.answer()
        # שליחת הודעה חדשה כי my_balance מצפה להודעה
        user_id = update.effective_user.id
        from services.payment_service import PaymentService
        from services.payout_service import PayoutService
        
        balance, frozen = await PaymentService.get_user_balance(user_id)
        
        text = "💰 *היתרה שלי*\n\n"
        text += f"💵 יתרה זמינה: {balance:.2f}₪\n"
        
        if frozen > 0:
            text += f"🔒 יתרה קפואה: {frozen:.2f}₪\n"
            text += f"💎 סה\"כ: {(balance + frozen):.2f}₪\n\n"
            text += "💡 יתרה קפואה = כסף בהצעות במכרזים\n"
        else:
            text += f"\n💡 יתרה קפואה: 0₪\n"
        
        keyboard = []
        
        # אפשרויות טעינה
        if Config.PAYMENT_GATEWAY_ENABLED:
            keyboard.append([
                InlineKeyboardButton("💳 תשלום בכרטיס אשראי", callback_data="pay_credit_card")
            ])
            keyboard.append([
                InlineKeyboardButton("➕ הוסף יתרה (ביט/העברה)", callback_data="add_balance")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("➕ הוסף יתרה", callback_data="add_balance")
            ])
        
        keyboard.append([InlineKeyboardButton("📊 היסטוריית תנועות", callback_data="transaction_history")])
        
        # אם מוכר - הצג אפשרות משיכה
        user = await UserService.get_user(user_id)
        if user and user.role.value in ["seller_verified", "seller_unverified"]:
            available = await PayoutService.calculate_available_for_payout(user_id)
            text += f"\n💸 זמין למשיכה: {available:.2f}₪\n"
            
            if available >= Config.MIN_PAYOUT_AMOUNT:
                if Config.AUTO_PAYOUT_ENABLED:
                    keyboard.append([InlineKeyboardButton("💸 משיכת כספים", callback_data="automated_payout")])
                else:
                    keyboard.append([InlineKeyboardButton("💸 בקשת משיכה", callback_data="request_payout")])
        
        # ניהול כרטיסים שמורים
        if Config.PAYMENT_GATEWAY_ENABLED and Config.ALLOW_SAVE_CARD:
            keyboard.append([InlineKeyboardButton("💳 כרטיסים שמורים", callback_data="cc_manage_cards")])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # ההזמנות שלי
    if action == "menu_my_orders":
        await query.answer()
        return await BuyerHandlers.show_my_orders(update, context)
    
    # המועדפים שלי
    if action == "menu_favorites":
        await query.answer()
        return await BuyerHandlers.show_my_favorites(update, context)
    
    # ההפקדות שלי
    if action == "menu_my_deposits":
        await query.answer()
        user_id = update.effective_user.id
        from database import db
        
        cursor = db.deposit_requests.find({"user_id": user_id}).sort("created_at", -1).limit(10)
        deposits = await cursor.to_list(length=None)
        
        if not deposits:
            text = "💰 *ההפקדות שלי*\n\nאין לך הפקדות עדיין."
        else:
            text = "💰 *ההפקדות שלי*\n\n"
            for dep in deposits:
                status_emoji = {
                    "pending": "🟡",
                    "approved": "✅",
                    "rejected": "❌"
                }.get(dep["status"], "❓")
                
                text += f"{status_emoji} {dep['amount']}₪ | {dep['reference_code']}\n"
                text += f"   {dep['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    
    # העלאת קופון (מוכרים) - התחל ישירות את תהליך העלאה
    if action == "menu_upload_coupon":
        await query.answer()
        user_id = update.effective_user.id
        
        # בדיקה אם מוכר
        if not await UserService.is_seller(user_id):
            await query.edit_message_text("❌ אתה צריך להירשם כמוכר קודם!")
            return
        
        # בדיקה אם מוכר ממתין לאישור
        user = await UserService.get_user(user_id)
        if user and getattr(user, 'seller_status', None) == 'pending':
            await query.edit_message_text(
                "⏳ *ממתין לאישור*\n\n"
                "הבקשה שלך להירשם כמוכר עדיין ממתינה לאישור אדמינים.\n"
                "תקבל הודעה כשהבקשה תאושר.",
                parse_mode="Markdown"
            )
            return
        
        # בדיקת הגבלה יומית למוכר לא מאומת
        is_verified = await UserService.is_verified_seller(user_id)
        if not is_verified:
            import database
            from datetime import datetime
            coupons = await database.get_coupons_collection()
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count = await coupons.count_documents({
                "seller_id": user_id,
                "created_at": {"$gte": today_start}
            })
            
            if count >= Config.DAILY_COUPON_LIMIT_UNVERIFIED:
                await query.edit_message_text(
                    f"❌ הגעת למגבלה היומית של {Config.DAILY_COUPON_LIMIT_UNVERIFIED} קופונים.\n"
                    f"נסה שוב מחר או הירשם כמוכר מאומת."
                )
                return
        
        # התחלת תהליך העלאה ישירות
        text = """
📦 *העלאת קופון חדש*

בוא נתחיל! שלח את הפרטים הבאים:

📝 1. כותרת הקופון (לדוגמה: ארוחה זוגית במסעדת איטלקיה)
"""
        await query.edit_message_text(text, parse_mode="Markdown")
        # Set conversation state for coupon upload
        context.user_data['awaiting_coupon_upload'] = True
        return
    
    # המכירות שלי (מוכרים)
    if action == "menu_my_sales":
        await query.answer()
        return await SellerHandlers.show_my_sales(update, context)
    
    # משיכת כספים (מוכרים)
    if action == "menu_withdraw":
        await query.answer()
        return await SellerHandlers.request_withdrawal(update, context)
    
    # סטטיסטיקות (מוכרים)
    if action == "menu_stats":
        await query.answer()
        return await SellerHandlers.show_seller_statistics(update, context)
    
    # הפוך למוכר - התחל ישירות את תהליך הרישום
    if action == "menu_become_seller":
        await query.answer()
        # בדיקה סטטוס מוכר קיים / ממתין / חסום
        user_id = update.effective_user.id
        user = await UserService.get_user(user_id)

        if user and getattr(user, "seller_status", None) == "pending":
            await query.edit_message_text(
                "⏳ *ממתין לאישור*\n\n"
                "הבקשה שלך להירשם כמוכר כבר נשלחה וממתינה לאישור אדמינים.\n"
                "תקבל הודעה כשהבקשה תאושר.",
                parse_mode="Markdown",
            )
            return

        if user and getattr(user, "seller_status", None) == "blocked":
            await query.edit_message_text(
                "🚫 *בקשת מוכר חסומה*\n\n"
                "לא ניתן להתחיל רישום כמוכר כרגע.\n"
                "אם אתה חושב שזו טעות, פנה לתמיכה: /support",
                parse_mode="Markdown",
            )
            return

        if await UserService.is_seller(user_id):
            await query.edit_message_text("✅ אתה כבר רשום כמוכר!")
            return

        # ניקוי מצבי המתנה קודמים כדי למנוע ניתוב שגוי
        for key in (
            "awaiting_seller_registration",
            "awaiting_commercial_name",
            "awaiting_phone",
            "awaiting_id_number",
            "business_name",
            "commercial_name",
            "phone",
        ):
            context.user_data.pop(key, None)
        
        # התחלת תהליך הרישום ישירות
        text = """
👨‍💼 *רישום כמוכר*

ברוך הבא להליך רישום המוכרים!

📝 בחר סוג רישום:

🔹 *מוכר מאומת* (עם ת.ז)
   • עמלה: 3%
   • ללא הגבלת קופונים
   • סמל "מאומת" בפרופיל

🔹 *מוכר רגיל* (ללא ת.ז)
   • עמלה: 5%
   • עד 10 קופונים ביום
   • ללא סימון מיוחד

📝 שלח את שם העסק שלך:
"""
        await query.edit_message_text(text, parse_mode="Markdown")
        # Set conversation state for seller registration
        context.user_data['awaiting_seller_registration'] = True
        return
    
    # פאנל אדמין
    if action == "menu_admin_panel":
        await query.answer()
        return await AdminHandlers.admin_menu(update, context)
    
    # ניהול מערכת
    if action == "menu_system_management":
        await query.answer()
        user_id = update.effective_user.id
        if user_id not in Config.ADMIN_IDS:
            await query.edit_message_text("❌ אין לך הרשאות אדמין.")
            return
        
        text = "🔧 *ניהול מערכת*\n\nבחר פעולה:"
        keyboard = Keyboards.system_management_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return
    
    # הצ'אטים שלי
    if action == "menu_my_chats":
        await query.answer()
        return await ChatHandlers.my_chats(update, context)
    
    # הגדרות
    if action == "menu_settings":
        await query.answer()
        user_id = update.effective_user.id
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
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # תקנון
    if action == "menu_rules":
        await query.answer()
        rules_text = """
📋 *תקנון ומדיניות*

*1. כללי שימוש*
• הבוט מיועד לקניה ומכירה של קופונים וכרטיסים דיגיטליים
• אסור להעלות קופונים מזויפים או לא תקינים
• אסור לבצע עסקאות מחוץ למערכת

*2. עמלות*
• קונה: 2% מערך העסקה
• מוכר מאומת: 3%
• מוכר לא מאומת: 5%
• משיכה: 1%

*3. מדיניות החזרים*
• יש 12 שעות לדווח על בעיה
• אחרי 12 שעות העסקה נסגרת אוטומטית
• החזרים בכפוף לאישור אדמין

*4. אחריות*
• המערכת אינה אחראית לקופונים לא תקינים
• הקונה אחראי לבדוק את הקופון מיד
• המוכר אחראי לספק קופון תקין

לשאלות: /support
"""
        keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]]
        await query.edit_message_text(rules_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    
    # פנייה למערכת - התחל ישירות את תהליך הפנייה
    if action == "menu_support":
        await query.answer()
        text = """
📩 *פנייה למערכת*

תוכל לשלוח לנו כל שאלה, בעיה או הצעה.

כתוב את הודעתך למטה ואנו נחזור אליך בהקדם.

💡 *דוגמאות:*
• דיווח על באג
• שאלה על המערכת
• בקשה לתמיכה בעסקה
• הצעה לשיפור

⏳ זמן מענה ממוצע: 24 שעות
"""
        await query.edit_message_text(text, parse_mode="Markdown")
        # Set conversation state for support message
        context.user_data['awaiting_support_message'] = True
        return

    # היסטוריית קופונים שנמכרו
    if action == "menu_sold_coupons":
        await query.answer()
        return await BuyerHandlers.show_sold_coupons_history(update, context)


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
        
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception:
            pass


async def menu_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Router for legacy ReplyKeyboard button texts and awaiting states from inline buttons.
    Now that we use inline buttons, redirect users to the main menu.
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    
    # טיפול ב-awaiting states מכפתורי inline
    
    # מצב המתנה לרישום מוכר - קליטת שם עסק
    if context.user_data.get('awaiting_seller_registration'):
        context.user_data.pop('awaiting_seller_registration', None)
        context.user_data['business_name'] = text
        # לפי ה-flow החדש: אחרי שם העסק עוברים לבקשת מספר טלפון
        # נשמור commercial_name כברירת מחדל = שם העסק, לתאימות לתצוגות קיימות.
        context.user_data["commercial_name"] = text
        await update.message.reply_text("📞 שלח מספר טלפון WhatsApp (לדוגמה: 0501234567):")
        context.user_data['awaiting_phone'] = True
        return
    
    # מצב המתנה לשם מסחרי
    if context.user_data.get('awaiting_commercial_name'):
        context.user_data.pop('awaiting_commercial_name', None)
        
        # וולידציה בסיסית
        if len(text) < 2:
            await update.message.reply_text("❌ שם מסחרי קצר מדי. אנא שלח שם בעל 2 תווים לפחות:")
            context.user_data['awaiting_commercial_name'] = True
            return
        
        if len(text) > 50:
            await update.message.reply_text("❌ שם מסחרי ארוך מדי. אנא שלח שם עד 50 תווים:")
            context.user_data['awaiting_commercial_name'] = True
            return
        
        context.user_data['commercial_name'] = text
        await update.message.reply_text("📞 שלח מספר טלפון WhatsApp (לדוגמה: 0501234567):")
        context.user_data['awaiting_phone'] = True
        return
    
    # מצב המתנה לטלפון
    if context.user_data.get('awaiting_phone'):
        context.user_data.pop('awaiting_phone', None)
        phone = text.replace("-", "").replace(" ", "")
        
        # וולידציה בסיסית
        if not phone.isdigit() or len(phone) < 9:
            await update.message.reply_text("❌ מספר טלפון לא תקין. אנא נסה שוב:")
            context.user_data['awaiting_phone'] = True
            return
        
        context.user_data['phone'] = phone
        await update.message.reply_text(
            "🆔 האם תרצה להירשם כמוכר מאומת?\n\n"
            "שלח תעודת זהות (9 ספרות) או /skip לדילוג:"
        )
        context.user_data['awaiting_id_number'] = True
        return
    
    # מצב המתנה לת.ז
    if context.user_data.get('awaiting_id_number'):
        context.user_data.pop('awaiting_id_number', None)
        # Route to the actual handler
        return await SellerHandlers.receive_id_number(update, context)
    
    # מצב המתנה להעלאת קופון - קליטת כותרת
    if context.user_data.get('awaiting_coupon_upload'):
        context.user_data.pop('awaiting_coupon_upload', None)
        context.user_data['coupon_title'] = text
        
        # הצגת קטגוריות
        from services.coupon_service import CouponService
        categories_text = "\n".join([f"{i+1}. {cat}" for i, cat in enumerate(CouponService.CATEGORIES)])
        
        await update.message.reply_text(
            f"📁 *בחר קטגוריה*\n\n{categories_text}\n\nשלח מספר (1-{len(CouponService.CATEGORIES)}):",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_coupon_category'] = True
        return
    
    # המשך תהליך העלאת קופון - קטגוריה
    if context.user_data.get('awaiting_coupon_category'):
        context.user_data.pop('awaiting_coupon_category', None)
        from services.coupon_service import CouponService
        
        try:
            cat_num = int(text) - 1
            if 0 <= cat_num < len(CouponService.CATEGORIES):
                context.user_data['coupon_category'] = CouponService.CATEGORIES[cat_num]
            else:
                raise ValueError()
        except:
            await update.message.reply_text("❌ מספר לא תקין. נסה שוב:")
            context.user_data['awaiting_coupon_category'] = True
            return
        
        await update.message.reply_text("💰 שלח מחיר מקורי (לדוגמה: 250):")
        context.user_data['awaiting_original_price'] = True
        return
    
    # מחיר מקורי
    if context.user_data.get('awaiting_original_price'):
        context.user_data.pop('awaiting_original_price', None)
        try:
            price = float(text)
            if price <= 0:
                raise ValueError()
            context.user_data['original_price'] = price
        except:
            await update.message.reply_text("❌ מחיר לא תקין. נסה שוב:")
            context.user_data['awaiting_original_price'] = True
            return
        
        await update.message.reply_text("💵 שלח מחיר מכירה (לדוגמה: 150):")
        context.user_data['awaiting_sale_price'] = True
        return
    
    # מחיר מכירה
    if context.user_data.get('awaiting_sale_price'):
        context.user_data.pop('awaiting_sale_price', None)
        try:
            price = float(text)
            if price <= 0 or price >= context.user_data['original_price']:
                await update.message.reply_text("❌ מחיר המכירה חייב להיות נמוך מהמחיר המקורי. נסה שוב:")
                context.user_data['awaiting_sale_price'] = True
                return
            context.user_data['sale_price'] = price
        except:
            await update.message.reply_text("❌ מחיר לא תקין. נסה שוב:")
            context.user_data['awaiting_sale_price'] = True
            return
        
        await update.message.reply_text("📝 שלח תיאור (או /skip לדילוג):")
        context.user_data['awaiting_description'] = True
        return
    
    # תיאור
    if context.user_data.get('awaiting_description'):
        context.user_data.pop('awaiting_description', None)
        if text == "/skip":
            context.user_data['description'] = None
        else:
            context.user_data['description'] = text
        
        await update.message.reply_text("🔐 שלח קוד דיגיטלי/ברקוד של הקופון (או /skip):")
        context.user_data['awaiting_digital_code'] = True
        return
    
    # קוד דיגיטלי
    if context.user_data.get('awaiting_digital_code'):
        context.user_data.pop('awaiting_digital_code', None)
        if text == "/skip":
            context.user_data['digital_code'] = None
        else:
            context.user_data['digital_code'] = text
        
        await update.message.reply_text(
            "📅 שלח תאריך תפוגה (DD/MM/YYYY) או /skip:\n"
            "(לדוגמה: 31/12/2026)"
        )
        context.user_data['awaiting_expiry_date'] = True
        return
    
    # תאריך תפוגה וסיום
    if context.user_data.get('awaiting_expiry_date'):
        context.user_data.pop('awaiting_expiry_date', None)
        from datetime import datetime
        from services.coupon_service import CouponService
        from utils import format_price
        
        expiry_date = None
        if text != "/skip":
            try:
                expiry_date = datetime.strptime(text, "%d/%m/%Y")
            except:
                await update.message.reply_text("❌ תאריך לא תקין. נסה שוב או /skip:")
                context.user_data['awaiting_expiry_date'] = True
                return
        
        # יצירת הקופון
        coupon = await CouponService.create_coupon(
            seller_id=update.effective_user.id,
            title=context.user_data['coupon_title'],
            category=context.user_data['coupon_category'],
            original_price=context.user_data['original_price'],
            sale_price=context.user_data['sale_price'],
            description=context.user_data.get('description'),
            digital_code=context.user_data.get('digital_code'),
            expires_at=expiry_date
        )
        
        if coupon:
            await update.message.reply_text(
                f"✅ *הקופון הועלה בהצלחה!*\n\n"
                f"🎫 {coupon.title}\n"
                f"💰 מחיר: {format_price(coupon.sale_price)}\n"
                f"📁 קטגוריה: {coupon.category}\n\n"
                f"הקופון זמין כעת לקנייה במערכת.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ ההעלאה נכשלה. אנא נסה שוב.")
        
        # ניקוי נתוני קופון
        for key in ['coupon_title', 'coupon_category', 'original_price', 'sale_price', 'description', 'digital_code']:
            context.user_data.pop(key, None)
        return
    
    # מצב המתנה לפנייה למערכת
    if context.user_data.get('awaiting_support_message'):
        context.user_data.pop('awaiting_support_message', None)
        
        from database import db
        from services.notification_service import NotificationService
        from datetime import datetime
        
        user_id = update.effective_user.id
        message = text
        user = update.effective_user
        
        # שמירת הפנייה במסד נתונים
        support_ticket = {
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "message": message,
            "status": "open",
            "created_at": datetime.utcnow()
        }
        
        result = await db.support_tickets.insert_one(support_ticket)
        
        # שליחת התראה לאדמינים
        for admin_id in Config.ADMIN_IDS:
            try:
                await NotificationService.send_notification(
                    user_id=admin_id,
                    title="📩 פנייה חדשה למערכת",
                    message=f"מאת: {user.first_name} (@{user.username})\n\n{message[:200]}...",
                    notification_type="support_ticket",
                    data={"ticket_id": str(result.inserted_id)}
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        await update.message.reply_text(
            f"✅ *פנייתך נקלטה בהצלחה!*\n\n"
            f"מספר פנייה: {str(result.inserted_id)[:8]}\n\n"
            f"נחזור אליך בהקדם האפשרי.\n"
            f"תודה על פנייתך! 🙏",
            parse_mode="Markdown"
        )
        return

    # רשימת הטקסטים הישנים של כפתורי התפריט
    old_menu_texts = [
        "🛒 קניית קופונים", "📜 ההזמנות שלי", "💰 יתרה והטענה",
        "📋 תקנון", "💬 הצ'אטים שלי", "📊 המכירות שלי",
        "📈 סטטיסטיקות", "💸 משיכת כספים", "👨‍💼 פאנל אדמין",
        "⚙️ הגדרות", "🔧 ניהול מערכת", "⭐ המועדפים שלי",
        "📦 העלאת קופון", "🏪 הפוך למוכר", "📩 פנייה למערכת"
    ]
    
    # אם המשתמש הקליד טקסט של כפתור ישן, שלח אותו לתפריט הראשי
    if text in old_menu_texts:
        await update.message.reply_text(
            "💡 התפריט עודכן לכפתורים אינטראקטיביים!\n\n"
            "השתמש בפקודה /start או /menu לפתיחת התפריט הראשי."
        )
        return await main_menu_command(update, context)

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
            7: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_business_name)],  # BUSINESS_NAME
            9: [MessageHandler(filters.TEXT & ~filters.COMMAND, SellerHandlers.receive_phone)],  # PHONE
            10: [  # ID_NUMBER
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
    # Seller profile & reviews (from coupon details)
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_seller_profile, pattern=r"^seller_\d+$"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_seller_reviews, pattern=r"^reviews_\d+(?:_page_\d+)?$"))
    
    # Favorites handlers
    application.add_handler(CallbackQueryHandler(BuyerHandlers.show_my_favorites, pattern="^my_favorites$"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.add_to_favorites, pattern="^fav_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.remove_from_favorites, pattern="^unfav_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.favorites_pagination, pattern="^favorites_page_"))

    # Notification action handlers (confirm/report from notification)
    application.add_handler(CallbackQueryHandler(BuyerHandlers.confirm_from_notification, pattern="^confirm_from_notif_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.report_from_notification, pattern="^report_from_notif_"))

    # Sold coupons history handlers
    application.add_handler(CallbackQueryHandler(BuyerHandlers.sold_coupons_pagination, pattern="^sold_page_"))
    application.add_handler(CallbackQueryHandler(BuyerHandlers.sold_coupon_info, pattern="^sold_coupon_info$"))
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
    application.add_handler(CallbackQueryHandler(AdminHandlers.block_seller, pattern="^block_seller_"))
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
    
    # Fraud management callbacks
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_menu, pattern="^fraud_menu$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_pending_events, pattern="^fraud_pending_events$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_view_event, pattern="^fraud_event_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_mark_reviewed, pattern="^fraud_mark_reviewed_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_stats, pattern="^fraud_stats$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_blocked_users, pattern="^fraud_blocked_users$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_view_user, pattern="^fraud_view_user_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_user_history, pattern="^fraud_user_history_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_block_user, pattern="^fraud_block_user_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_unblock_user, pattern="^fraud_unblock_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_keep_blocked, pattern="^fraud_keep_blocked_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_warn_user, pattern="^fraud_warn_user_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.fraud_calc_trust, pattern="^fraud_calc_trust_"))
    
    # Escrow management callbacks
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_menu, pattern="^escrow_menu$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_balance, pattern="^escrow_balance$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_pending, pattern="^escrow_pending$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_disputed, pattern="^escrow_disputed$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_view, pattern="^escrow_view_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_release, pattern="^escrow_release_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_refund, pattern="^escrow_refund_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_confirm_release, pattern="^escrow_confirm_release_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_confirm_refund, pattern="^escrow_confirm_refund_"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_stats, pattern="^escrow_stats$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_daily_report, pattern="^escrow_daily_report$"))
    application.add_handler(CallbackQueryHandler(AdminHandlers.escrow_logs, pattern="^escrow_logs_"))
    
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

    # Admin Forum (Topics) mirroring handlers (optional)
    for handler in get_admin_forum_chat_handlers():
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
    
    # Menu callbacks (main menu inline buttons)
    application.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))
    
    # ==================== Seller Dashboard Callbacks ====================
    
    # Main dashboard
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_dashboard, pattern="^seller_dashboard$"))
    
    # Statistics
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_advanced_stats, pattern="^dashboard_stats$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.change_stats_period, pattern="^stats_period_"))
    
    # Graph
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_sales_graph, pattern="^dashboard_graph$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.change_graph_period, pattern="^graph_period_"))
    
    # Analytics views
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_top_products, pattern="^dashboard_top_products$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_category_breakdown, pattern="^dashboard_categories$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_peak_times, pattern="^dashboard_peak_times$"))
    
    # Reports
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_reports_menu, pattern="^dashboard_reports$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.generate_monthly_report, pattern="^report_monthly$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.generate_commission_report, pattern="^report_commissions$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.generate_disputes_report, pattern="^report_disputes$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.export_sales_csv, pattern="^export_sales_csv$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.export_products_csv, pattern="^export_products_csv$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.export_all_csv, pattern="^export_all_csv$"))
    
    # Product Management
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_products_menu, pattern="^dashboard_products$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_products_list, pattern="^products_list$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.select_product, pattern="^product_select_"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.clear_product_selection, pattern="^products_clear_selection$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.products_pagination, pattern="^products_page_"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_duplicate_menu, pattern="^products_duplicate$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.duplicate_product, pattern="^product_duplicate_"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_bulk_price_menu, pattern="^products_bulk_price$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.apply_bulk_price_change, pattern="^bulk_price_"))
    
    # Alert Settings
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_alert_settings, pattern="^dashboard_alerts$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.toggle_alert, pattern="^alert_toggle_"))
    
    # Scheduled Coupons
    application.add_handler(CallbackQueryHandler(SellerHandlers.show_scheduled_list, pattern="^products_scheduled_list$"))
    application.add_handler(CallbackQueryHandler(SellerHandlers.cancel_scheduled_coupon, pattern="^scheduled_cancel_"))
    
    # Settings callbacks
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern="^settings_"))

    # ReplyKeyboard router (menu buttons) - register late so more specific
    # ConversationHandlers (support/upload) can match first.
    # Allow /skip during inline "awaiting_id_number" flow (router ignores commands by default).
    application.add_handler(MessageHandler(filters.Regex(r"^/skip$"), menu_text_router))
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
