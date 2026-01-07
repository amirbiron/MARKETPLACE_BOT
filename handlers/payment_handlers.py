"""
Handlers לניהול תשלומים ומשיכות
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.payment_service import PaymentService
from services.payout_service import PayoutService
from services.user_service import UserService
from config import Config
import logging

logger = logging.getLogger(__name__)

# States
ENTER_PAYOUT_AMOUNT, ENTER_PAYMENT_DETAILS = range(2)


class PaymentHandlers:
    """Handlers עבור תשלומים"""

    @staticmethod
    async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה ביתרה"""
        user_id = update.effective_user.id

        balance, frozen = await PaymentService.get_user_balance(user_id)

        text = "💰 *היתרה שלי*\n\n"
        text += f"💵 יתרה זמינה: {balance:.2f}₪\n"

        if frozen > 0:
            text += f"🔒 יתרה קפואה: {frozen:.2f}₪\n"
            text += f"💎 סה\"כ: {(balance + frozen):.2f}₪\n\n"
            text += "💡 יתרה קפואה = כסף בהצעות במכרזים\n"
        else:
            text += f"\n💡 יתרה קפואה: 0₪\n"

        keyboard = [
            [InlineKeyboardButton("➕ הוסף יתרה", callback_data="add_balance")],
            [InlineKeyboardButton("📊 היסטוריית תנועות", callback_data="transaction_history")]
        ]

        # אם מוכר - הצג אפשרות משיכה
        user = await UserService.get_user(user_id)
        if user and user.role in ["seller_verified", "seller_unverified"]:
            available = await PayoutService.calculate_available_for_payout(user_id)
            text += f"\n💸 זמין למשיכה: {available:.2f}₪\n"

            if available >= Config.MIN_PAYOUT_AMOUNT:
                keyboard.insert(1, [InlineKeyboardButton("💸 בקשת משיכה", callback_data="request_payout")])

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """היסטוריית תנועות"""
        query = update.callback_query
        if query:
            await query.answer()

        user_id = update.effective_user.id
        transactions = await PaymentService.get_transaction_history(user_id, limit=20)

        text = "📊 *היסטוריית תנועות*\n\n"

        if not transactions:
            text += "אין תנועות עדיין"
        else:
            for txn in transactions[:15]:
                amount = txn["amount"]
                sign = "+" if amount > 0 else ""
                emoji = "💰" if amount > 0 else "💸"

                text += f"{emoji} {sign}{amount:.2f}₪\n"
                text += f"   {txn['description']}\n"
                text += f"   {txn['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"

        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]]

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
    async def add_balance_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הוראות להוספת יתרה"""
        query = update.callback_query
        await query.answer()

        text = "➕ *הוספת יתרה*\n\n"
        text += "📱 *דרכי תשלום:*\n\n"
        text += "1️⃣ העברה בנקאית:\n"
        text += "   בנק: XX\n"
        text += "   סניף: XXXX\n"
        text += "   חשבון: XXXXXXX\n\n"
        text += "2️⃣ PayPal / ביט:\n"
        text += "   טלפון: 050-XXXXXXX\n\n"
        text += "3️⃣ כרטיס אשראי (בקרוב)\n\n"
        text += "⚠️ *חשוב:*\n"
        text += "לאחר התשלום, שלח אסמכתא ל-@admin\n"
        text += "היתרה תתווסף תוך 24 שעות\n\n"
        text += "💡 מינימום הטענה: 50₪"

        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def request_payout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך בקשת משיכה"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id

        # בדיקת זכאות
        available = await PayoutService.calculate_available_for_payout(user_id)

        if available < Config.MIN_PAYOUT_AMOUNT:
            await query.edit_message_text(
                f"❌ יתרה לא מספיקה למשיכה\n\n"
                f"זמין: {available:.2f}₪\n"
                f"מינימום: {Config.MIN_PAYOUT_AMOUNT}₪"
            )
            return ConversationHandler.END

        balance, frozen = await PaymentService.get_user_balance(user_id)

        text = "💸 *בקשת משיכת כספים*\n\n"
        text += f"💵 יתרה זמינה: {balance:.2f}₪\n"
        text += f"💎 זמין למשיכה: {available:.2f}₪\n\n"
        text += f"📌 מינימום משיכה: {Config.MIN_PAYOUT_AMOUNT}₪\n"
        text += f"📌 עמלת משיכה: {Config.SELLER_COMMISSION_RATE*100:.0f}%\n\n"
        text += "כמה ברצונך למשוך? (שלח סכום בשקלים)"

        await query.edit_message_text(text, parse_mode="Markdown")

        return ENTER_PAYOUT_AMOUNT

    @staticmethod
    async def process_payout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד סכום המשיכה"""
        user_id = update.effective_user.id

        try:
            amount = float(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין")
            return ENTER_PAYOUT_AMOUNT

        # בדיקת זכאות
        can_request, error = await PayoutService.can_request_payout(user_id, amount)

        if not can_request:
            await update.message.reply_text(error)
            return ConversationHandler.END

        # חישוב סכום נטו
        commission = amount * Config.SELLER_COMMISSION_RATE
        net_amount = amount - commission

        context.user_data["payout_amount"] = amount

        text = f"💸 *אישור בקשת משיכה*\n\n"
        text += f"סכום מבוקש: {amount:.2f}₪\n"
        text += f"עמלה ({Config.SELLER_COMMISSION_RATE*100:.0f}%): -{commission:.2f}₪\n"
        text += f"תקבל: {net_amount:.2f}₪\n\n"
        text += f"📱 פרטי העברה:\n"
        text += f"שלח את פרטי החשבון/PayPal/ביט שלך\n"
        text += f"לדוגמה: 'בנק XX, סניף 123, חשבון 456789'\n"
        text += f"או 'PayPal: email@example.com'"

        await update.message.reply_text(text, parse_mode="Markdown")

        return ENTER_PAYMENT_DETAILS

    @staticmethod
    async def process_payment_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד פרטי תשלום ויצירת בקשה"""
        user_id = update.effective_user.id
        amount = context.user_data.get("payout_amount")
        payment_details_text = update.message.text

        payment_details = {"details": payment_details_text}

        # יצירת בקשת משיכה
        result = await PayoutService.request_payout(user_id, amount, payment_details)

        if isinstance(result, str) and result.startswith("❌"):
            await update.message.reply_text(result)
            return ConversationHandler.END

        commission = amount * Config.SELLER_COMMISSION_RATE
        net_amount = amount - commission

        await update.message.reply_text(
            f"✅ *בקשת המשיכה נשלחה!*\n\n"
            f"סכום: {amount:.2f}₪\n"
            f"תקבל: {net_amount:.2f}₪\n\n"
            f"הבקשה ממתינה לאישור אדמין\n"
            f"תקבל התראה בעת אישור\n\n"
            f"⏰ זמן עיבוד: עד 24 שעות",
            parse_mode="Markdown"
        )

        # ניקוי קונטקסט
        context.user_data.pop("payout_amount", None)

        return ConversationHandler.END

    @staticmethod
    async def my_payouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """המשיכות שלי"""
        user_id = update.effective_user.id

        payouts = await PayoutService.get_seller_payouts(user_id)

        if not payouts:
            text = "💸 *המשיכות שלי*\n\n"
            text += "אין לך בקשות משיכה\n\n"
            text += "💡 השתמש ב-/balance כדי לבקש משיכה"
        else:
            text = "💸 *המשיכות שלי*\n\n"

            for i, payout in enumerate(payouts[:10], 1):
                status_emoji = {
                    "pending": "🟡",
                    "approved": "✅",
                    "rejected": "❌"
                }.get(payout["status"], "❓")

                text += f"{i}. {status_emoji} {payout['net_amount']:.2f}₪\n"
                text += f"   סטטוס: {payout['status']}\n"
                text += f"   תאריך: {payout['created_at'].strftime('%d/%m/%Y')}\n"

                if payout.get("rejection_reason"):
                    text += f"   סיבה: {payout['rejection_reason']}\n"

                text += "\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    @staticmethod
    async def cancel_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול בקשת משיכה"""
        context.user_data.pop("payout_amount", None)
        await update.message.reply_text("❌ בקשת משיכה בוטלה")
        return ConversationHandler.END


def get_payment_handlers():
    """החזרת handlers לתשלומים"""

    # Conversation לבקשת משיכה
    payout_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(PaymentHandlers.request_payout_start, pattern="^request_payout$")
        ],
        states={
            ENTER_PAYOUT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_payout_amount)
            ],
            ENTER_PAYMENT_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_payment_details)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", PaymentHandlers.cancel_payout)
        ],
    )

    return [
        CommandHandler("balance", PaymentHandlers.my_balance),
        CommandHandler("my_payouts", PaymentHandlers.my_payouts),
        CallbackQueryHandler(PaymentHandlers.my_balance, pattern="^my_balance$"),
        CallbackQueryHandler(PaymentHandlers.transaction_history, pattern="^transaction_history$"),
        CallbackQueryHandler(PaymentHandlers.add_balance_info, pattern="^add_balance$"),
        payout_conv
    ]
