"""
Handlers לניהול תשלומים ומשיכות
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.payment_service import PaymentService
from services.payout_service import PayoutService
from services.user_service import UserService
from services.notification_service import NotificationService
from config import Config
from database import db
from datetime import datetime
import random
import string
import logging

logger = logging.getLogger(__name__)

# States
ENTER_PAYOUT_AMOUNT, ENTER_PAYMENT_DETAILS = range(2)
ENTER_DEPOSIT_AMOUNT, WAITING_PAYMENT_PROOF = range(10, 12)


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
    def _generate_reference_code() -> str:
        """יצירת קוד ייחודי לזיהוי הפקדה"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    @staticmethod
    async def start_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך הוספת יתרה"""
        query = update.callback_query
        await query.answer()

        text = f"""
➕ *הוספת יתרה*

בחר סכום להטענה או שלח סכום מותאם אישית:

💡 מינימום הטענה: {Config.MIN_DEPOSIT_AMOUNT}₪
"""

        keyboard = [
            [
                InlineKeyboardButton("50₪", callback_data="deposit_amount_50"),
                InlineKeyboardButton("100₪", callback_data="deposit_amount_100"),
            ],
            [
                InlineKeyboardButton("200₪", callback_data="deposit_amount_200"),
                InlineKeyboardButton("500₪", callback_data="deposit_amount_500"),
            ],
            [InlineKeyboardButton("💰 סכום אחר", callback_data="deposit_custom")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def select_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת סכום הפקדה מוגדר מראש"""
        query = update.callback_query
        await query.answer()

        amount = int(query.data.replace("deposit_amount_", ""))
        context.user_data["deposit_amount"] = amount

        return await PaymentHandlers._show_payment_methods(update, context, amount)

    @staticmethod
    async def request_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בקשת סכום מותאם אישית"""
        query = update.callback_query
        await query.answer()

        text = f"""
💰 *סכום מותאם אישית*

שלח את הסכום שברצונך להטעין (בשקלים):

💡 מינימום: {Config.MIN_DEPOSIT_AMOUNT}₪

לביטול: /cancel
"""

        await query.edit_message_text(text, parse_mode="Markdown")
        return ENTER_DEPOSIT_AMOUNT

    @staticmethod
    async def process_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד סכום מותאם אישית"""
        try:
            amount = int(update.message.text.strip())
            if amount < Config.MIN_DEPOSIT_AMOUNT:
                await update.message.reply_text(
                    f"❌ סכום מינימלי להטענה: {Config.MIN_DEPOSIT_AMOUNT}₪\n"
                    f"שלח סכום גדול יותר או /cancel לביטול"
                )
                return ENTER_DEPOSIT_AMOUNT
        except ValueError:
            await update.message.reply_text(
                "❌ אנא שלח מספר תקין (ללא סימנים)\n"
                "לדוגמה: 150"
            )
            return ENTER_DEPOSIT_AMOUNT

        context.user_data["deposit_amount"] = amount
        return await PaymentHandlers._show_payment_methods_message(update, context, amount)

    @staticmethod
    async def _show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
        """הצגת אמצעי תשלום (מ-callback query)"""
        query = update.callback_query

        # יצירת קוד ייחודי
        ref_code = PaymentHandlers._generate_reference_code()
        context.user_data["deposit_ref"] = ref_code

        text = PaymentHandlers._build_payment_text(amount, ref_code)
        keyboard = [
            [InlineKeyboardButton("📸 שלחתי! להעלאת אישור", callback_data="upload_proof")],
            [InlineKeyboardButton("❌ ביטול", callback_data="my_balance")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    @staticmethod
    async def _show_payment_methods_message(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
        """הצגת אמצעי תשלום (מהודעה)"""
        # יצירת קוד ייחודי
        ref_code = PaymentHandlers._generate_reference_code()
        context.user_data["deposit_ref"] = ref_code

        text = PaymentHandlers._build_payment_text(amount, ref_code)
        keyboard = [
            [InlineKeyboardButton("📸 שלחתי! להעלאת אישור", callback_data="upload_proof")],
            [InlineKeyboardButton("❌ ביטול", callback_data="my_balance")]
        ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    @staticmethod
    def _build_payment_text(amount: int, ref_code: str) -> str:
        """בניית טקסט אמצעי תשלום"""
        text = f"""
💳 *הטענת {amount}₪*

📋 *קוד הזיהוי שלך:* `{ref_code}`
⚠️ *חשוב לציין את הקוד בהעברה!*

━━━━━━━━━━━━━━━━━━━━

"""
        # הוספת אמצעי תשלום זמינים
        payment_methods_available = False

        if Config.BIT_PHONE:
            text += f"""📱 *ביט / פייבוקס:*
   טלפון: `{Config.BIT_PHONE}`
   סכום: {amount}₪
   הערה: {ref_code}

"""
            payment_methods_available = True

        if Config.PAYBOX_LINK:
            text += f"""🔗 *פייבוקס (לינק):*
   {Config.PAYBOX_LINK}

"""
            payment_methods_available = True

        if Config.BANK_NAME and Config.BANK_ACCOUNT:
            text += f"""🏦 *העברה בנקאית:*
   בנק: {Config.BANK_NAME}
   סניף: {Config.BANK_BRANCH}
   חשבון: {Config.BANK_ACCOUNT}
   ע"ש: {Config.BANK_OWNER}
   סכום: {amount}₪
   הערה: {ref_code}

"""
            payment_methods_available = True

        if not payment_methods_available:
            text += """⚠️ *אמצעי תשלום לא הוגדרו*
   פנה לתמיכה: /support

"""

        text += """━━━━━━━━━━━━━━━━━━━━

✅ *אחרי ששילמת:*
לחץ על הכפתור למטה ושלח צילום מסך של האישור
"""
        return text

    @staticmethod
    async def request_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בקשת אישור תשלום"""
        query = update.callback_query
        await query.answer()

        amount = context.user_data.get("deposit_amount")
        ref_code = context.user_data.get("deposit_ref")

        if not amount or not ref_code:
            await query.edit_message_text(
                "❌ פג תוקף הבקשה. לחץ על 'הוסף יתרה' מחדש.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ הוסף יתרה", callback_data="add_balance")
                ]])
            )
            return ConversationHandler.END

        text = f"""
📸 *העלאת אישור תשלום*

סכום: *{amount}₪*
קוד זיהוי: `{ref_code}`

📤 שלח צילום מסך של אישור ההעברה/תשלום.

💡 וודא שרואים בתמונה:
• סכום ההעברה
• תאריך ושעה
• קוד הזיהוי (אם רשמת)

לביטול: /cancel
"""

        await query.edit_message_text(text, parse_mode="Markdown")
        return WAITING_PAYMENT_PROOF

    @staticmethod
    async def process_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד אישור תשלום"""
        user_id = update.effective_user.id
        user = update.effective_user
        amount = context.user_data.get("deposit_amount")
        ref_code = context.user_data.get("deposit_ref")

        if not amount or not ref_code:
            await update.message.reply_text(
                "❌ פג תוקף הבקשה. התחל מחדש עם 'יתרה והטענה'"
            )
            return ConversationHandler.END

        # קבלת התמונה
        photo = None
        if update.message.photo:
            photo = update.message.photo[-1].file_id  # הגדולה ביותר
        elif update.message.document:
            photo = update.message.document.file_id

        if not photo:
            await update.message.reply_text(
                "❌ אנא שלח תמונה (צילום מסך) של אישור התשלום.\n"
                "לביטול: /cancel"
            )
            return WAITING_PAYMENT_PROOF

        # שמירת בקשת הפקדה במסד נתונים
        deposit_request = {
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "amount": amount,
            "reference_code": ref_code,
            "proof_file_id": photo,
            "status": "pending",  # pending, approved, rejected
            "created_at": datetime.utcnow(),
            "processed_at": None,
            "processed_by": None,
            "rejection_reason": None
        }

        result = await db.deposit_requests.insert_one(deposit_request)
        request_id = str(result.inserted_id)

        # שליחת התראה לאדמינים
        for admin_id in Config.ADMIN_IDS:
            try:
                admin_text = f"""
💰 *בקשת הפקדה חדשה*

👤 מאת: {user.first_name} (@{user.username or 'ללא'})
🆔 ID: `{user_id}`
💵 סכום: *{amount}₪*
📋 קוד: `{ref_code}`

🔍 מזהה בקשה: `{request_id[:8]}`
"""
                admin_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ אשר", callback_data=f"approve_deposit_{request_id}"),
                        InlineKeyboardButton("❌ דחה", callback_data=f"reject_deposit_{request_id}")
                    ]
                ])

                # שליחת התמונה לאדמין
                from telegram import Bot
                bot: Bot = context.bot
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=photo,
                    caption=admin_text,
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

        # אישור למשתמש
        await update.message.reply_text(
            f"""
✅ *הבקשה נשלחה בהצלחה!*

💵 סכום: {amount}₪
📋 קוד זיהוי: `{ref_code}`
🔍 מזהה בקשה: `{request_id[:8]}`

⏳ הבקשה נשלחה לאישור.
תקבל הודעה ברגע שהיתרה תתעדכן.

📊 בדרך כלל תוך מספר דקות עד שעה.
""",
            parse_mode="Markdown"
        )

        # ניקוי
        context.user_data.pop("deposit_amount", None)
        context.user_data.pop("deposit_ref", None)

        return ConversationHandler.END

    @staticmethod
    async def approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור הפקדה (אדמין)"""
        query = update.callback_query
        await query.answer()

        admin_id = update.effective_user.id
        if admin_id not in Config.ADMIN_IDS:
            await query.edit_message_caption("❌ אין לך הרשאות")
            return

        from bson import ObjectId
        request_id = query.data.replace("approve_deposit_", "")

        # מציאת הבקשה
        deposit = await db.deposit_requests.find_one({"_id": ObjectId(request_id)})
        if not deposit:
            await query.edit_message_caption("❌ בקשה לא נמצאה")
            return

        if deposit["status"] != "pending":
            await query.edit_message_caption(f"⚠️ הבקשה כבר טופלה (סטטוס: {deposit['status']})")
            return

        # עדכון יתרת המשתמש
        success = await PaymentService.add_balance(
            deposit["user_id"],
            deposit["amount"],
            f"הפקדה - קוד {deposit['reference_code']}"
        )

        if not success:
            await query.edit_message_caption("❌ שגיאה בעדכון היתרה")
            return

        # עדכון סטטוס הבקשה
        await db.deposit_requests.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "approved",
                    "processed_at": datetime.utcnow(),
                    "processed_by": admin_id
                }
            }
        )

        # עדכון הודעת האדמין
        new_caption = query.message.caption + f"\n\n✅ *אושר* על ידי אדמין {admin_id}"
        await query.edit_message_caption(new_caption, parse_mode="Markdown")

        # הודעה למשתמש
        try:
            from telegram import Bot
            bot: Bot = context.bot
            await bot.send_message(
                chat_id=deposit["user_id"],
                text=f"""
✅ *ההפקדה אושרה!*

💵 סכום: {deposit['amount']}₪
📋 קוד: `{deposit['reference_code']}`

היתרה שלך עודכנה בהצלחה! 🎉
לחץ /balance לצפייה ביתרה
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    @staticmethod
    async def reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דחיית הפקדה (אדמין)"""
        query = update.callback_query
        await query.answer()

        admin_id = update.effective_user.id
        if admin_id not in Config.ADMIN_IDS:
            await query.edit_message_caption("❌ אין לך הרשאות")
            return

        from bson import ObjectId
        request_id = query.data.replace("reject_deposit_", "")

        # מציאת הבקשה
        deposit = await db.deposit_requests.find_one({"_id": ObjectId(request_id)})
        if not deposit:
            await query.edit_message_caption("❌ בקשה לא נמצאה")
            return

        if deposit["status"] != "pending":
            await query.edit_message_caption(f"⚠️ הבקשה כבר טופלה (סטטוס: {deposit['status']})")
            return

        # עדכון סטטוס הבקשה
        await db.deposit_requests.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "rejected",
                    "processed_at": datetime.utcnow(),
                    "processed_by": admin_id,
                    "rejection_reason": "לא אושר על ידי אדמין"
                }
            }
        )

        # עדכון הודעת האדמין
        new_caption = query.message.caption + f"\n\n❌ *נדחה* על ידי אדמין {admin_id}"
        await query.edit_message_caption(new_caption, parse_mode="Markdown")

        # הודעה למשתמש
        try:
            from telegram import Bot
            bot: Bot = context.bot
            await bot.send_message(
                chat_id=deposit["user_id"],
                text=f"""
❌ *ההפקדה נדחתה*

💵 סכום: {deposit['amount']}₪
📋 קוד: `{deposit['reference_code']}`

הבקשה לא אושרה. 
אם אתה בטוח שביצעת את ההעברה, פנה לתמיכה: /support
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    @staticmethod
    async def my_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפקדות שלי"""
        user_id = update.effective_user.id

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

        await update.message.reply_text(text, parse_mode="Markdown")

    @staticmethod
    async def cancel_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול תהליך הפקדה"""
        context.user_data.pop("deposit_amount", None)
        context.user_data.pop("deposit_ref", None)
        await update.message.reply_text("❌ תהליך ההפקדה בוטל")
        return ConversationHandler.END

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

    # Conversation לסכום הפקדה מותאם אישית
    custom_deposit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(PaymentHandlers.request_custom_amount, pattern="^deposit_custom$")
        ],
        states={
            ENTER_DEPOSIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_custom_amount)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", PaymentHandlers.cancel_deposit)
        ],
    )

    # Conversation להעלאת אישור תשלום
    proof_upload_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(PaymentHandlers.request_payment_proof, pattern="^upload_proof$")
        ],
        states={
            WAITING_PAYMENT_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, PaymentHandlers.process_payment_proof)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", PaymentHandlers.cancel_deposit)
        ],
    )

    return [
        CommandHandler("balance", PaymentHandlers.my_balance),
        CommandHandler("my_payouts", PaymentHandlers.my_payouts),
        CommandHandler("my_deposits", PaymentHandlers.my_deposits),
        CallbackQueryHandler(PaymentHandlers.my_balance, pattern="^my_balance$"),
        CallbackQueryHandler(PaymentHandlers.transaction_history, pattern="^transaction_history$"),
        # תהליך הפקדה
        CallbackQueryHandler(PaymentHandlers.start_add_balance, pattern="^add_balance$"),
        CallbackQueryHandler(PaymentHandlers.select_deposit_amount, pattern="^deposit_amount_"),
        custom_deposit_conv,
        proof_upload_conv,
        # אדמין - אישור/דחיית הפקדות
        CallbackQueryHandler(PaymentHandlers.approve_deposit, pattern="^approve_deposit_"),
        CallbackQueryHandler(PaymentHandlers.reject_deposit, pattern="^reject_deposit_"),
        payout_conv
    ]
