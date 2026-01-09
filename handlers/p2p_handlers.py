"""
Handlers לתהליך רכישה P2P - מודל לוח מודעות (Classifieds)

תהליך חדש:
1. קונה בוחר קופון
2. מוצגים לו פרטי התשלום של המוכר (ביט/פייבוקס)
3. קונה משלם ישירות למוכר
4. קונה מעלה צילום מסך כהוכחה
5. המוכר מקבל התראה ומאשר קבלת התשלום
6. הקופון משוחרר לקונה
7. עמלה מנוכית מקרדיט המוכר
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime, timedelta
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.service_credit_service import ServiceCreditService
from services.notification_service import NotificationService
from models import P2POrder, P2POrderStatus, CouponStatus
from config import Config
import database
import logging

logger = logging.getLogger(__name__)

# Conversation states
P2P_WAITING_PAYMENT_PROOF = 100
P2P_SELLER_CONFIRM = 101


class P2PHandlers:
    """Handlers לרכישות P2P"""
    
    @staticmethod
    async def start_p2p_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך רכישה P2P - הצגת פרטי תשלום של המוכר"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = ObjectId(query.data.replace("p2p_buy_", ""))
        buyer_id = update.effective_user.id
        
        # קבלת פרטי הקופון
        coupon = await CouponService.get_coupon(coupon_id)
        
        if not coupon or coupon.status != CouponStatus.ACTIVE:
            await query.edit_message_text(
                "❌ הקופון לא זמין יותר.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="main_menu")
                ]])
            )
            return ConversationHandler.END
        
        # וידוא שהקונה לא קונה מעצמו
        if buyer_id == coupon.seller_id:
            await query.edit_message_text("❌ לא ניתן לקנות קופון מעצמך")
            return ConversationHandler.END
        
        # קבלת פרטי המוכר ואמצעי התשלום שלו
        seller = await UserService.get_user(coupon.seller_id)
        if not seller:
            await query.edit_message_text("❌ המוכר לא נמצא")
            return ConversationHandler.END
        
        payment_methods = await ServiceCreditService.get_seller_payment_methods(coupon.seller_id)
        
        if not payment_methods:
            await query.edit_message_text(
                "❌ המוכר לא הגדיר אמצעי תשלום.\n"
                "לא ניתן לרכוש קופון זה כרגע."
            )
            return ConversationHandler.END
        
        seller_name = seller.display_name
        
        # בניית הודעת התשלום
        text = f"""
🛒 *רכישת קופון*

🎫 *{coupon.title}*
💰 מחיר: *{coupon.sale_price:.2f}₪*

━━━━━━━━━━━━━━━━━━━━

💳 *פרטי תשלום של המוכר ({seller_name}):*

"""
        
        keyboard = []
        
        if payment_methods.get("bit"):
            text += f"📱 *ביט:* `{payment_methods['bit']}`\n"
            keyboard.append([InlineKeyboardButton(
                "📱 אני משלם בביט",
                callback_data=f"p2p_method_bit_{coupon_id}"
            )])
        
        if payment_methods.get("paybox"):
            text += f"🔗 *פייבוקס:* {payment_methods['paybox']}\n"
            keyboard.append([InlineKeyboardButton(
                "🔗 אני משלם בפייבוקס",
                callback_data=f"p2p_method_paybox_{coupon_id}"
            )])
        
        text += """
━━━━━━━━━━━━━━━━━━━━

📋 *הוראות:*
1. בחר אמצעי תשלום למטה
2. בצע העברה בסכום המדויק
3. צלם את מסך האישור
4. העלה את הצילום לבוט
5. המוכר יאשר ותקבל את הקופון!

⚠️ *חשוב:* אל תכתוב הערות בהעברה
"""
        
        keyboard.append([InlineKeyboardButton("❌ ביטול", callback_data=f"coupon_{coupon_id}")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return ConversationHandler.END
    
    @staticmethod
    async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת אמצעי תשלום והמשך לצילום מסך"""
        query = update.callback_query
        await query.answer()
        
        # פרסור callback data
        data = query.data  # p2p_method_bit_<coupon_id> or p2p_method_paybox_<coupon_id>
        parts = data.split("_")
        method = parts[2]  # bit or paybox
        coupon_id = ObjectId(parts[3])
        
        buyer_id = update.effective_user.id
        
        # קבלת פרטי הקופון
        coupon = await CouponService.get_coupon(coupon_id)
        if not coupon or coupon.status != CouponStatus.ACTIVE:
            await query.edit_message_text("❌ הקופון לא זמין יותר")
            return ConversationHandler.END
        
        # יצירת הזמנה P2P בסטטוס ממתין לתשלום
        p2p_orders = await database.get_p2p_orders_collection()
        
        order = P2POrder(
            buyer_id=buyer_id,
            seller_id=coupon.seller_id,
            coupon_id=coupon_id,
            price=coupon.sale_price,
            status=P2POrderStatus.PENDING_BUYER_PAYMENT,
            payment_method_used=method
        )
        
        result = await p2p_orders.insert_one(order.to_dict())
        order_id = result.inserted_id
        
        # שמירה בקונטקסט
        context.user_data["p2p_order_id"] = str(order_id)
        context.user_data["p2p_coupon_id"] = str(coupon_id)
        context.user_data["p2p_method"] = method
        
        method_name = "ביט" if method == "bit" else "פייבוקס"
        
        text = f"""
📸 *העלאת אישור תשלום*

🎫 קופון: {coupon.title}
💰 סכום לתשלום: *{coupon.sale_price:.2f}₪*
💳 אמצעי תשלום: {method_name}

━━━━━━━━━━━━━━━━━━━━

✅ לאחר ששילמת, שלח צילום מסך של אישור התשלום.

📋 וודא שהצילום מכיל:
• סכום ההעברה
• תאריך ושעה
• שם הנמען (אם מוצג)

⏰ לאחר העלאת הצילום, למוכר יש *{Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות* לאשר.

לביטול: /cancel
"""
        
        await query.edit_message_text(text, parse_mode="Markdown")
        
        return P2P_WAITING_PAYMENT_PROOF
    
    @staticmethod
    async def receive_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת צילום מסך של אישור תשלום"""
        buyer_id = update.effective_user.id
        order_id_str = context.user_data.get("p2p_order_id")
        
        if not order_id_str:
            await update.message.reply_text("❌ פג תוקף הבקשה. התחל מחדש.")
            return ConversationHandler.END
        
        # בדיקת תמונה
        photo = None
        if update.message.photo:
            photo = update.message.photo[-1].file_id
        elif update.message.document and update.message.document.mime_type.startswith("image"):
            photo = update.message.document.file_id
        
        if not photo:
            await update.message.reply_text(
                "❌ אנא שלח תמונה (צילום מסך) של אישור התשלום.\n"
                "לביטול: /cancel"
            )
            return P2P_WAITING_PAYMENT_PROOF
        
        order_id = ObjectId(order_id_str)
        
        # עדכון ההזמנה עם צילום ההוכחה
        p2p_orders = await database.get_p2p_orders_collection()
        
        confirmation_deadline = datetime.utcnow() + timedelta(
            hours=Config.SELLER_CONFIRMATION_TIMEOUT_HOURS
        )
        
        result = await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.PENDING_SELLER_CONFIRMATION.value,
                    "payment_proof_image": photo,
                    "seller_confirmation_deadline": confirmation_deadline
                }
            }
        )
        
        if result.modified_count == 0:
            await update.message.reply_text("❌ שגיאה בעדכון ההזמנה")
            return ConversationHandler.END
        
        # קבלת פרטי ההזמנה
        order_data = await p2p_orders.find_one({"_id": order_id})
        coupon_id = order_data["coupon_id"]
        seller_id = order_data["seller_id"]
        
        coupon = await CouponService.get_coupon(coupon_id)
        buyer = await UserService.get_user(buyer_id)
        
        buyer_name = buyer.display_name if buyer else "קונה"
        
        # שליחת התראה למוכר
        seller_text = f"""
💰 *התקבלה הוכחת תשלום חדשה!*

🎫 קופון: {coupon.title if coupon else 'קופון'}
💵 סכום: {order_data['price']:.2f}₪
👤 מאת: {buyer_name}

⏰ *יש לך {Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות לאשר קבלת התשלום!*

אם לא תאשר בזמן, העסקה תיכנס למחלוקת אוטומטית.
"""
        
        seller_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ קיבלתי תשלום - אשר", callback_data=f"p2p_confirm_{order_id}")],
            [InlineKeyboardButton("❌ לא קיבלתי - מחלוקת", callback_data=f"p2p_dispute_{order_id}")],
        ])
        
        try:
            # שליחת התמונה למוכר
            await context.bot.send_photo(
                chat_id=seller_id,
                photo=photo,
                caption=seller_text,
                reply_markup=seller_keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify seller {seller_id}: {e}")
        
        # אישור לקונה
        await update.message.reply_text(
            f"""
✅ *צילום התשלום התקבל!*

📤 נשלחה התראה למוכר.

⏰ המוכר צריך לאשר תוך *{Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות*.
אם לא יאשר, תיפתח מחלוקת אוטומטית.

📊 תקבל הודעה כשהמוכר יאשר ותקבל את הקופון!
""",
            parse_mode="Markdown"
        )
        
        # ניקוי קונטקסט
        context.user_data.pop("p2p_order_id", None)
        context.user_data.pop("p2p_coupon_id", None)
        context.user_data.pop("p2p_method", None)
        
        return ConversationHandler.END
    
    @staticmethod
    async def seller_confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור קבלת תשלום על ידי המוכר"""
        query = update.callback_query
        await query.answer()
        
        order_id = ObjectId(query.data.replace("p2p_confirm_", ""))
        seller_id = update.effective_user.id
        
        p2p_orders = await database.get_p2p_orders_collection()
        order_data = await p2p_orders.find_one({"_id": order_id})
        
        if not order_data:
            await query.edit_message_caption("❌ הזמנה לא נמצאה")
            return
        
        # וידוא שזה המוכר
        if order_data["seller_id"] != seller_id:
            await query.answer("❌ אין לך הרשאה לאשר הזמנה זו", show_alert=True)
            return
        
        # וידוא סטטוס
        if order_data["status"] != P2POrderStatus.PENDING_SELLER_CONFIRMATION.value:
            await query.edit_message_caption("❌ ההזמנה כבר טופלה")
            return
        
        # קבלת פרטי הקופון
        coupon_id = order_data["coupon_id"]
        coupon = await CouponService.get_coupon(coupon_id)
        
        if not coupon:
            await query.edit_message_caption("❌ הקופון לא נמצא")
            return
        
        # ניכוי עמלה מקרדיט המוכר
        success, commission, message = await ServiceCreditService.deduct_commission(
            seller_id=seller_id,
            sale_price=order_data["price"],
            order_id=order_id
        )
        
        # עדכון סטטוס ההזמנה
        await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.COMPLETED.value,
                    "seller_confirmed_at": datetime.utcnow(),
                    "completed_at": datetime.utcnow(),
                    "commission_amount": commission
                }
            }
        )
        
        # סימון הקופון כנמכר
        coupons = await database.get_coupons_collection()
        await coupons.update_one(
            {"_id": coupon_id},
            {"$set": {"status": CouponStatus.SOLD.value}}
        )
        
        # שליחת הקופון לקונה
        buyer_id = order_data["buyer_id"]
        
        buyer_text = f"""
🎉 *הקופון שלך מוכן!*

🎫 *{coupon.title}*

🔐 *קוד הקופון:*
`{coupon.digital_code or 'לא צוין קוד דיגיטלי'}`

📝 תיאור:
{coupon.description or 'אין תיאור'}

━━━━━━━━━━━━━━━━━━━━

✅ העסקה הושלמה בהצלחה!
💡 נשמח אם תדרג את המוכר.
"""
        
        buyer_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ דרג את המוכר", callback_data=f"rate_p2p_{order_id}")],
            [InlineKeyboardButton("🔙 תפריט ראשי", callback_data="main_menu")],
        ])
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=buyer_text,
                reply_markup=buyer_keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send coupon to buyer {buyer_id}: {e}")
        
        # אישור למוכר
        credit_stats = await ServiceCreditService.get_credit_stats(seller_id)
        
        await query.edit_message_caption(
            f"""
✅ *העסקה אושרה!*

💰 קיבלת: {order_data['price']:.2f}₪
💸 עמלה שנוכתה: {commission:.2f} נקודות

📊 יתרת קרדיט נוכחית: {credit_stats['balance']:.2f} נקודות
🛒 מכירות מוצלחות: {credit_stats['sales_count']}

{message if 'שים לב' in message else ''}
""",
            parse_mode="Markdown"
        )
    
    @staticmethod
    async def seller_dispute_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פתיחת מחלוקת על ידי המוכר (לא קיבל תשלום)"""
        query = update.callback_query
        await query.answer()
        
        order_id = ObjectId(query.data.replace("p2p_dispute_", ""))
        seller_id = update.effective_user.id
        
        p2p_orders = await database.get_p2p_orders_collection()
        order_data = await p2p_orders.find_one({"_id": order_id})
        
        if not order_data or order_data["seller_id"] != seller_id:
            await query.edit_message_caption("❌ הזמנה לא נמצאה או אין הרשאה")
            return
        
        # עדכון סטטוס למחלוקת
        await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.MANUAL_DISPUTE.value,
                    "dispute_opened_at": datetime.utcnow(),
                    "dispute_reason": "המוכר טוען שלא קיבל תשלום"
                }
            }
        )
        
        # התראה לאדמינים
        admin_text = f"""
⚠️ *מחלוקת חדשה - המוכר לא קיבל תשלום*

🆔 הזמנה: `{order_id}`
👤 קונה: {order_data['buyer_id']}
🏪 מוכר: {order_data['seller_id']}
💰 סכום: {order_data['price']:.2f}₪

📋 סיבה: המוכר טוען שלא קיבל תשלום

🖼️ צילום ההוכחה מצורף למעלה.
"""
        
        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ תשלום תקין - שחרר קופון", callback_data=f"p2p_admin_release_{order_id}")],
            [InlineKeyboardButton("❌ תשלום מזויף - חסום קונה", callback_data=f"p2p_admin_reject_{order_id}")],
        ])
        
        for admin_id in Config.ADMIN_IDS:
            try:
                # שליחת צילום ההוכחה לאדמין
                if order_data.get("payment_proof_image"):
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=order_data["payment_proof_image"],
                        caption=admin_text,
                        reply_markup=admin_keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_keyboard,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        # הודעה לקונה
        buyer_id = order_data["buyer_id"]
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"""
⚠️ *נפתחה מחלוקת בהזמנה שלך*

המוכר טוען שלא קיבל את התשלום.

🔍 אדמין יבדוק את צילום ההוכחה שלך.
תקבל הודעה על ההחלטה.
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify buyer {buyer_id}: {e}")
        
        await query.edit_message_caption(
            "⚠️ *מחלוקת נפתחה*\n\n"
            "אדמין יבדוק את צילום ההוכחה של הקונה.\n"
            "תקבל הודעה על ההחלטה.",
            parse_mode="Markdown"
        )
    
    @staticmethod
    async def admin_release_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אדמין משחרר את הקופון (תשלום תקין)"""
        query = update.callback_query
        await query.answer()
        
        admin_id = update.effective_user.id
        if admin_id not in Config.ADMIN_IDS:
            await query.answer("❌ אין לך הרשאות", show_alert=True)
            return
        
        order_id = ObjectId(query.data.replace("p2p_admin_release_", ""))
        
        p2p_orders = await database.get_p2p_orders_collection()
        order_data = await p2p_orders.find_one({"_id": order_id})
        
        if not order_data:
            await query.edit_message_caption("❌ הזמנה לא נמצאה")
            return
        
        seller_id = order_data["seller_id"]
        buyer_id = order_data["buyer_id"]
        coupon_id = order_data["coupon_id"]
        
        # ניכוי עמלה + קנס מהמוכר
        penalty = Config.SELLER_TIMEOUT_PENALTY
        success, commission, _ = await ServiceCreditService.deduct_commission(
            seller_id=seller_id,
            sale_price=order_data["price"],
            order_id=order_id
        )
        
        # קנס נוסף למוכר
        await ServiceCreditService.apply_timeout_penalty(seller_id)
        
        # עדכון ההזמנה
        await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.COMPLETED.value,
                    "completed_at": datetime.utcnow(),
                    "admin_notes": f"אושר ידנית על ידי אדמין {admin_id}",
                    "commission_amount": commission
                }
            }
        )
        
        # סימון הקופון כנמכר
        coupons = await database.get_coupons_collection()
        await coupons.update_one(
            {"_id": coupon_id},
            {"$set": {"status": CouponStatus.SOLD.value}}
        )
        
        # קבלת הקופון
        coupon = await CouponService.get_coupon(coupon_id)
        
        # שליחת הקופון לקונה
        buyer_text = f"""
🎉 *הקופון שלך מוכן!*

אדמין אישר את התשלום שלך.

🎫 *{coupon.title if coupon else 'קופון'}*

🔐 *קוד הקופון:*
`{coupon.digital_code if coupon else 'לא זמין'}`
"""
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=buyer_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send coupon to buyer: {e}")
        
        # הודעה למוכר
        try:
            await context.bot.send_message(
                chat_id=seller_id,
                text=f"""
⚠️ *העסקה אושרה על ידי אדמין*

אדמין אישר שהתשלום בוצע.
הקופון שוחרר לקונה.

💸 נוכו {commission:.2f} נקודות עמלה.
🚨 נוסף קנס של {penalty:.2f} נקודות על אי-מענה בזמן.
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify seller: {e}")
        
        await query.edit_message_caption(
            f"✅ אושר! קופון שוחרר לקונה.\n"
            f"קנס {penalty}₪ הוחל על המוכר.",
            parse_mode="Markdown"
        )
    
    @staticmethod
    async def admin_reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אדמין דוחה תשלום מזויף וחוסם קונה"""
        query = update.callback_query
        await query.answer()
        
        admin_id = update.effective_user.id
        if admin_id not in Config.ADMIN_IDS:
            await query.answer("❌ אין לך הרשאות", show_alert=True)
            return
        
        order_id = ObjectId(query.data.replace("p2p_admin_reject_", ""))
        
        p2p_orders = await database.get_p2p_orders_collection()
        order_data = await p2p_orders.find_one({"_id": order_id})
        
        if not order_data:
            await query.edit_message_caption("❌ הזמנה לא נמצאה")
            return
        
        buyer_id = order_data["buyer_id"]
        seller_id = order_data["seller_id"]
        coupon_id = order_data["coupon_id"]
        
        # ביטול ההזמנה
        await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.CANCELLED.value,
                    "admin_notes": f"נדחה על ידי אדמין {admin_id} - תשלום מזויף"
                }
            }
        )
        
        # החזרת הקופון לסטטוס פעיל
        coupons = await database.get_coupons_collection()
        await coupons.update_one(
            {"_id": coupon_id},
            {"$set": {"status": CouponStatus.ACTIVE.value}}
        )
        
        # חסימת הקונה
        users = await database.get_users_collection()
        await users.update_one(
            {"user_id": buyer_id},
            {"$set": {"blocked": True, "block_reason": "תשלום מזויף"}}
        )
        
        # הודעה לקונה
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text="""
🚫 *חשבונך נחסם*

העלית הוכחת תשלום מזויפת.
פעולה זו מהווה הונאה.

לערעור, פנה לתמיכה: /support
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify buyer: {e}")
        
        # הודעה למוכר
        try:
            await context.bot.send_message(
                chat_id=seller_id,
                text="""
✅ *המחלוקת נפתרה לטובתך*

אדמין אישר שהתשלום היה מזויף.
הקונה נחסם, הקופון שלך חזר להיות פעיל.
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify seller: {e}")
        
        await query.edit_message_caption(
            "✅ התשלום נדחה, הקונה נחסם.",
            parse_mode="Markdown"
        )
    
    @staticmethod
    async def cancel_p2p_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול תהליך רכישה P2P"""
        order_id_str = context.user_data.get("p2p_order_id")
        
        if order_id_str:
            # ביטול ההזמנה אם נוצרה
            p2p_orders = await database.get_p2p_orders_collection()
            await p2p_orders.update_one(
                {"_id": ObjectId(order_id_str), "status": P2POrderStatus.PENDING_BUYER_PAYMENT.value},
                {"$set": {"status": P2POrderStatus.CANCELLED.value}}
            )
        
        # ניקוי קונטקסט
        context.user_data.pop("p2p_order_id", None)
        context.user_data.pop("p2p_coupon_id", None)
        context.user_data.pop("p2p_method", None)
        
        await update.message.reply_text("❌ הרכישה בוטלה")
        return ConversationHandler.END


# פונקציה לטיפול ב-timeout אוטומטי (תרוץ כ-background task)
async def process_p2p_timeouts(bot) -> int:
    """
    בדיקה ועיבוד של הזמנות שעברו timeout
    מופעל על ידי background scheduler
    
    Returns:
        מספר ההזמנות שנכנסו למחלוקת
    """
    p2p_orders = await database.get_p2p_orders_collection()
    
    # מציאת הזמנות שעברו את זמן האישור
    now = datetime.utcnow()
    
    cursor = p2p_orders.find({
        "status": P2POrderStatus.PENDING_SELLER_CONFIRMATION.value,
        "seller_confirmation_deadline": {"$lte": now}
    })
    
    timed_out_orders = await cursor.to_list(length=None)
    processed = 0
    
    for order_data in timed_out_orders:
        order_id = order_data["_id"]
        seller_id = order_data["seller_id"]
        buyer_id = order_data["buyer_id"]
        
        # עדכון לסטטוס מחלוקת אוטומטית
        await p2p_orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": P2POrderStatus.AUTO_DISPUTE.value,
                    "dispute_opened_at": now,
                    "dispute_reason": "timeout - המוכר לא אישר בזמן"
                }
            }
        )
        
        # התראה לאדמינים
        admin_text = f"""
⏰ *מחלוקת אוטומטית - Timeout*

המוכר לא אישר קבלת תשלום תוך {Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות.

🆔 הזמנה: `{order_id}`
👤 קונה: {buyer_id}
🏪 מוכר: {seller_id}
💰 סכום: {order_data['price']:.2f}₪
"""
        
        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ שחרר קופון + קנס למוכר", callback_data=f"p2p_admin_release_{order_id}")],
            [InlineKeyboardButton("❌ דחה תשלום", callback_data=f"p2p_admin_reject_{order_id}")],
        ])
        
        for admin_id in Config.ADMIN_IDS:
            try:
                if order_data.get("payment_proof_image"):
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=order_data["payment_proof_image"],
                        caption=admin_text,
                        reply_markup=admin_keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_keyboard,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} about timeout: {e}")
        
        # התראה לקונה
        try:
            await bot.send_message(
                chat_id=buyer_id,
                text=f"""
⏰ *המוכר לא אישר בזמן*

עברו {Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות והמוכר לא אישר קבלת התשלום.
העסקה נכנסה למחלוקת אוטומטית.

🔍 אדמין יבדוק את צילום ההוכחה שלך.
תקבל הודעה על ההחלטה.
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify buyer {buyer_id} about timeout: {e}")
        
        # התראה למוכר
        try:
            await bot.send_message(
                chat_id=seller_id,
                text=f"""
⚠️ *לא אישרת תשלום בזמן!*

עברו {Config.SELLER_CONFIRMATION_TIMEOUT_HOURS} שעות ולא אישרת קבלת תשלום.
העסקה נכנסה למחלוקת.

🚨 אם התשלום יאושר על ידי אדמין, תקבל קנס של {Config.SELLER_TIMEOUT_PENALTY}₪.
""",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify seller {seller_id} about timeout: {e}")
        
        processed += 1
        logger.info(f"Auto-dispute created for order {order_id} due to timeout")
    
    return processed
