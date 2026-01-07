"""
Handlers למערכת תמיכה ופניות
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from database import db
from config import Config
from services.notification_service import NotificationService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# States
WAITING_FOR_SUPPORT_MESSAGE = range(1)


class SupportHandlers:
    """Handlers עבור מערכת תמיכה"""

    @staticmethod
    async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת /support - פתיחת פנייה למערכת"""
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

        await update.message.reply_text(text, parse_mode="Markdown")
        return WAITING_FOR_SUPPORT_MESSAGE

    @staticmethod
    async def process_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד פנייה"""
        user_id = update.effective_user.id
        message = update.message.text
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

        # שליחת התראה לכל האדמינים
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

        return ConversationHandler.END

    @staticmethod
    async def cancel_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול פנייה"""
        await update.message.reply_text("❌ פנייה בוטלה")
        return ConversationHandler.END

    @staticmethod
    async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפניות שלי"""
        user_id = update.effective_user.id

        # קבלת כל הפניות של המשתמש
        cursor = db.support_tickets.find({
            "user_id": user_id
        }).sort("created_at", -1).limit(10)

        tickets = await cursor.to_list(length=None)

        if not tickets:
            await update.message.reply_text(
                "📭 אין לך פניות פתוחות\n\n"
                "השתמש ב-/support כדי לפתוח פנייה חדשה"
            )
            return

        text = "📩 *הפניות שלי*\n\n"

        for i, ticket in enumerate(tickets, 1):
            status_emoji = {
                "open": "🟡",
                "in_progress": "🔵",
                "resolved": "✅",
                "closed": "⚫"
            }.get(ticket.get("status", "open"), "❓")

            text += f"{i}. {status_emoji} {ticket['message'][:50]}...\n"
            text += f"   תאריך: {ticket['created_at'].strftime('%d/%m/%Y')}\n"

            if ticket.get("response"):
                text += f"   📝 תשובה: {ticket['response'][:50]}...\n"

            text += "\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    @staticmethod
    async def admin_view_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפניות (לאדמין)"""
        query = update.callback_query
        if query:
            await query.answer()

        # בדיקת הרשאות אדמין
        user_id = update.effective_user.id
        if user_id not in Config.ADMIN_IDS:
            if query:
                await query.edit_message_text("❌ אין לך הרשאות אדמין")
            else:
                await update.message.reply_text("❌ אין לך הרשאות אדמין")
            return

        # קבלת פניות פתוחות
        cursor = db.support_tickets.find({
            "status": {"$in": ["open", "in_progress"]}
        }).sort("created_at", 1).limit(10)

        tickets = await cursor.to_list(length=None)

        if not tickets:
            text = "✅ אין פניות ממתינות"
            keyboard = None
        else:
            text = "📩 *פניות למערכת* (10 אחרונות)\n\n"

            keyboard = []
            for i, ticket in enumerate(tickets, 1):
                text += f"{i}. {ticket.get('first_name', 'משתמש')}\n"
                text += f"   {ticket['message'][:70]}...\n"
                text += f"   {ticket['created_at'].strftime('%d/%m %H:%M')}\n\n"

                keyboard.append([InlineKeyboardButton(
                    f"#{i} - פרטים",
                    callback_data=f"support_view_{ticket['_id']}"
                )])

            keyboard.append([InlineKeyboardButton("🔄 רענן", callback_data="admin_support_tickets")])

        if query:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                parse_mode="Markdown"
            )


def get_support_handlers():
    """החזרת handlers לתמיכה"""

    # Conversation handler לפנייה חדשה
    support_conv = ConversationHandler(
        entry_points=[
            CommandHandler("support", SupportHandlers.support_command)
        ],
        states={
            WAITING_FOR_SUPPORT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, SupportHandlers.process_support_message)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", SupportHandlers.cancel_support)
        ],
    )

    return [
        support_conv,
        CommandHandler("my_tickets", SupportHandlers.my_tickets),
        CallbackQueryHandler(SupportHandlers.admin_view_tickets, pattern="^admin_support_tickets$"),
    ]
