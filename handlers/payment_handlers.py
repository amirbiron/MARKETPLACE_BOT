"""
Handlers לניהול תשלומים ומשיכות
תמיכה בסליקה/אשראי
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.payment_service import PaymentService
from services.payment_gateway_service import PaymentGatewayService
from services.payout_service import PayoutService
from services.user_service import UserService
from services.notification_service import NotificationService
from models import PaymentTransactionType, PayoutMethod
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
# Credit card states
CC_SELECT_AMOUNT, CC_SELECT_CARD, CC_ENTER_PAYPAL, CC_ENTER_BANK = range(20, 24)
# Payout method states
PAYOUT_SELECT_METHOD, PAYOUT_ENTER_DETAILS = range(30, 32)


class PaymentHandlers:
    """Handlers עבור תשלומים"""

    @staticmethod
    async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה ביתרה - תומך גם ב-message וגם ב-callback_query"""
        user_id = update.effective_user.id
        query = update.callback_query
        
        # אם זה callback query, ענה עליו קודם
        if query:
            await query.answer()

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

        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

        # תמיכה גם ב-callback_query וגם ב-message
        if query:
            try:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception:
                # אם לא ניתן לערוך את ההודעה, שלח הודעה חדשה
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
        elif update.message:
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

    # ==================== Credit Card Payment Handlers ====================

    @staticmethod
    async def start_credit_card_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תשלום בכרטיס אשראי"""
        query = update.callback_query
        if query:
            await query.answer()
        
        if not Config.PAYMENT_GATEWAY_ENABLED:
            text = "❌ *תשלום בכרטיס אשראי אינו זמין כרגע*\n\nאנא השתמש בשיטות התשלום האחרות."
            if query:
                await query.edit_message_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, parse_mode="Markdown")
            return ConversationHandler.END
        
        text = f"""
💳 *תשלום בכרטיס אשראי*

בחר סכום לטעינה או שלח סכום מותאם אישית:

💡 מינימום: {Config.MIN_CARD_PAYMENT}₪
💡 מקסימום לעסקה: {Config.MAX_TRANSACTION_AMOUNT}₪
💡 מגבלה יומית: {Config.DAILY_CARD_LIMIT}₪

🔒 התשלום מאובטח ב-3D Secure
"""
        
        keyboard = [
            [
                InlineKeyboardButton("50₪", callback_data="cc_amount_50"),
                InlineKeyboardButton("100₪", callback_data="cc_amount_100"),
            ],
            [
                InlineKeyboardButton("200₪", callback_data="cc_amount_200"),
                InlineKeyboardButton("500₪", callback_data="cc_amount_500"),
            ],
            [InlineKeyboardButton("💰 סכום אחר", callback_data="cc_custom_amount")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="add_balance")]
        ]
        
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
        
        return ConversationHandler.END

    @staticmethod
    async def select_cc_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת סכום לתשלום בכרטיס"""
        query = update.callback_query
        await query.answer()
        
        amount = int(query.data.replace("cc_amount_", ""))
        context.user_data["cc_amount"] = amount
        
        return await PaymentHandlers._show_card_options(update, context, amount)

    @staticmethod
    async def request_cc_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בקשת סכום מותאם לכרטיס אשראי"""
        query = update.callback_query
        await query.answer()
        
        text = f"""
💳 *סכום מותאם אישית*

שלח את הסכום שברצונך לטעון:

💡 מינימום: {Config.MIN_CARD_PAYMENT}₪
💡 מקסימום: {Config.MAX_TRANSACTION_AMOUNT}₪

לביטול: /cancel
"""
        await query.edit_message_text(text, parse_mode="Markdown")
        return CC_SELECT_AMOUNT

    @staticmethod
    async def process_cc_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד סכום מותאם לכרטיס"""
        try:
            amount = float(update.message.text.strip())
            
            if amount < Config.MIN_CARD_PAYMENT:
                await update.message.reply_text(
                    f"❌ סכום מינימלי: {Config.MIN_CARD_PAYMENT}₪\nשלח סכום גדול יותר או /cancel"
                )
                return CC_SELECT_AMOUNT
            
            if amount > Config.MAX_TRANSACTION_AMOUNT:
                await update.message.reply_text(
                    f"❌ סכום מקסימלי לעסקה: {Config.MAX_TRANSACTION_AMOUNT}₪\nשלח סכום קטן יותר או /cancel"
                )
                return CC_SELECT_AMOUNT
            
            context.user_data["cc_amount"] = amount
            return await PaymentHandlers._show_card_options_message(update, context, amount)
            
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין")
            return CC_SELECT_AMOUNT

    @staticmethod
    async def _show_card_options(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
        """הצגת אפשרויות כרטיס (מ-callback)"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        # קבלת כרטיסים שמורים
        saved_cards = await PaymentGatewayService.get_user_saved_cards(user_id)
        
        text = f"""
💳 *טעינת {amount:.0f}₪*

"""
        
        keyboard = []
        
        # הצגת כרטיסים שמורים
        if saved_cards and Config.ALLOW_SAVE_CARD:
            text += "🔐 *כרטיסים שמורים:*\n"
            for card in saved_cards:
                emoji = "⭐" if card.is_default else "💳"
                card_text = f"{emoji} {card.card_brand} ****{card.card_last4}"
                if card.card_expiry:
                    card_text += f" ({card.card_expiry})"
                keyboard.append([
                    InlineKeyboardButton(card_text, callback_data=f"cc_use_card_{card._id}")
                ])
            text += "\n"
        
        text += "🆕 *כרטיס חדש:*"
        
        keyboard.append([
            InlineKeyboardButton("💳 תשלום בכרטיס חדש", callback_data="cc_new_card")
        ])
        
        if Config.ALLOW_SAVE_CARD:
            keyboard.append([
                InlineKeyboardButton("💳➕ תשלום ושמירת כרטיס", callback_data="cc_new_card_save")
            ])
        
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="pay_credit_card")
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return ConversationHandler.END

    @staticmethod
    async def _show_card_options_message(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
        """הצגת אפשרויות כרטיס (מהודעה)"""
        user_id = update.effective_user.id
        saved_cards = await PaymentGatewayService.get_user_saved_cards(user_id)
        
        text = f"💳 *טעינת {amount:.0f}₪*\n\n"
        
        keyboard = []
        
        if saved_cards and Config.ALLOW_SAVE_CARD:
            text += "🔐 *כרטיסים שמורים:*\n"
            for card in saved_cards:
                emoji = "⭐" if card.is_default else "💳"
                card_text = f"{emoji} {card.card_brand} ****{card.card_last4}"
                keyboard.append([
                    InlineKeyboardButton(card_text, callback_data=f"cc_use_card_{card._id}")
                ])
            text += "\n"
        
        text += "🆕 *כרטיס חדש:*"
        
        keyboard.append([InlineKeyboardButton("💳 תשלום בכרטיס חדש", callback_data="cc_new_card")])
        
        if Config.ALLOW_SAVE_CARD:
            keyboard.append([InlineKeyboardButton("💳➕ תשלום ושמירת כרטיס", callback_data="cc_new_card_save")])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="pay_credit_card")])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return ConversationHandler.END

    @staticmethod
    async def process_new_card_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד תשלום בכרטיס חדש"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        amount = context.user_data.get("cc_amount")
        
        if not amount:
            await query.edit_message_text("❌ פג תוקף הבקשה. התחל מחדש.")
            return ConversationHandler.END
        
        save_card = query.data == "cc_new_card_save"
        
        # יצירת תשלום
        transaction, error = await PaymentGatewayService.create_payment(
            user_id=user_id,
            amount=amount,
            transaction_type=PaymentTransactionType.DEPOSIT,
            description=f"טעינת יתרה {amount}₪",
            save_card=save_card
        )
        
        if error:
            await query.edit_message_text(f"❌ {error}")
            return ConversationHandler.END
        
        if not transaction or not transaction.payment_url:
            await query.edit_message_text("❌ שגיאה ביצירת קישור תשלום")
            return ConversationHandler.END
        
        text = f"""
💳 *תשלום מאובטח*

סכום: *{amount:.0f}₪*
מזהה: `{transaction._id}`

⏰ יש לך {Config.PAYMENT_TIMEOUT_MINUTES} דקות להשלים את התשלום.

🔒 התשלום מאובטח ב-3D Secure

לחץ על הכפתור למעבר לדף התשלום:
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 מעבר לתשלום", url=transaction.payment_url)],
            [InlineKeyboardButton("🔄 בדוק סטטוס תשלום", callback_data=f"cc_check_status_{transaction._id}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="my_balance")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # ניקוי
        context.user_data.pop("cc_amount", None)
        
        return ConversationHandler.END

    @staticmethod
    async def use_saved_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שימוש בכרטיס שמור"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        card_id = query.data.replace("cc_use_card_", "")
        amount = context.user_data.get("cc_amount")
        
        if not amount:
            await query.edit_message_text("❌ פג תוקף הבקשה. התחל מחדש.")
            return ConversationHandler.END
        
        await query.edit_message_text("⏳ מעבד תשלום...")
        
        # יצירת תשלום עם כרטיס שמור
        transaction, error = await PaymentGatewayService.create_payment(
            user_id=user_id,
            amount=amount,
            transaction_type=PaymentTransactionType.DEPOSIT,
            use_saved_card_id=card_id
        )
        
        if error:
            await query.edit_message_text(f"❌ {error}")
            return ConversationHandler.END
        
        if transaction and transaction.status.value == "completed":
            text = f"""
✅ *התשלום הצליח!*

סכום: *{amount:.0f}₪*
היתרה שלך עודכנה.

לצפייה ביתרה: /balance
"""
            keyboard = [[InlineKeyboardButton("💰 צפה ביתרה", callback_data="my_balance")]]
        else:
            text = f"""
❌ *התשלום נכשל*

אנא נסה שוב או השתמש בכרטיס אחר.
"""
            keyboard = [[InlineKeyboardButton("🔄 נסה שוב", callback_data="pay_credit_card")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        context.user_data.pop("cc_amount", None)
        return ConversationHandler.END

    @staticmethod
    async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בדיקת סטטוס תשלום"""
        query = update.callback_query
        await query.answer("בודק סטטוס...")
        
        transaction_id = query.data.replace("cc_check_status_", "")
        
        transaction = await PaymentGatewayService.get_transaction(transaction_id)
        
        if not transaction:
            await query.edit_message_text("❌ עסקה לא נמצאה")
            return
        
        status_map = {
            "pending": ("⏳", "ממתין לתשלום"),
            "processing": ("🔄", "בעיבוד"),
            "completed": ("✅", "הושלם בהצלחה"),
            "failed": ("❌", "נכשל"),
            "cancelled": ("🚫", "בוטל"),
            "expired": ("⌛", "פג תוקף")
        }
        
        emoji, status_text = status_map.get(transaction.status.value, ("❓", transaction.status.value))
        
        text = f"""
📊 *סטטוס תשלום*

מזהה: `{transaction_id[:12]}...`
סכום: *{transaction.amount:.0f}₪*
סטטוס: {emoji} {status_text}
"""
        
        if transaction.status.value == "completed":
            text += "\n✅ היתרה שלך עודכנה!"
            keyboard = [[InlineKeyboardButton("💰 צפה ביתרה", callback_data="my_balance")]]
        elif transaction.status.value == "pending":
            text += f"\n⏰ נותרו {Config.PAYMENT_TIMEOUT_MINUTES} דקות להשלמת התשלום"
            keyboard = [
                [InlineKeyboardButton("💳 מעבר לתשלום", url=transaction.payment_url)] if transaction.payment_url else [],
                [InlineKeyboardButton("🔄 רענן סטטוס", callback_data=f"cc_check_status_{transaction_id}")],
                [InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]
            ]
            keyboard = [k for k in keyboard if k]  # Remove empty lists
        else:
            keyboard = [
                [InlineKeyboardButton("🔄 נסה שוב", callback_data="pay_credit_card")],
                [InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]
            ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def manage_saved_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניהול כרטיסים שמורים"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        saved_cards = await PaymentGatewayService.get_user_saved_cards(user_id)
        
        if not saved_cards:
            text = "💳 *כרטיסים שמורים*\n\nאין לך כרטיסים שמורים.\n\n"
            text += "💡 תוכל לשמור כרטיס בעת תשלום הבא."
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="menu_settings")]]
        else:
            text = f"💳 *כרטיסים שמורים* ({len(saved_cards)}/{Config.MAX_SAVED_CARDS_PER_USER})\n\n"
            
            keyboard = []
            for card in saved_cards:
                emoji = "⭐" if card.is_default else "💳"
                card_text = f"{emoji} {card.card_brand} ****{card.card_last4}"
                keyboard.append([
                    InlineKeyboardButton(card_text, callback_data=f"cc_card_details_{card._id}")
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="menu_settings")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def show_card_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת פרטי כרטיס שמור"""
        query = update.callback_query
        await query.answer()
        
        card_id = query.data.replace("cc_card_details_", "")
        user_id = update.effective_user.id
        
        saved_cards = await PaymentGatewayService.get_user_saved_cards(user_id)
        card = next((c for c in saved_cards if str(c._id) == card_id), None)
        
        if not card:
            await query.edit_message_text("❌ כרטיס לא נמצא")
            return
        
        text = f"""
💳 *פרטי כרטיס*

🏷️ סוג: {card.card_brand}
🔢 מספר: **** **** **** {card.card_last4}
📅 תוקף: {card.card_expiry or 'לא זמין'}
⭐ ברירת מחדל: {'כן' if card.is_default else 'לא'}
📆 נוסף: {card.created_at.strftime('%d/%m/%Y')}
"""
        
        keyboard = []
        
        if not card.is_default:
            keyboard.append([
                InlineKeyboardButton("⭐ הגדר כברירת מחדל", callback_data=f"cc_set_default_{card_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("🗑️ מחק כרטיס", callback_data=f"cc_delete_card_{card_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="cc_manage_cards")
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def set_default_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הגדרת כרטיס כברירת מחדל"""
        query = update.callback_query
        await query.answer()
        
        card_id = query.data.replace("cc_set_default_", "")
        user_id = update.effective_user.id
        
        success = await PaymentGatewayService.set_default_card(user_id, card_id)
        
        if success:
            await query.edit_message_text(
                "✅ הכרטיס הוגדר כברירת מחדל",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 חזרה לכרטיסים", callback_data="cc_manage_cards")]
                ])
            )
        else:
            await query.edit_message_text("❌ שגיאה בעדכון")

    @staticmethod
    async def delete_saved_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מחיקת כרטיס שמור"""
        query = update.callback_query
        await query.answer()
        
        card_id = query.data.replace("cc_delete_card_", "")
        
        text = "⚠️ *האם למחוק את הכרטיס?*\n\nלא ניתן לבטל פעולה זו."
        
        keyboard = [
            [
                InlineKeyboardButton("✅ כן, מחק", callback_data=f"cc_confirm_delete_{card_id}"),
                InlineKeyboardButton("❌ ביטול", callback_data=f"cc_card_details_{card_id}")
            ]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def confirm_delete_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור מחיקת כרטיס"""
        query = update.callback_query
        await query.answer()
        
        card_id = query.data.replace("cc_confirm_delete_", "")
        user_id = update.effective_user.id
        
        success = await PaymentGatewayService.delete_saved_card(user_id, card_id)
        
        if success:
            await query.edit_message_text(
                "✅ הכרטיס נמחק בהצלחה",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 חזרה לכרטיסים", callback_data="cc_manage_cards")]
                ])
            )
        else:
            await query.edit_message_text("❌ שגיאה במחיקת הכרטיס")

    @staticmethod
    async def cc_payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """היסטוריית תשלומים בכרטיס"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        transactions = await PaymentGatewayService.get_user_transactions(user_id, limit=15)
        
        text = "💳 *היסטוריית תשלומים בכרטיס*\n\n"
        
        if not transactions:
            text += "אין תשלומים עדיין"
        else:
            for txn in transactions:
                status_emoji = {
                    "completed": "✅",
                    "pending": "⏳",
                    "failed": "❌",
                    "expired": "⌛"
                }.get(txn.status.value, "❓")
                
                text += f"{status_emoji} {txn.amount:.0f}₪ | {txn.created_at.strftime('%d/%m %H:%M')}\n"
                if txn.card_last4:
                    text += f"   כרטיס: ****{txn.card_last4}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def cancel_cc_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול תשלום בכרטיס"""
        context.user_data.pop("cc_amount", None)
        await update.message.reply_text("❌ התשלום בוטל")
        return ConversationHandler.END

    # ==================== Automated Payout Handlers ====================

    @staticmethod
    async def start_automated_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת משיכה אוטומטית"""
        query = update.callback_query
        if query:
            await query.answer()
        
        user_id = update.effective_user.id
        
        # חישוב זמין למשיכה
        available = await PayoutService.calculate_available_for_payout(user_id)
        
        if available < Config.MIN_AUTO_PAYOUT_AMOUNT:
            text = f"❌ *יתרה לא מספיקה*\n\n"
            text += f"זמין למשיכה: {available:.2f}₪\n"
            text += f"מינימום: {Config.MIN_AUTO_PAYOUT_AMOUNT}₪"
            
            if query:
                await query.edit_message_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, parse_mode="Markdown")
            return ConversationHandler.END
        
        text = f"""
💸 *משיכת כספים*

💰 זמין למשיכה: *{available:.2f}₪*
📌 עמלת משיכה: {Config.PAYOUT_COMMISSION * 100:.0f}%
📅 זמן עיבוד: {Config.PAYOUT_PROCESSING_DAYS} ימי עסקים

בחר שיטת משיכה:
"""
        
        keyboard = [
            [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="payout_method_bank_transfer")],
            [InlineKeyboardButton("📱 ביט", callback_data="payout_method_bit")],
        ]
        
        # הוספת PayPal/Payoneer אם מוגדרים
        if Config.PAYPAL_CLIENT_ID:
            keyboard.append([InlineKeyboardButton("🅿️ PayPal", callback_data="payout_method_paypal")])
        
        if Config.PAYONEER_API_KEY:
            keyboard.append([InlineKeyboardButton("💳 Payoneer", callback_data="payout_method_payoneer")])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")])
        
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
        
        return ConversationHandler.END

    @staticmethod
    async def select_payout_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת שיטת משיכה"""
        query = update.callback_query
        await query.answer()
        
        method_str = query.data.replace("payout_method_", "")
        method = PayoutMethod(method_str)
        context.user_data["payout_method"] = method
        
        user_id = update.effective_user.id
        
        # קבלת פרטים שמורים
        saved_details = await PayoutService.get_saved_payout_details(user_id, method)
        
        available = await PayoutService.calculate_available_for_payout(user_id)
        context.user_data["payout_available"] = available
        
        # הצגת טופס לפי שיטה
        if method == PayoutMethod.BANK_TRANSFER:
            text = f"🏦 *משיכה לחשבון בנק*\n\n"
            text += f"זמין: {available:.2f}₪\n\n"
            
            if saved_details:
                text += "📋 פרטים שמורים:\n"
                text += f"בנק: {saved_details.get('bank_name', '')}\n"
                text += f"סניף: {saved_details.get('branch', '')}\n"
                text += f"חשבון: {saved_details.get('account', '')}\n"
                text += f"שם: {saved_details.get('owner_name', '')}\n\n"
                
                keyboard = [
                    [InlineKeyboardButton("✅ השתמש בפרטים שמורים", callback_data="payout_use_saved")],
                    [InlineKeyboardButton("📝 עדכן פרטים", callback_data="payout_new_details")],
                    [InlineKeyboardButton("🔙 חזרה", callback_data="request_payout")]
                ]
            else:
                text += "שלח את פרטי חשבון הבנק בפורמט:\n"
                text += "`בנק, סניף, מספר חשבון, שם בעל החשבון`\n\n"
                text += "לדוגמה: `לאומי, 123, 456789, ישראל ישראלי`"
                
                keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="request_payout")]]
                
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return PAYOUT_ENTER_DETAILS
        
        elif method == PayoutMethod.BIT:
            text = f"📱 *משיכה לביט*\n\n"
            text += f"זמין: {available:.2f}₪\n\n"
            text += "שלח את מספר הטלפון המקושר לביט:"
            
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="request_payout")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return PAYOUT_ENTER_DETAILS
        
        elif method == PayoutMethod.PAYPAL:
            text = f"🅿️ *משיכה ל-PayPal*\n\n"
            text += f"זמין: {available:.2f}₪\n\n"
            text += "שלח את כתובת המייל של חשבון ה-PayPal שלך:"
            
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="request_payout")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return PAYOUT_ENTER_DETAILS
        
        elif method == PayoutMethod.PAYONEER:
            text = f"💳 *משיכה ל-Payoneer*\n\n"
            text += f"זמין: {available:.2f}₪\n\n"
            text += "שלח את מזהה ה-Payoneer או המייל שלך:"
            
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="request_payout")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return PAYOUT_ENTER_DETAILS
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    @staticmethod
    async def process_payout_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד פרטי משיכה"""
        user_id = update.effective_user.id
        method = context.user_data.get("payout_method")
        available = context.user_data.get("payout_available", 0)
        details_text = update.message.text.strip()
        
        if not method:
            await update.message.reply_text("❌ פג תוקף הבקשה. התחל מחדש.")
            return ConversationHandler.END
        
        # פרסור פרטים לפי שיטה
        payout_details = {}
        
        if method == PayoutMethod.BANK_TRANSFER:
            parts = [p.strip() for p in details_text.split(",")]
            if len(parts) < 4:
                await update.message.reply_text(
                    "❌ פורמט שגוי. שלח: בנק, סניף, חשבון, שם\n"
                    "לדוגמה: לאומי, 123, 456789, ישראל ישראלי"
                )
                return PAYOUT_ENTER_DETAILS
            
            payout_details = {
                "bank_name": parts[0],
                "branch": parts[1],
                "account": parts[2],
                "owner_name": parts[3]
            }
        
        elif method == PayoutMethod.BIT:
            # בדיקת מספר טלפון
            phone = details_text.replace("-", "").replace(" ", "")
            if not phone.startswith("05") or len(phone) != 10:
                await update.message.reply_text("❌ מספר טלפון לא תקין. שלח מספר בפורמט 05XXXXXXXX")
                return PAYOUT_ENTER_DETAILS
            
            payout_details = {"phone": phone}
        
        elif method == PayoutMethod.PAYPAL:
            if "@" not in details_text:
                await update.message.reply_text("❌ כתובת מייל לא תקינה")
                return PAYOUT_ENTER_DETAILS
            
            payout_details = {"paypal_email": details_text}
        
        elif method == PayoutMethod.PAYONEER:
            payout_details = {"payoneer_id": details_text}
        
        # שמירת פרטים
        await PayoutService.save_payout_details(user_id, method, payout_details)
        context.user_data["payout_details"] = payout_details
        
        # בקשת סכום משיכה
        fee = available * Config.PAYOUT_COMMISSION
        net = available - fee
        
        text = f"""
✅ *פרטים נשמרו*

💰 זמין למשיכה: {available:.2f}₪
💸 עמלה ({Config.PAYOUT_COMMISSION * 100:.0f}%): {fee:.2f}₪
✅ תקבל: {net:.2f}₪

שלח את הסכום שברצונך למשוך (עד {available:.0f}₪):
"""
        
        await update.message.reply_text(text, parse_mode="Markdown")
        return ENTER_PAYOUT_AMOUNT

    @staticmethod
    async def use_saved_payout_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שימוש בפרטי משיכה שמורים"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        method = context.user_data.get("payout_method")
        available = context.user_data.get("payout_available", 0)
        
        saved_details = await PayoutService.get_saved_payout_details(user_id, method)
        
        if not saved_details:
            await query.edit_message_text("❌ לא נמצאו פרטים שמורים")
            return ConversationHandler.END
        
        context.user_data["payout_details"] = saved_details
        
        fee = available * Config.PAYOUT_COMMISSION
        net = available - fee
        
        text = f"""
💰 *משיכה - בחר סכום*

זמין: {available:.2f}₪
עמלה: {fee:.2f}₪
תקבל: {net:.2f}₪

שלח את הסכום שברצונך למשוך:
"""
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return ENTER_PAYOUT_AMOUNT

    @staticmethod
    async def process_automated_payout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד סכום משיכה אוטומטית"""
        user_id = update.effective_user.id
        method = context.user_data.get("payout_method")
        payout_details = context.user_data.get("payout_details")
        available = context.user_data.get("payout_available", 0)
        
        try:
            amount = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין")
            return ENTER_PAYOUT_AMOUNT
        
        if amount < Config.MIN_AUTO_PAYOUT_AMOUNT:
            await update.message.reply_text(f"❌ סכום מינימלי: {Config.MIN_AUTO_PAYOUT_AMOUNT}₪")
            return ENTER_PAYOUT_AMOUNT
        
        if amount > available:
            await update.message.reply_text(f"❌ הסכום חורג מהזמין ({available:.2f}₪)")
            return ENTER_PAYOUT_AMOUNT
        
        # יצירת בקשת משיכה
        payout_id, error = await PayoutService.request_automated_payout(
            seller_id=user_id,
            amount=amount,
            method=method,
            payout_details=payout_details
        )
        
        if error:
            await update.message.reply_text(f"❌ {error}")
            return ConversationHandler.END
        
        fee = amount * Config.PAYOUT_COMMISSION
        net = amount - fee
        
        text = f"""
✅ *בקשת משיכה נשלחה!*

💰 סכום: {amount:.2f}₪
💸 עמלה: {fee:.2f}₪
✅ תקבל: {net:.2f}₪

📋 שיטה: {PayoutService._get_method_name(method)}
⏰ זמן עיבוד: {Config.PAYOUT_PROCESSING_DAYS} ימי עסקים

תקבל התראה בעת אישור המשיכה.
"""
        
        await update.message.reply_text(text, parse_mode="Markdown")
        
        # ניקוי
        context.user_data.pop("payout_method", None)
        context.user_data.pop("payout_details", None)
        context.user_data.pop("payout_available", None)
        
        return ConversationHandler.END

    @staticmethod
    async def cancel_automated_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול משיכה אוטומטית"""
        context.user_data.pop("payout_method", None)
        context.user_data.pop("payout_details", None)
        context.user_data.pop("payout_available", None)
        await update.message.reply_text("❌ בקשת המשיכה בוטלה")
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

    # Conversation לתשלום בכרטיס אשראי - סכום מותאם
    cc_custom_amount_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(PaymentHandlers.request_cc_custom_amount, pattern="^cc_custom_amount$")
        ],
        states={
            CC_SELECT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_cc_custom_amount)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", PaymentHandlers.cancel_cc_payment)
        ],
    )

    # Conversation למשיכה אוטומטית
    automated_payout_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(PaymentHandlers.select_payout_method, pattern="^payout_method_")
        ],
        states={
            PAYOUT_ENTER_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_payout_details)
            ],
            ENTER_PAYOUT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, PaymentHandlers.process_automated_payout_amount)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", PaymentHandlers.cancel_automated_payout)
        ],
    )

    return [
        CommandHandler("balance", PaymentHandlers.my_balance),
        CommandHandler("my_payouts", PaymentHandlers.my_payouts),
        CommandHandler("my_deposits", PaymentHandlers.my_deposits),
        CallbackQueryHandler(PaymentHandlers.my_balance, pattern="^my_balance$"),
        CallbackQueryHandler(PaymentHandlers.transaction_history, pattern="^transaction_history$"),
        
        # תהליך הפקדה ידנית
        CallbackQueryHandler(PaymentHandlers.start_add_balance, pattern="^add_balance$"),
        CallbackQueryHandler(PaymentHandlers.select_deposit_amount, pattern="^deposit_amount_"),
        custom_deposit_conv,
        proof_upload_conv,
        
        # אדמין - אישור/דחיית הפקדות
        CallbackQueryHandler(PaymentHandlers.approve_deposit, pattern="^approve_deposit_"),
        CallbackQueryHandler(PaymentHandlers.reject_deposit, pattern="^reject_deposit_"),
        
        # משיכה ידנית
        payout_conv,
        
        # === תשלום בכרטיס אשראי ===
        CallbackQueryHandler(PaymentHandlers.start_credit_card_payment, pattern="^pay_credit_card$"),
        CallbackQueryHandler(PaymentHandlers.select_cc_amount, pattern="^cc_amount_"),
        cc_custom_amount_conv,
        CallbackQueryHandler(PaymentHandlers.process_new_card_payment, pattern="^cc_new_card$"),
        CallbackQueryHandler(PaymentHandlers.process_new_card_payment, pattern="^cc_new_card_save$"),
        CallbackQueryHandler(PaymentHandlers.use_saved_card, pattern="^cc_use_card_"),
        CallbackQueryHandler(PaymentHandlers.check_payment_status, pattern="^cc_check_status_"),
        
        # ניהול כרטיסים שמורים
        CallbackQueryHandler(PaymentHandlers.manage_saved_cards, pattern="^cc_manage_cards$"),
        CallbackQueryHandler(PaymentHandlers.show_card_details, pattern="^cc_card_details_"),
        CallbackQueryHandler(PaymentHandlers.set_default_card, pattern="^cc_set_default_"),
        CallbackQueryHandler(PaymentHandlers.delete_saved_card, pattern="^cc_delete_card_"),
        CallbackQueryHandler(PaymentHandlers.confirm_delete_card, pattern="^cc_confirm_delete_"),
        CallbackQueryHandler(PaymentHandlers.cc_payment_history, pattern="^cc_history$"),
        
        # === משיכות אוטומטיות ===
        CallbackQueryHandler(PaymentHandlers.start_automated_payout, pattern="^automated_payout$"),
        automated_payout_conv,
        CallbackQueryHandler(PaymentHandlers.use_saved_payout_details, pattern="^payout_use_saved$"),
        CallbackQueryHandler(PaymentHandlers.select_payout_method, pattern="^payout_new_details$"),
    ]
