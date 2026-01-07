"""
Handlers למערכת מחלוקות
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.dispute_service import DisputeService
from services.user_service import UserService
from database import db
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

# States
ENTER_DISPUTE_REASON, ENTER_DISPUTE_MESSAGE = range(2)


class DisputeHandlers:
    """Handlers עבור מחלוקות"""

    @staticmethod
    async def start_dispute(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך פתיחת מחלוקת"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        order_id = query.data.split("_")[-1]

        # בדיקת זכאות
        can_open, error = await DisputeService.can_open_dispute(user_id, order_id)

        if not can_open:
            await query.edit_message_text(error)
            return ConversationHandler.END

        # שמירת order_id
        context.user_data["dispute_order_id"] = order_id

        await query.edit_message_text(
            "⚠️ *פתיחת מחלוקת*\n\n"
            "אנא תאר את הבעיה (עד 500 תווים):\n\n"
            "לדוגמה:\n"
            "- הקוד לא עובד\n"
            "- לא קיבלתי את הקופון\n"
            "- המוצר לא תואם את התיאור",
            parse_mode="Markdown"
        )

        return ENTER_DISPUTE_REASON

    @staticmethod
    async def process_dispute_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד סיבת המחלוקת"""
        user_id = update.effective_user.id
        order_id = context.user_data.get("dispute_order_id")
        reason = update.message.text[:500]

        if len(reason) < 10:
            await update.message.reply_text("❌ אנא תאר את הבעיה ביתר פירוט (לפחות 10 תווים)")
            return ENTER_DISPUTE_REASON

        # פתיחת מחלוקת
        result = await DisputeService.open_dispute(user_id, order_id, reason)

        if isinstance(result, str) and result.startswith("❌"):
            await update.message.reply_text(result)
            return ConversationHandler.END

        dispute_id = result

        await update.message.reply_text(
            f"✅ *מחלוקת נפתחה בהצלחה*\n\n"
            f"מספר מחלוקת: {dispute_id[:8]}\n\n"
            f"המוכר קיבל התראה והמחלוקת הועברה לטיפול.\n"
            f"תקבל עדכון כאשר תהיה תגובה.\n\n"
            f"💬 תוכל להוסיף הודעות נוספות דרך /my_disputes",
            parse_mode="Markdown"
        )

        # ניקוי קונטקסט
        context.user_data.pop("dispute_order_id", None)

        return ConversationHandler.END

    @staticmethod
    async def my_disputes(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """המחלוקות שלי"""
        user_id = update.effective_user.id

        # קבלת מחלוקות כקונה
        buyer_disputes = await DisputeService.get_user_disputes(user_id, as_buyer=True)

        # קבלת מחלוקות כמוכר
        user = await UserService.get_user(user_id)
        seller_disputes = []
        if user and user.role in ["seller_verified", "seller_unverified"]:
            seller_disputes = await DisputeService.get_user_disputes(user_id, as_buyer=False)

        if not buyer_disputes and not seller_disputes:
            await update.message.reply_text(
                "⚖️ *המחלוקות שלי*\n\n"
                "אין לך מחלוקות פתוחות\n\n"
                "💡 ניתן לפתוח מחלוקת מדף 'ההזמנות שלי'",
                parse_mode="Markdown"
            )
            return

        text = "⚖️ *המחלוקות שלי*\n\n"

        keyboard = []

        if buyer_disputes:
            text += "📦 *כקונה:*\n\n"
            for i, dispute in enumerate(buyer_disputes[:5], 1):
                coupon = dispute.get("coupon", {})
                status_emoji = {
                    "open": "🟡",
                    "in_progress": "🔵",
                    "resolved_refund": "✅",
                    "resolved_no_refund": "❌",
                    "closed": "⚫"
                }.get(dispute["status"], "❓")

                text += f"{i}. {status_emoji} {coupon.get('title', 'קופון')}\n"
                text += f"   סטטוס: {dispute['status']}\n"
                text += f"   נפתחה: {dispute['created_at'].strftime('%d/%m/%Y')}\n\n"

                keyboard.append([InlineKeyboardButton(
                    f"#{i} - פרטים",
                    callback_data=f"dispute_view_{dispute['_id']}"
                )])

        if seller_disputes:
            text += "\n💼 *כמוכר:*\n\n"
            for i, dispute in enumerate(seller_disputes[:5], 1):
                coupon = dispute.get("coupon", {})
                status_emoji = {
                    "open": "🟡",
                    "in_progress": "🔵",
                    "resolved_refund": "❌",
                    "resolved_no_refund": "✅",
                    "closed": "⚫"
                }.get(dispute["status"], "❓")

                text += f"{i}. {status_emoji} {coupon.get('title', 'קופון')}\n"
                text += f"   סטטוס: {dispute['status']}\n\n"

                keyboard.append([InlineKeyboardButton(
                    f"מוכר #{i} - פרטים",
                    callback_data=f"dispute_view_{dispute['_id']}"
                )])

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode="Markdown"
        )

    @staticmethod
    async def view_dispute(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפרטי מחלוקת"""
        query = update.callback_query
        await query.answer()

        dispute_id = query.data.split("_")[-1]
        dispute = await DisputeService.get_dispute_by_id(dispute_id)

        if not dispute:
            await query.edit_message_text("❌ מחלוקת לא נמצאה")
            return

        order = dispute.get("order", {})
        coupon = dispute.get("coupon", {})

        status_text = {
            "open": "🟡 פתוחה",
            "in_progress": "🔵 בטיפול",
            "resolved_refund": "✅ נפתרה - החזר כספי",
            "resolved_no_refund": "❌ נפתרה - ללא החזר",
            "closed": "⚫ סגורה"
        }.get(dispute["status"], "❓ לא ידוע")

        text = f"⚖️ *פרטי מחלוקת*\n\n"
        text += f"📦 *קופון:* {coupon.get('title', 'לא ידוע')}\n"
        text += f"💰 סכום: {order.get('price_paid', 0):.2f}₪\n\n"

        text += f"📊 *סטטוס:* {status_text}\n"
        text += f"📅 נפתחה: {dispute['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"

        text += f"💬 *הסיבה:*\n{dispute['reason']}\n\n"

        if dispute.get("resolution"):
            text += f"✅ *פתרון:*\n{dispute['resolution']}\n\n"

        # קבלת הודעות
        messages = await DisputeService.get_dispute_messages(dispute_id)

        if messages:
            text += f"📝 *הודעות ({len(messages)}):*\n\n"
            for msg in messages[-5:]:  # 5 אחרונות
                text += f"• {msg['sender_name']}: {msg['message'][:100]}\n"

        keyboard = []

        if dispute["status"] == "open":
            keyboard.append([InlineKeyboardButton(
                "💬 הוסף הודעה",
                callback_data=f"dispute_msg_{dispute_id}"
            )])

        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="my_disputes")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def add_dispute_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת הוספת הודעה למחלוקת"""
        query = update.callback_query
        await query.answer()

        dispute_id = query.data.split("_")[-1]
        context.user_data["dispute_message_id"] = dispute_id

        await query.edit_message_text(
            "💬 *הוספת הודעה למחלוקת*\n\n"
            "כתוב את ההודעה שלך למטה:",
            parse_mode="Markdown"
        )

        return ENTER_DISPUTE_MESSAGE

    @staticmethod
    async def add_dispute_message_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד הוספת הודעה"""
        user_id = update.effective_user.id
        dispute_id = context.user_data.get("dispute_message_id")
        message = update.message.text[:500]

        error = await DisputeService.add_dispute_message(dispute_id, user_id, message)

        if error:
            await update.message.reply_text(error)
            return ConversationHandler.END

        await update.message.reply_text(
            "✅ ההודעה נוספה למחלוקת\n\n"
            "הצד השני יקבל התראה"
        )

        context.user_data.pop("dispute_message_id", None)
        return ConversationHandler.END

    @staticmethod
    async def cancel_dispute_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול פעולה"""
        context.user_data.pop("dispute_order_id", None)
        context.user_data.pop("dispute_message_id", None)
        await update.message.reply_text("❌ פעולה בוטלה")
        return ConversationHandler.END


def get_dispute_handlers():
    """החזרת handlers למחלוקות"""

    # Conversation לפתיחת מחלוקת
    open_dispute_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(DisputeHandlers.start_dispute, pattern="^dispute_open_")
        ],
        states={
            ENTER_DISPUTE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, DisputeHandlers.process_dispute_reason)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", DisputeHandlers.cancel_dispute_action)
        ],
    )

    # Conversation להוספת הודעה
    add_message_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(DisputeHandlers.add_dispute_message_start, pattern="^dispute_msg_")
        ],
        states={
            ENTER_DISPUTE_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, DisputeHandlers.add_dispute_message_process)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", DisputeHandlers.cancel_dispute_action)
        ],
    )

    return [
        CommandHandler("my_disputes", DisputeHandlers.my_disputes),
        CallbackQueryHandler(DisputeHandlers.view_dispute, pattern="^dispute_view_"),
        CallbackQueryHandler(DisputeHandlers.my_disputes, pattern="^my_disputes$"),
        open_dispute_conv,
        add_message_conv
    ]
