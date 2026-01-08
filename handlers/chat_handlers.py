"""
Handlers למערכת צ'אט
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.chat_service import ChatService
from services.user_service import UserService
from database import db
import logging

logger = logging.getLogger(__name__)

# States
WAITING_FOR_MESSAGE, SELECT_CHAT = range(2)


class ChatHandlers:
    """Handlers עבור צ'אט"""

    @staticmethod
    async def my_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצ'אטים שלי"""
        user_id = update.effective_user.id
        query = update.callback_query

        chats = await ChatService.get_user_chats(user_id)

        keyboard = []
        
        if not chats:
            text = "💬 *הצ'אטים שלי*\n\n"
            text += "אין לך שיחות פעילות\n\n"
            text += "💡 תוכל לפתוח שיחה עם מוכר מדף הקופון"
            keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        text = "💬 *הצ'אטים שלי*\n\n"

        for i, chat in enumerate(chats[:10], 1):
            unread_emoji = "🔴" if chat.get("unread_count", 0) > 0 else "💬"

            text += f"{i}. {unread_emoji} *{chat['other_user_name']}* ({chat['other_user_role']})\n"
            text += f"   {chat.get('last_message', 'אין הודעות')[:50]}\n"

            if chat.get("unread_count", 0) > 0:
                text += f"   🔔 {chat['unread_count']} הודעות חדשות\n"

            text += "\n"

            keyboard.append([InlineKeyboardButton(
                f"{unread_emoji} {chat['other_user_name'][:20]}",
                callback_data=f"chat_open_{chat['_id']}"
            )])

        keyboard.append([InlineKeyboardButton("🔄 רענן", callback_data="my_chats_refresh")])
        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

        if query:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    @staticmethod
    async def open_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פתיחת שיחה"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        chat_id = query.data.split("_")[-1]

        # שמירת chat_id בקונטקסט
        context.user_data["current_chat_id"] = chat_id

        # קבלת הודעות
        messages = await ChatService.get_chat_messages(chat_id, user_id, limit=20)

        if messages is None:
            await query.edit_message_text("❌ שיחה לא נמצאה או אין לך גישה")
            return ConversationHandler.END

        # קבלת מידע על השיחה
        chat = await ChatService.get_chat_by_id(chat_id, user_id)

        if not chat:
            await query.edit_message_text("❌ שיחה לא נמצאה")
            return ConversationHandler.END

        # קביעת השם של הצד השני
        is_buyer = user_id == chat["buyer_id"]
        other_user_id = chat["seller_id"] if is_buyer else chat["buyer_id"]

        other_user = await db.users.find_one({"user_id": other_user_id})
        other_name = other_user.get("first_name") or other_user.get("business_name", "משתמש") if other_user else "משתמש"

        text = f"💬 *שיחה עם {other_name}*\n\n"

        if not messages:
            text += "אין הודעות עדיין. שלח הודעה ראשונה!\n\n"
        else:
            text += "📝 *הודעות אחרונות:*\n\n"

            for msg in messages[-10:]:  # 10 הודעות אחרונות
                is_me = msg["sender_id"] == user_id
                sender_name = "אתה" if is_me else other_name
                time_str = msg["created_at"].strftime("%H:%M")

                prefix = "➡️" if is_me else "⬅️"
                text += f"{prefix} *{sender_name}* ({time_str}):\n"
                text += f"   {msg['message']}\n\n"

        text += "✍️ כתוב הודעה למטה או לחץ 'סגור שיחה' כדי לצאת."

        keyboard = [[
            InlineKeyboardButton("🔄 רענן", callback_data=f"chat_open_{chat_id}"),
            InlineKeyboardButton("🚪 סגור שיחה", callback_data=f"chat_close_{chat_id}")
        ]]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

        return WAITING_FOR_MESSAGE

    @staticmethod
    async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שליחת הודעה בצ'אט"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get("current_chat_id")

        if not chat_id:
            await update.message.reply_text("❌ לא נבחרה שיחה. השתמש ב-/chats כדי לפתוח שיחה")
            return ConversationHandler.END

        message_text = update.message.text

        # שליחת ההודעה
        result = await ChatService.send_message(chat_id, user_id, message_text)

        if isinstance(result, str) and result.startswith("❌"):
            await update.message.reply_text(result)
            return ConversationHandler.END

        await update.message.reply_text(
            "✅ ההודעה נשלחה!\n\n"
            "כתוב הודעה נוספת או השתמש ב-/chats כדי לחזור לרשימת השיחות"
        )

        return WAITING_FOR_MESSAGE

    @staticmethod
    async def close_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סגירת שיחה"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        chat_id = query.data.split("_")[-1]

        error = await ChatService.close_chat(chat_id, user_id)

        if error:
            await query.edit_message_text(error)
            return ConversationHandler.END

        await query.edit_message_text(
            "✅ השיחה נסגרה\n\n"
            "השתמש ב-/chats כדי לראות שיחות אחרות"
        )

        # ניקוי קונטקסט
        context.user_data.pop("current_chat_id", None)

        return ConversationHandler.END

    @staticmethod
    async def start_chat_with_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת שיחה עם מוכר (מתוך קופון)"""
        query = update.callback_query
        await query.answer()

        buyer_id = update.effective_user.id
        seller_id = int(query.data.split("_")[-1])

        # יצירת או קבלת שיחה קיימת
        chat_id = await ChatService.create_chat(buyer_id, seller_id)

        if not chat_id:
            await query.edit_message_text("❌ שגיאה ביצירת שיחה")
            return

        # שמירת chat_id
        context.user_data["current_chat_id"] = chat_id

        seller = await db.users.find_one({"user_id": seller_id})
        seller_name = seller.get("business_name", "מוכר") if seller else "מוכר"

        await query.edit_message_text(
            f"💬 *שיחה עם {seller_name}*\n\n"
            f"השיחה נפתחה. כתוב הודעה למטה.\n\n"
            f"💡 ההודעות אנונימיות - המוכר לא רואה את המספר שלך",
            parse_mode="Markdown"
        )

        return WAITING_FOR_MESSAGE

    @staticmethod
    async def cancel_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול שיחה"""
        context.user_data.pop("current_chat_id", None)
        await update.message.reply_text("❌ שיחה בוטלה")
        return ConversationHandler.END

    @staticmethod
    async def refresh_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """רענון רשימת שיחות"""
        query = update.callback_query
        await query.answer("מרענן...")

        user_id = update.effective_user.id
        chats = await ChatService.get_user_chats(user_id)

        if not chats:
            text = "💬 *הצ'אטים שלי*\n\n"
            text += "אין לך שיחות פעילות"
        else:
            text = "💬 *הצ'אטים שלי*\n\n"

            keyboard = []
            for i, chat in enumerate(chats[:10], 1):
                unread_emoji = "🔴" if chat.get("unread_count", 0) > 0 else "💬"

                text += f"{i}. {unread_emoji} *{chat['other_user_name']}* ({chat['other_user_role']})\n"
                text += f"   {chat.get('last_message', 'אין הודעות')[:50]}\n"

                if chat.get("unread_count", 0) > 0:
                    text += f"   🔔 {chat['unread_count']} הודעות חדשות\n"

                text += "\n"

                keyboard.append([InlineKeyboardButton(
                    f"{unread_emoji} {chat['other_user_name'][:20]}",
                    callback_data=f"chat_open_{chat['_id']}"
                )])

            keyboard.append([InlineKeyboardButton("🔄 רענן", callback_data="my_chats_refresh")])

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )


def get_chat_handlers():
    """החזרת handlers לצ'אט"""

    chat_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ChatHandlers.open_chat, pattern="^chat_open_"),
            CallbackQueryHandler(ChatHandlers.start_chat_with_seller, pattern="^chat_seller_")
        ],
        states={
            WAITING_FOR_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ChatHandlers.send_message),
                CallbackQueryHandler(ChatHandlers.open_chat, pattern="^chat_open_"),
                CallbackQueryHandler(ChatHandlers.close_chat, pattern="^chat_close_")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", ChatHandlers.cancel_chat),
            CommandHandler("chats", ChatHandlers.my_chats)
        ],
        allow_reentry=True
    )

    return [
        CommandHandler("chats", ChatHandlers.my_chats),
        CallbackQueryHandler(ChatHandlers.refresh_chats, pattern="^my_chats_refresh$"),
        chat_conv
    ]
