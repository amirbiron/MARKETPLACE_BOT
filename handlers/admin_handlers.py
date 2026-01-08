"""
Handlers לאדמינים - ניהול המערכת
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from services.fraud_detection_service import FraudDetectionService, FraudEventType, FraudRiskLevel
from services.escrow_service import EscrowService
from models import EscrowStatus
from keyboards import Keyboards
from utils import format_price, format_datetime
from config import Config
from datetime import datetime
import database
import logging

logger = logging.getLogger(__name__)

# States for conversations
BROADCAST_MESSAGE, BLOCK_USER_ID, ADD_BALANCE_AMOUNT, SEND_USER_MESSAGE = range(20, 24)


class AdminHandlers:
    """Handlers לאדמינים"""
    
    @staticmethod
    async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט אדמין ראשי"""
        user_id = update.effective_user.id
        query = update.callback_query
        
        if not await UserService.is_admin(user_id):
            error_text = "❌ אין לך הרשאות אדמין."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        # סטטיסטיקות מהירות
        users = await database.get_users_collection()
        coupons = await database.get_coupons_collection()
        orders = await database.get_orders_collection()
        
        total_users = await users.count_documents({})
        total_sellers = await users.count_documents({"role": {"$in": ["seller_verified", "seller_unverified"]}})
        total_coupons = await coupons.count_documents({"status": "active"})
        total_orders = await orders.count_documents({})
        
        text = f"""
👨‍💼 *פאנל אדמין*

📊 *סטטיסטיקות מהירות:*
👥 משתמשים: {total_users}
💼 מוכרים: {total_sellers}
🎫 קופונים פעילים: {total_coupons}
📦 הזמנות: {total_orders}

בחר פעולה:
"""
        
        keyboard = Keyboards.admin_main_keyboard()
        
        if query:
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_seller_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת בקשות רישום מוכרים"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        if not await UserService.is_admin(user_id):
            await query.edit_message_text("❌ אין לך הרשאות.")
            return
        
        # קבלת מוכרים ממתינים לאישור
        users = await database.get_users_collection()
        pending = await users.find({
            "seller_status": "pending",
            "role": {"$in": ["seller_verified", "seller_unverified"]}
        }).to_list(10)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין בקשות ממתינות.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        text = f"👥 *בקשות רישום מוכרים:* ({len(pending)} ממתינות)\n\n"
        
        items = []
        for seller_data in pending:
            from models import User
            seller = User.from_dict(seller_data)
            verified = "✅ מאומת" if seller.is_verified else "📝 רגיל"
            commercial = seller.commercial_name or seller.business_name or seller.first_name
            items.append((
                f"{commercial} - {verified}",
                f"seller_req_{seller.user_id}"
            ))
        
        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "seller_reqs")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_seller_request_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פרטי בקשת מוכר"""
        query = update.callback_query
        await query.answer()
        
        seller_id = int(query.data.replace("seller_req_", ""))
        seller = await UserService.get_user(seller_id)
        
        if not seller:
            await query.edit_message_text("❌ המוכר לא נמצא.")
            return
        
        verified_str = "מאומת ✅" if seller.is_verified else "רגיל"
        commission = "3%" if seller.is_verified else "5%"
        commercial = seller.commercial_name or seller.business_name or "לא צוין"
        
        text = f"""
👤 *פרטי בקשת מוכר*

🏢 שם עסק: {seller.business_name or 'לא צוין'}
🏷️ שם מסחרי: {commercial}
📞 טלפון: {seller.phone or 'לא צוין'}
{"🆔 ת.ז: סופק ✅" if seller.id_number else "🆔 ת.ז: לא סופק"}

📊 סוג מוכר: {verified_str}
💰 עמלה: {commission}
👤 שם: {seller.first_name or 'לא זמין'}
📛 Telegram: @{seller.username or 'לא זמין'}
🔑 User ID: `{seller.user_id}`

בחר פעולה:
"""
        
        keyboard = Keyboards.admin_seller_request_keyboard(seller.user_id)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def approve_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור מוכר"""
        query = update.callback_query
        await query.answer()
        
        seller_id = int(query.data.replace("approve_seller_", ""))
        seller = await UserService.get_user(seller_id)
        
        # עדכון סטטוס לאושר
        success = await UserService.approve_seller(seller_id)
        
        if success:
            # שליחת הודעה למוכר
            commercial = seller.commercial_name or seller.business_name or "מוכר"
            verified_str = "מאומת ✅" if seller.is_verified else "רגיל"
            commission = "3%" if seller.is_verified else "5%"
            
            try:
                await context.bot.send_message(
                    seller_id,
                    f"🎉 *מזל טוב! בקשתך אושרה!*\n\n"
                    f"🏷️ שם מסחרי: {commercial}\n"
                    f"📊 סוג מוכר: {verified_str}\n"
                    f"💰 עמלה: {commission}\n\n"
                    f"✅ כעת תוכל להתחיל להעלות קופונים!\n"
                    f"השתמש ב-/upload להעלאת קופון חדש.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify seller {seller_id}: {e}")
            
            # עדכון הודעת האדמין
            admin_id = update.effective_user.id
            new_text = query.message.text + f"\n\n✅ *אושר* על ידי אדמין {admin_id}"
            try:
                await query.edit_message_text(new_text, parse_mode="Markdown")
            except:
                await query.edit_message_text(
                    f"✅ המוכר {commercial} אושר בהצלחה!",
                    reply_markup=Keyboards.back_button()
                )
        else:
            await query.edit_message_text("❌ האישור נכשל.")
    
    @staticmethod
    async def reject_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דחיית מוכר (תאימות לאחור)"""
        query = update.callback_query
        await query.answer()

        seller_id = int(query.data.replace("reject_seller_", ""))
        # route to the new handler logic
        query.data = f"block_seller_{seller_id}"
        return await AdminHandlers.block_seller(update, context)

    @staticmethod
    async def block_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חסימת בקשת מוכר"""
        query = update.callback_query
        await query.answer()

        seller_id = int(query.data.replace("block_seller_", ""))
        seller = await UserService.get_user(seller_id)

        success = await UserService.block_seller(seller_id)

        if success:
            commercial = seller.commercial_name or seller.business_name or "מוכר"

            # הודעה למוכר
            try:
                await context.bot.send_message(
                    seller_id,
                    "🚫 *הבקשה שלך נחסמה*\n\n"
                    "לצערנו, בקשתך לרישום כמוכר לא אושרה כרגע.\n\n"
                    "אם אתה חושב שזו טעות, פנה לתמיכה: /support",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify seller {seller_id}: {e}")

            # עדכון הודעת האדמין
            admin_id = update.effective_user.id
            new_text = (query.message.text or "") + f"\n\n🚫 *נחסם* על ידי אדמין {admin_id}"
            try:
                await query.edit_message_text(new_text, parse_mode="Markdown")
            except Exception:
                await query.edit_message_text(
                    f"🚫 הבקשה של {commercial} נחסמה.",
                    reply_markup=Keyboards.back_button()
                )
        else:
            await query.edit_message_text("❌ החסימה נכשלה.")
    
    @staticmethod
    async def show_payout_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת בקשות משיכה"""
        query = update.callback_query
        await query.answer()
        
        payouts = await database.get_payouts_collection()
        pending = await payouts.find({"status": "pending"}).sort("created_at", -1).to_list(10)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין בקשות משיכה ממתינות.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        items = []
        for payout_data in pending:
            from models import Payout
            payout = Payout.from_dict(payout_data)
            seller = await UserService.get_user(payout.seller_id)
            
            items.append((
                f"{seller.business_name if seller else 'מוכר'} - {format_price(payout.net_amount)}",
                f"payout_{str(payout._id)}"
            ))
        
        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "payouts")
        text = "💸 *בקשות משיכה ממתינות:*"
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_disputes(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת מחלוקות פתוחות"""
        query = update.callback_query
        await query.answer()
        
        disputes = await database.get_disputes_collection()
        open_disputes = await disputes.find({"status": "open"}).sort("created_at", -1).to_list(10)
        
        if not open_disputes:
            await query.edit_message_text(
                "✅ אין מחלוקות פתוחות.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        items = []
        for dispute_data in open_disputes:
            from models import Dispute
            dispute = Dispute.from_dict(dispute_data)
            order = await OrderService.get_order(dispute.order_id)
            
            items.append((
                f"מחלוקת #{str(dispute._id)[:8]} - {format_datetime(dispute.created_at)}",
                f"dispute_{str(dispute._id)}"
            ))
        
        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "disputes")
        text = "⚖️ *מחלוקות פתוחות:*"
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def add_balance_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הוספת יתרה למשתמש"""
        query = update.callback_query
        await query.answer()
        
        # רשימת משתמשים אחרונים
        users = await database.get_users_collection()
        recent = await users.find().sort("created_at", -1).limit(10).to_list(10)
        
        items = []
        for user_data in recent:
            from models import User
            user = User.from_dict(user_data)
            items.append((
                f"{user.first_name or 'משתמש'} (@{user.username or 'N/A'}) - {format_price(user.balance)}",
                f"addbal_{user.user_id}"
            ))
        
        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "addbal")
        text = "💵 *בחר משתמש להוספת יתרה:*"
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_system_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סטטיסטיקות מערכת מפורטות"""
        query = update.callback_query
        await query.answer()
        
        users = await database.get_users_collection()
        coupons = await database.get_coupons_collection()
        orders = await database.get_orders_collection()
        
        # משתמשים
        total_users = await users.count_documents({})
        total_buyers = await users.count_documents({"role": "buyer"})
        total_sellers = await users.count_documents({"role": {"$in": ["seller_verified", "seller_unverified"]}})
        verified_sellers = await users.count_documents({"role": "seller_verified"})
        
        # קופונים
        active_coupons = await coupons.count_documents({"status": "active"})
        sold_coupons = await coupons.count_documents({"status": "sold"})
        
        # הזמנות
        total_orders = await orders.count_documents({})
        completed_orders = await orders.count_documents({"status": {"$in": ["completed", "confirmed"]}})
        pending_orders = await orders.count_documents({"status": "pending"})
        
        # הכנסות מערכת (עמלות)
        pipeline = [
            {"$match": {"status": {"$in": ["completed", "confirmed"]}}},
            {"$group": {
                "_id": None,
                "buyer_commissions": {"$sum": "$buyer_commission"},
                "seller_commissions": {"$sum": "$seller_commission"}
            }}
        ]
        
        cursor = orders.aggregate(pipeline)
        commission_data = await cursor.to_list(1)
        
        if commission_data:
            total_commissions = commission_data[0]['buyer_commissions'] + commission_data[0]['seller_commissions']
        else:
            total_commissions = 0
        
        text = f"""
📊 *סטטיסטיקות מערכת מפורטות*

👥 *משתמשים:*
  • סה"כ: {total_users}
  • קונים: {total_buyers}
  • מוכרים: {total_sellers}
  • מאומתים: {verified_sellers}

🎫 *קופונים:*
  • פעילים: {active_coupons}
  • נמכרו: {sold_coupons}

📦 *הזמנות:*
  • סה"כ: {total_orders}
  • הושלמו: {completed_orders}
  • ממתינות: {pending_orders}

💰 *הכנסות מערכת:*
  • עמלות: {format_price(total_commissions)}
"""
        
        await query.edit_message_text(text, reply_markup=Keyboards.back_button(), parse_mode="Markdown")
    
    # ==================== ניהול מערכת ====================
    
    @staticmethod
    async def system_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט ניהול מערכת"""
        user_id = update.effective_user.id
        
        if user_id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ אין לך הרשאות אדמין.")
            return
        
        text = """
🔧 *ניהול מערכת*

בחר פעולה:
"""
        
        keyboard = Keyboards.system_management_keyboard()
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניהול משתמשים - רשימה"""
        query = update.callback_query
        await query.answer()
        
        users_col = await database.get_users_collection()
        
        # סטטיסטיקות
        total = await users_col.count_documents({})
        blocked = await users_col.count_documents({"blocked": True})
        
        # 10 משתמשים אחרונים
        recent = await users_col.find().sort("created_at", -1).limit(10).to_list(10)
        
        text = f"""
👥 *ניהול משתמשים*

📊 סה"כ: {total} | חסומים: {blocked}

*משתמשים אחרונים:*
"""
        
        keyboard = []
        for user_data in recent:
            from models import User
            user = User.from_dict(user_data)
            role_emoji = "🏪" if "seller" in user.role.value else "👤"
            blocked_mark = "🚫" if getattr(user, 'blocked', False) else ""
            
            text += f"\n{role_emoji}{blocked_mark} {user.first_name or 'משתמש'} | {format_price(user.balance)}"
            
            keyboard.append([InlineKeyboardButton(
                f"{role_emoji} {user.first_name or user.username or user.user_id}",
                callback_data=f"sys_user_{user.user_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔍 חיפוש לפי ID", callback_data="sys_search_user")])
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="sys_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def view_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפרטי משתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("sys_user_", ""))
        user = await UserService.get_user(user_id)
        
        if not user:
            await query.edit_message_text("❌ משתמש לא נמצא")
            return
        
        # ספירת הזמנות
        orders_col = await database.get_orders_collection()
        order_count = await orders_col.count_documents({"buyer_id": user_id})
        
        blocked_status = "🚫 חסום" if getattr(user, 'blocked', False) else "✅ פעיל"
        role_text = {
            "buyer": "קונה",
            "seller_unverified": "מוכר (לא מאומת)",
            "seller_verified": "מוכר מאומת",
            "admin": "אדמין"
        }.get(user.role.value, user.role.value)
        
        text = f"""
👤 *פרטי משתמש*

🆔 ID: `{user.user_id}`
📛 שם: {user.first_name or 'לא מוגדר'}
👤 Username: @{user.username or 'לא מוגדר'}

📋 תפקיד: {role_text}
📊 סטטוס: {blocked_status}

💰 יתרה: {format_price(user.balance)}
🔒 קפואה: {format_price(user.frozen_balance)}
📦 הזמנות: {order_count}

📅 הצטרף: {user.created_at.strftime('%d/%m/%Y %H:%M') if user.created_at else 'לא ידוע'}
"""
        
        if user.business_name:
            text += f"\n🏪 שם עסק: {user.business_name}"
        if user.phone:
            text += f"\n📱 טלפון: {user.phone}"
        
        # כפתורי פעולה
        keyboard = []
        
        if getattr(user, 'blocked', False):
            keyboard.append([InlineKeyboardButton("✅ בטל חסימה", callback_data=f"sys_unblock_{user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🚫 חסום משתמש", callback_data=f"sys_block_{user_id}")])
        
        keyboard.append([InlineKeyboardButton("💵 הוסף יתרה", callback_data=f"sys_addbal_{user_id}")])
        keyboard.append([InlineKeyboardButton("📨 שלח הודעה", callback_data=f"sys_msg_{user_id}")])
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="sys_manage_users")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חסימת משתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("sys_block_", ""))
        
        users_col = await database.get_users_collection()
        result = await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": True, "blocked_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            # הודעה למשתמש
            try:
                await context.bot.send_message(
                    user_id,
                    "🚫 חשבונך נחסם.\nלפרטים נוספים פנה לתמיכה."
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ משתמש {user_id} נחסם בהצלחה",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"sys_user_{user_id}")
                ]])
            )
        else:
            await query.edit_message_text("❌ החסימה נכשלה")
    
    @staticmethod
    async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול חסימת משתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("sys_unblock_", ""))
        
        users_col = await database.get_users_collection()
        result = await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": False}, "$unset": {"blocked_at": ""}}
        )
        
        if result.modified_count > 0:
            try:
                await context.bot.send_message(
                    user_id,
                    "✅ החסימה על חשבונך הוסרה.\nברוך הבא בחזרה!"
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ החסימה על משתמש {user_id} הוסרה",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"sys_user_{user_id}")
                ]])
            )
        else:
            await query.edit_message_text("❌ ביטול החסימה נכשל")
    
    @staticmethod
    async def manage_sellers(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניהול מוכרים"""
        query = update.callback_query
        await query.answer()
        
        users_col = await database.get_users_collection()
        
        # מוכרים
        sellers = await users_col.find({
            "role": {"$in": ["seller_verified", "seller_unverified"]}
        }).sort("created_at", -1).limit(15).to_list(15)
        
        verified_count = await users_col.count_documents({"role": "seller_verified"})
        unverified_count = await users_col.count_documents({"role": "seller_unverified"})
        
        text = f"""
🏪 *ניהול מוכרים*

📊 מאומתים: {verified_count} | רגילים: {unverified_count}

*מוכרים:*
"""
        
        keyboard = []
        for seller_data in sellers:
            from models import User
            seller = User.from_dict(seller_data)
            verified = "✅" if seller.role.value == "seller_verified" else "📝"
            blocked = "🚫" if getattr(seller, 'blocked', False) else ""
            
            keyboard.append([InlineKeyboardButton(
                f"{verified}{blocked} {seller.business_name or seller.first_name or 'מוכר'}",
                callback_data=f"sys_user_{seller.user_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="sys_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def manage_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניהול קופונים"""
        query = update.callback_query
        await query.answer()
        
        coupons_col = await database.get_coupons_collection()
        
        active = await coupons_col.count_documents({"status": "active"})
        sold = await coupons_col.count_documents({"status": "sold"})
        expired = await coupons_col.count_documents({"status": "expired"})
        
        # קופונים אחרונים
        recent = await coupons_col.find().sort("created_at", -1).limit(10).to_list(10)
        
        text = f"""
🎫 *ניהול קופונים*

📊 פעילים: {active} | נמכרו: {sold} | פג תוקף: {expired}

*קופונים אחרונים:*
"""
        
        keyboard = []
        for coupon_data in recent:
            from models import Coupon
            coupon = Coupon.from_dict(coupon_data)
            status_emoji = {"active": "🟢", "sold": "✅", "expired": "🔴"}.get(coupon.status.value, "❓")
            
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {coupon.title[:25]} | {format_price(coupon.sale_price)}",
                callback_data=f"sys_coupon_{str(coupon._id)}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="sys_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def view_coupon_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפרטי קופון"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = query.data.replace("sys_coupon_", "")
        coupon = await CouponService.get_coupon(ObjectId(coupon_id))
        
        if not coupon:
            await query.edit_message_text("❌ קופון לא נמצא")
            return
        
        seller = await UserService.get_user(coupon.seller_id)
        
        status_text = {
            "active": "🟢 פעיל",
            "sold": "✅ נמכר",
            "expired": "🔴 פג תוקף",
            "deleted": "🗑️ נמחק"
        }.get(coupon.status.value, coupon.status.value)
        
        text = f"""
🎫 *פרטי קופון*

📛 {coupon.title}
📁 קטגוריה: {coupon.category}

💰 מחיר מקורי: {format_price(coupon.original_price)}
💵 מחיר מכירה: {format_price(coupon.sale_price)}

👤 מוכר: {seller.business_name if seller else 'לא ידוע'}
📊 סטטוס: {status_text}

📅 נוצר: {coupon.created_at.strftime('%d/%m/%Y %H:%M') if coupon.created_at else 'לא ידוע'}
"""
        
        keyboard = []
        if coupon.status.value == "active":
            keyboard.append([InlineKeyboardButton("🗑️ מחק קופון", callback_data=f"sys_del_coupon_{coupon_id}")])
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="sys_manage_coupons")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def delete_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מחיקת קופון"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = query.data.replace("sys_del_coupon_", "")
        
        coupons_col = await database.get_coupons_collection()
        result = await coupons_col.update_one(
            {"_id": ObjectId(coupon_id)},
            {"$set": {"status": "deleted", "deleted_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            await query.edit_message_text(
                "✅ הקופון נמחק בהצלחה",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="sys_manage_coupons")
                ]])
            )
        else:
            await query.edit_message_text("❌ המחיקה נכשלה")
    
    @staticmethod
    async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת שליחת הודעה לכולם"""
        query = update.callback_query
        await query.answer()
        
        text = """
📢 *שליחת הודעה לכל המשתמשים*

כתוב את ההודעה שתישלח לכל המשתמשים במערכת.

⚠️ *שים לב:* ההודעה תישלח לכולם!

לביטול: /cancel
"""
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return BROADCAST_MESSAGE
    
    @staticmethod
    async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שליחת ההודעה לכולם"""
        message_text = update.message.text
        admin_id = update.effective_user.id
        
        if admin_id not in Config.ADMIN_IDS:
            return ConversationHandler.END
        
        users_col = await database.get_users_collection()
        all_users = await users_col.find({"blocked": {"$ne": True}}).to_list(None)
        
        sent = 0
        failed = 0
        
        status_msg = await update.message.reply_text("📤 שולח הודעות... 0%")
        
        for i, user_data in enumerate(all_users):
            try:
                await context.bot.send_message(
                    user_data["user_id"],
                    f"📢 *הודעה מהמערכת*\n\n{message_text}",
                    parse_mode="Markdown"
                )
                sent += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to send broadcast to {user_data['user_id']}: {e}")
            
            # עדכון התקדמות כל 10 הודעות
            if (i + 1) % 10 == 0:
                progress = int((i + 1) / len(all_users) * 100)
                try:
                    await status_msg.edit_text(f"📤 שולח הודעות... {progress}%")
                except:
                    pass
        
        await status_msg.edit_text(
            f"✅ *שליחה הושלמה!*\n\n"
            f"📨 נשלחו: {sent}\n"
            f"❌ נכשלו: {failed}",
            parse_mode="Markdown"
        )
        
        return ConversationHandler.END
    
    @staticmethod
    async def view_pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בבקשות הפקדה ממתינות"""
        query = update.callback_query
        await query.answer()
        
        deposits = database.db.deposit_requests
        pending = await deposits.find({"status": "pending"}).sort("created_at", -1).limit(15).to_list(15)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין בקשות הפקדה ממתינות",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="admin_menu")
                ]])
            )
            return
        
        text = f"💰 *בקשות הפקדה ממתינות ({len(pending)}):*\n\n"
        
        keyboard = []
        for dep in pending:
            user = await UserService.get_user(dep["user_id"])
            name = user.first_name if user else "משתמש"
            
            text += f"• {name} - {dep['amount']}₪ - {dep['reference_code']}\n"
            
            keyboard.append([InlineKeyboardButton(
                f"💵 {name} - {dep['amount']}₪",
                callback_data=f"view_deposit_{str(dep['_id'])}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="admin_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בלוגים אחרונים"""
        query = update.callback_query
        await query.answer()
        
        # נציג פעולות אחרונות מהמערכת
        transactions = await database.db.transactions.find().sort("created_at", -1).limit(20).to_list(20)
        
        text = "📋 *לוגים אחרונים:*\n\n"
        
        if not transactions:
            text += "אין פעולות אחרונות"
        else:
            for txn in transactions[:15]:
                amount = txn.get("amount", 0)
                sign = "+" if amount > 0 else ""
                emoji = "💰" if amount > 0 else "💸"
                
                text += f"{emoji} {sign}{amount:.0f}₪ | {txn.get('description', 'פעולה')[:30]}\n"
                text += f"   {txn['created_at'].strftime('%d/%m %H:%M')}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="sys_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def system_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הגדרות מערכת"""
        query = update.callback_query
        await query.answer()
        
        text = f"""
⚙️ *הגדרות מערכת נוכחיות*

💰 *עמלות:*
• קונה: {Config.BUYER_COMMISSION_RATE * 100:.0f}%
• מוכר מאומת: {Config.VERIFIED_SELLER_COMMISSION_RATE * 100:.0f}%
• מוכר רגיל: {Config.UNVERIFIED_SELLER_COMMISSION_RATE * 100:.0f}%
• משיכה: {Config.WITHDRAWAL_COMMISSION * 100:.0f}%

📊 *הגבלות:*
• מינימום משיכה: {Config.MIN_WITHDRAWAL_AMOUNT}₪
• מינימום הפקדה: {Config.MIN_DEPOSIT_AMOUNT}₪
• קופונים ליום (לא מאומת): {Config.DAILY_COUPON_LIMIT_UNVERIFIED}

⏰ *זמנים:*
• חלון דיווח: {Config.REPORT_WINDOW_HOURS} שעות
• הקפאת כספים: {Config.BALANCE_FREEZE_HOURS} שעות

👨‍💼 *אדמינים:*
{', '.join([str(aid) for aid in Config.ADMIN_IDS])}

💳 *פרטי תשלום:*
• ביט: {Config.BIT_PHONE or 'לא מוגדר'}
• פייבוקס: {'מוגדר' if Config.PAYBOX_LINK else 'לא מוגדר'}
• בנק: {Config.BANK_NAME or 'לא מוגדר'}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="sys_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def sys_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חזרה לתפריט ניהול מערכת"""
        query = update.callback_query
        await query.answer()
        
        text = """
🔧 *ניהול מערכת*

בחר פעולה:
"""
        
        keyboard = Keyboards.system_management_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול פעולת אדמין"""
        await update.message.reply_text("❌ הפעולה בוטלה")
        return ConversationHandler.END
    
    @staticmethod
    async def start_add_balance_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת הוספת יתרה למשתמש ספציפי"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("sys_addbal_", ""))
        context.user_data["add_balance_user_id"] = user_id
        
        user = await UserService.get_user(user_id)
        name = user.first_name if user else "משתמש"
        
        text = f"""
💵 *הוספת יתרה ל{name}*

יתרה נוכחית: {format_price(user.balance) if user else '0₪'}

שלח את הסכום להוספה (מספר בלבד):
לדוגמה: 100

לביטול: /cancel
"""
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return ADD_BALANCE_AMOUNT
    
    @staticmethod
    async def process_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד הוספת יתרה"""
        admin_id = update.effective_user.id
        
        if admin_id not in Config.ADMIN_IDS:
            return ConversationHandler.END
        
        try:
            amount = float(update.message.text.strip())
            if amount <= 0:
                await update.message.reply_text("❌ הסכום חייב להיות חיובי. נסה שוב:")
                return ADD_BALANCE_AMOUNT
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין:")
            return ADD_BALANCE_AMOUNT
        
        user_id = context.user_data.get("add_balance_user_id")
        if not user_id:
            await update.message.reply_text("❌ שגיאה. התחל מחדש.")
            return ConversationHandler.END
        
        # הוספת היתרה
        from services.payment_service import PaymentService
        success = await PaymentService.add_balance(
            user_id,
            amount,
            f"הוספה ידנית ע\"י אדמין {admin_id}"
        )
        
        if success:
            user = await UserService.get_user(user_id)
            
            # הודעה למשתמש
            try:
                await context.bot.send_message(
                    user_id,
                    f"💰 *התקבלה יתרה!*\n\n"
                    f"סכום: {format_price(amount)}\n"
                    f"יתרה חדשה: {format_price(user.balance) if user else 'לא ידוע'}",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ נוספו {format_price(amount)} למשתמש {user_id}\n"
                f"יתרה חדשה: {format_price(user.balance) if user else 'לא ידוע'}"
            )
        else:
            await update.message.reply_text("❌ ההוספה נכשלה")
        
        context.user_data.pop("add_balance_user_id", None)
        return ConversationHandler.END
    
    @staticmethod
    async def start_send_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת שליחת הודעה למשתמש ספציפי"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("sys_msg_", ""))
        context.user_data["msg_user_id"] = user_id
        
        user = await UserService.get_user(user_id)
        name = user.first_name if user else "משתמש"
        
        text = f"""
📨 *שליחת הודעה ל{name}*

כתוב את ההודעה שתישלח למשתמש:

לביטול: /cancel
"""
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return SEND_USER_MESSAGE
    
    @staticmethod
    async def process_send_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד שליחת הודעה למשתמש"""
        admin_id = update.effective_user.id
        
        if admin_id not in Config.ADMIN_IDS:
            return ConversationHandler.END
        
        message_text = update.message.text
        user_id = context.user_data.get("msg_user_id")
        
        if not user_id:
            await update.message.reply_text("❌ שגיאה. התחל מחדש.")
            return ConversationHandler.END
        
        try:
            await context.bot.send_message(
                user_id,
                f"📨 *הודעה מהמערכת*\n\n{message_text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ ההודעה נשלחה למשתמש {user_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ השליחה נכשלה: {str(e)}")
        
        context.user_data.pop("msg_user_id", None)
        return ConversationHandler.END

    # ==================== Fraud Management Handlers ====================

    @staticmethod
    async def fraud_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט ניהול הונאות"""
        query = update.callback_query
        if query:
            await query.answer()
        
        user_id = update.effective_user.id
        if not await UserService.is_admin(user_id):
            if query:
                await query.edit_message_text("❌ אין לך הרשאות אדמין.")
            else:
                await update.message.reply_text("❌ אין לך הרשאות אדמין.")
            return
        
        # קבלת סטטיסטיקות מהירות
        stats = await FraudDetectionService.get_fraud_stats()
        
        text = f"""
🛡️ *ניהול הונאות (Anti-Fraud)*

📊 *סטטיסטיקות מהירות:*
📋 סה"כ אירועים: {stats.get('total_events', 0)}
⏳ ממתינים לבדיקה: {stats.get('unreviewed_events', 0)}
🚫 משתמשים חסומים: {stats.get('blocked_users', 0)}
⚡ אירועים ב-24 שעות: {stats.get('recent_events_24h', 0)}

בחר פעולה:
"""
        
        keyboard = Keyboards.fraud_management_keyboard()
        
        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def fraud_pending_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת אירועי הונאה ממתינים לבדיקה"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        if not await UserService.is_admin(user_id):
            await query.edit_message_text("❌ אין לך הרשאות.")
            return
        
        pending = await FraudDetectionService.get_pending_reviews(limit=10)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין אירועי הונאה ממתינים לבדיקה!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")
                ]])
            )
            return
        
        text = f"🚨 *אירועי הונאה ממתינים ({len(pending)}):*\n\n"
        
        keyboard = []
        for event in pending:
            risk_emoji = {
                "critical": "🔴",
                "high": "🟠", 
                "medium": "🟡",
                "low": "🟢"
            }.get(event.get("risk_level", "low"), "⚪")
            
            event_type_names = {
                "duplicate_coupon": "קופון כפול",
                "high_dispute_rate": "מחלוקות גבוהות",
                "high_refund_rate": "החזרים גבוהים",
                "suspicious_pricing": "מחיר חשוד",
                "rapid_activity": "פעילות מהירה",
                "auto_block": "חסימה אוטומטית",
                "low_trust_score": "ניקוד נמוך",
                "large_transaction": "עסקה גדולה",
                "new_seller_limit": "הגבלת מוכר חדש"
            }
            
            event_name = event_type_names.get(event.get("event_type", ""), event.get("event_type", "לא ידוע"))
            user_id_event = event.get("user_id", 0)
            
            keyboard.append([InlineKeyboardButton(
                f"{risk_emoji} {event_name} | User: {user_id_event}",
                callback_data=f"fraud_event_{str(event['_id'])}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def fraud_view_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה באירוע הונאה בודד"""
        query = update.callback_query
        await query.answer()
        
        log_id = query.data.replace("fraud_event_", "")
        
        await database._ensure_connected()
        fraud_logs = database.db.fraud_logs
        
        event = await fraud_logs.find_one({"_id": ObjectId(log_id)})
        
        if not event:
            await query.edit_message_text(
                "❌ האירוע לא נמצא",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="fraud_pending_events")
                ]])
            )
            return
        
        risk_emoji = {
            "critical": "🔴 קריטי",
            "high": "🟠 גבוה",
            "medium": "🟡 בינוני",
            "low": "🟢 נמוך"
        }.get(event.get("risk_level", "low"), "⚪ לא ידוע")
        
        event_type_names = {
            "duplicate_coupon": "קופון כפול",
            "high_dispute_rate": "אחוז מחלוקות גבוה",
            "high_refund_rate": "אחוז החזרים גבוה",
            "suspicious_pricing": "מחיר חשוד",
            "rapid_activity": "פעילות מהירה מדי",
            "auto_block": "חסימה אוטומטית",
            "low_trust_score": "ניקוד אמינות נמוך",
            "large_transaction": "עסקה גדולה",
            "new_seller_limit": "הגבלת מוכר חדש"
        }
        
        event_name = event_type_names.get(event.get("event_type", ""), event.get("event_type", "לא ידוע"))
        event_user_id = event.get("user_id", 0)
        
        # קבלת פרטי המשתמש
        user = await UserService.get_user(event_user_id)
        user_name = user.first_name if user else "לא ידוע"
        user_role = user.role.value if user else "לא ידוע"
        
        # פירוט האירוע
        details = event.get("details", {})
        details_text = ""
        for key, value in details.items():
            details_text += f"  • {key}: {value}\n"
        
        text = f"""
🚨 *פרטי אירוע הונאה*

📋 *סוג:* {event_name}
⚠️ *רמת סיכון:* {risk_emoji}

👤 *משתמש:*
  • ID: `{event_user_id}`
  • שם: {user_name}
  • תפקיד: {user_role}

📝 *פרטים:*
{details_text or "  אין פרטים נוספים"}

📅 *תאריך:* {event.get('created_at', datetime.utcnow()).strftime('%d/%m/%Y %H:%M')}
✅ *נבדק:* {'כן' if event.get('reviewed') else 'לא'}
"""
        
        keyboard = Keyboards.fraud_event_keyboard(log_id, event_user_id)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def fraud_mark_reviewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סימון אירוע כנבדק"""
        query = update.callback_query
        await query.answer()
        
        admin_id = update.effective_user.id
        log_id = query.data.replace("fraud_mark_reviewed_", "")
        
        success = await FraudDetectionService.mark_as_reviewed(log_id, admin_id)
        
        if success:
            await query.edit_message_text(
                "✅ האירוע סומן כנבדק!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה לרשימה", callback_data="fraud_pending_events")
                ]])
            )
        else:
            await query.edit_message_text(
                "❌ הסימון נכשל",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="fraud_pending_events")
                ]])
            )

    @staticmethod
    async def fraud_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת סטטיסטיקות הונאה מפורטות"""
        query = update.callback_query
        await query.answer()
        
        stats = await FraudDetectionService.get_fraud_stats()
        
        # סוגי אירועים
        events_by_type = stats.get("events_by_type", {})
        type_names = {
            "duplicate_coupon": "קופון כפול",
            "high_dispute_rate": "מחלוקות גבוהות",
            "high_refund_rate": "החזרים גבוהים",
            "suspicious_pricing": "מחיר חשוד",
            "rapid_activity": "פעילות מהירה",
            "auto_block": "חסימה אוטומטית",
            "low_trust_score": "ניקוד נמוך",
            "large_transaction": "עסקה גדולה",
            "new_seller_limit": "הגבלת מוכר חדש"
        }
        
        types_text = ""
        for event_type, count in events_by_type.items():
            name = type_names.get(event_type, event_type)
            types_text += f"  • {name}: {count}\n"
        
        # רמות סיכון
        events_by_risk = stats.get("events_by_risk", {})
        risk_emojis = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        
        risk_text = ""
        for risk_level, count in events_by_risk.items():
            emoji = risk_emojis.get(risk_level, "⚪")
            risk_text += f"  {emoji} {risk_level}: {count}\n"
        
        text = f"""
📊 *סטטיסטיקות הונאה מפורטות*

📋 *כללי:*
  • סה"כ אירועים: {stats.get('total_events', 0)}
  • ממתינים לבדיקה: {stats.get('unreviewed_events', 0)}
  • משתמשים חסומים (אוטומטית): {stats.get('blocked_users', 0)}
  • אירועים ב-24 שעות: {stats.get('recent_events_24h', 0)}

📈 *לפי סוג אירוע:*
{types_text or "  אין נתונים"}

⚠️ *לפי רמת סיכון:*
{risk_text or "  אין נתונים"}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    @staticmethod
    async def fraud_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת רשימת משתמשים חסומים"""
        query = update.callback_query
        await query.answer()
        
        blocked = await UserService.get_blocked_users(limit=20)
        
        if not blocked:
            await query.edit_message_text(
                "✅ אין משתמשים חסומים!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")
                ]])
            )
            return
        
        text = f"🚫 *משתמשים חסומים ({len(blocked)}):*\n\n"
        
        users_list = []
        for user_data in blocked:
            name = user_data.get("first_name") or user_data.get("username") or str(user_data.get("user_id"))
            user_id = user_data.get("user_id")
            auto = "🤖" if user_data.get("auto_blocked") else "👤"
            
            text += f"{auto} {name} (ID: `{user_id}`)\n"
            users_list.append((f"{auto} {name}", user_id))
        
        keyboard = Keyboards.fraud_blocked_users_keyboard(users_list[:10], 0, (len(users_list) + 9) // 10)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def fraud_view_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפרטי משתמש מפאנל הונאות"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_view_user_", ""))
        user = await UserService.get_user(user_id)
        
        if not user:
            await query.edit_message_text(
                "❌ המשתמש לא נמצא",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")
                ]])
            )
            return
        
        # ניקוד אמינות
        trust_score = await FraudDetectionService.get_trust_score(user_id)
        trust_display = Keyboards.trust_score_display(trust_score)
        
        # ספירת אירועי הונאה
        fraud_history = await FraudDetectionService.get_user_fraud_history(user_id)
        
        is_blocked = getattr(user, 'blocked', False) or user.__dict__.get('blocked', False)
        blocked_status = "🚫 חסום" if is_blocked else "✅ פעיל"
        
        users_col = await database.get_users_collection()
        user_data = await users_col.find_one({"user_id": user_id})
        is_blocked = user_data.get("blocked", False) if user_data else False
        
        text = f"""
👤 *פרטי משתמש - פאנל הונאות*

🆔 ID: `{user.user_id}`
📛 שם: {user.first_name or 'לא מוגדר'}
👤 Username: @{user.username or 'לא מוגדר'}

📋 תפקיד: {user.role.value}
📊 סטטוס: {blocked_status}

🛡️ *ניקוד אמינות:*
{trust_display}

📈 *היסטוריית הונאה:*
  • סה"כ אירועים: {len(fraud_history)}

💰 יתרה: {format_price(user.balance)}
⭐ דירוג: {user.rating_average:.1f} ({user.rating_count} דירוגים)
"""
        
        keyboard = Keyboards.fraud_user_actions_keyboard(user_id, is_blocked)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def fraud_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת היסטוריית הונאה של משתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_user_history_", ""))
        history = await FraudDetectionService.get_user_fraud_history(user_id)
        
        if not history:
            await query.edit_message_text(
                f"✅ אין היסטוריית הונאה למשתמש {user_id}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")
                ]])
            )
            return
        
        text = f"📋 *היסטוריית הונאה - משתמש {user_id}*\n\n"
        
        type_names = {
            "duplicate_coupon": "קופון כפול",
            "high_dispute_rate": "מחלוקות",
            "high_refund_rate": "החזרים",
            "suspicious_pricing": "מחיר חשוד",
            "rapid_activity": "פעילות מהירה",
            "auto_block": "חסימה אוטו'",
            "low_trust_score": "ניקוד נמוך"
        }
        
        risk_emojis = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        
        for event in history[:15]:
            event_type = type_names.get(event.get("event_type", ""), event.get("event_type", ""))
            risk_emoji = risk_emojis.get(event.get("risk_level", "low"), "⚪")
            date = event.get("created_at", datetime.utcnow()).strftime("%d/%m %H:%M")
            reviewed = "✅" if event.get("reviewed") else "⏳"
            
            text += f"{risk_emoji} {event_type} | {date} {reviewed}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    @staticmethod
    async def fraud_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חסימת משתמש מפאנל הונאות"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_block_user_", ""))
        admin_id = update.effective_user.id
        
        success = await UserService.block_user(user_id, reason="חסימה ידנית מפאנל הונאות", auto=False)
        
        if success:
            # לוג האירוע
            await FraudDetectionService.log_fraud_event(
                user_id=user_id,
                event_type=FraudEventType.MANUAL_REVIEW,
                details={"action": "manual_block", "admin_id": admin_id},
                risk_level=FraudRiskLevel.HIGH
            )
            
            # הודעה למשתמש
            try:
                await context.bot.send_message(
                    user_id,
                    "🚫 חשבונך נחסם.\nלפרטים נוספים פנה לתמיכה."
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ משתמש {user_id} נחסם בהצלחה!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")
                ]])
            )
        else:
            await query.edit_message_text("❌ החסימה נכשלה")

    @staticmethod
    async def fraud_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול חסימת משתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_unblock_", ""))
        
        success = await UserService.unblock_user(user_id)
        
        if success:
            # הודעה למשתמש
            try:
                await context.bot.send_message(
                    user_id,
                    "✅ החסימה על חשבונך הוסרה.\nברוך הבא בחזרה!"
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ החסימה על משתמש {user_id} הוסרה!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")
                ]])
            )
        else:
            await query.edit_message_text("❌ ביטול החסימה נכשל")

    @staticmethod
    async def fraud_keep_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור שהמשתמש יישאר חסום"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_keep_blocked_", ""))
        admin_id = update.effective_user.id
        
        # לוג שהאדמין בדק ואישר
        await FraudDetectionService.log_fraud_event(
            user_id=user_id,
            event_type=FraudEventType.MANUAL_REVIEW,
            details={"action": "confirmed_block", "admin_id": admin_id},
            risk_level=FraudRiskLevel.HIGH
        )
        
        await query.edit_message_text(
            f"✅ אושר - משתמש {user_id} יישאר חסום",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")
            ]])
        )

    @staticmethod
    async def fraud_warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שליחת אזהרה למשתמש"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_warn_user_", ""))
        
        try:
            await context.bot.send_message(
                user_id,
                "⚠️ *אזהרה מהמערכת*\n\n"
                "זיהינו פעילות חשודה בחשבונך.\n"
                "אנא וודא שפעילותך תואמת את התקנון.\n"
                "המשך פעילות חשודה עלול לגרום לחסימת חשבונך.",
                parse_mode="Markdown"
            )
            
            await query.edit_message_text(
                f"✅ נשלחה אזהרה למשתמש {user_id}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")
                ]])
            )
        except Exception as e:
            await query.edit_message_text(f"❌ השליחה נכשלה: {str(e)}")

    @staticmethod
    async def fraud_calc_trust(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חישוב מחדש של ניקוד אמינות"""
        query = update.callback_query
        await query.answer()
        
        user_id = int(query.data.replace("fraud_calc_trust_", ""))
        
        new_score = await FraudDetectionService.calculate_trust_score(user_id)
        trust_display = Keyboards.trust_score_display(new_score)
        
        await query.edit_message_text(
            f"🛡️ *ניקוד אמינות מעודכן*\n\n"
            f"משתמש: `{user_id}`\n\n"
            f"{trust_display}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 חזרה", callback_data=f"fraud_view_user_{user_id}")
            ]])
        )

    # ==================== Escrow Management Handlers ====================

    @staticmethod
    async def escrow_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט ניהול Escrow"""
        query = update.callback_query
        if query:
            await query.answer()
        
        user_id = update.effective_user.id
        if not await UserService.is_admin(user_id):
            error_text = "❌ אין לך הרשאות אדמין."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        # קבלת סטטיסטיקות מהירות
        stats = await EscrowService.get_escrow_stats()
        
        text = f"""
🔐 *ניהול Escrow*

📊 *מצב נוכחי:*
💰 יתרת Escrow: {format_price(stats.get('escrow_balance', 0))}
⏳ ממתינים לשחרור: {stats.get('total_held', 0)}
⚖️ במחלוקת: {stats.get('total_disputed', 0)}
✅ שוחררו (סה"כ): {stats.get('total_released', 0)}
↩️ הוחזרו (סה"כ): {stats.get('total_refunded', 0)}

⚡ *פעילות ב-24 שעות:*
📥 נכנסו: {stats.get('recent_24h_held', 0)}
📤 שוחררו: {stats.get('recent_24h_released', 0)}

בחר פעולה:
"""
        
        keyboard = Keyboards.escrow_management_keyboard()
        
        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת יתרת Escrow מפורטת"""
        query = update.callback_query
        await query.answer()
        
        balance = await EscrowService.get_escrow_balance()
        stats = await EscrowService.get_escrow_stats()
        
        amounts = stats.get("amounts_by_status", {})
        
        text = f"""
💰 *יתרת Escrow מפורטת*

🔒 *סה"כ מוחזק:* {format_price(balance)}

📊 *פילוח לפי סטטוס:*
⏳ מוחזק (held): {format_price(amounts.get('held', 0))}
⚖️ במחלוקת (disputed): {format_price(amounts.get('disputed', 0))}
✅ שוחרר (released): {format_price(amounts.get('released', 0))}
↩️ הוחזר (refunded): {format_price(amounts.get('refunded', 0))}

📈 *סה"כ עסקאות:*
⏳ מוחזקות: {stats.get('total_held', 0)}
⚖️ במחלוקת: {stats.get('total_disputed', 0)}
✅ הושלמו: {stats.get('total_released', 0)}
↩️ הוחזרו: {stats.get('total_refunded', 0)}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    @staticmethod
    async def escrow_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת עסקאות Escrow ממתינות לשחרור"""
        query = update.callback_query
        await query.answer()
        
        pending = await EscrowService.get_all_held_escrows(limit=15)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין עסקאות Escrow ממתינות!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")
                ]])
            )
            return
        
        text = f"⏳ *עסקאות Escrow ממתינות ({len(pending)}):*\n\n"
        
        items = []
        for escrow in pending:
            # חישוב זמן שנותר לשחרור
            if escrow.release_scheduled_at:
                time_left = escrow.release_scheduled_at - datetime.utcnow()
                hours_left = max(0, int(time_left.total_seconds() // 3600))
                minutes_left = max(0, int((time_left.total_seconds() % 3600) // 60))
                time_str = f"{hours_left}:{minutes_left:02d}"
            else:
                time_str = "N/A"
            
            items.append((
                f"💰 {format_price(escrow.amount)} | ⏰ {time_str}",
                f"escrow_view_{str(escrow._id)}"
            ))
        
        keyboard = Keyboards.escrow_list_keyboard(items, 0, 1, "escrow_pending")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_disputed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת עסקאות Escrow במחלוקת"""
        query = update.callback_query
        await query.answer()
        
        disputed = await EscrowService.get_disputed_escrows(limit=15)
        
        if not disputed:
            await query.edit_message_text(
                "✅ אין עסקאות Escrow במחלוקת!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")
                ]])
            )
            return
        
        text = f"⚖️ *עסקאות Escrow במחלוקת ({len(disputed)}):*\n\n"
        
        items = []
        for escrow in disputed:
            held_date = escrow.held_at.strftime("%d/%m") if escrow.held_at else "N/A"
            
            items.append((
                f"⚖️ {format_price(escrow.amount)} | 📅 {held_date}",
                f"escrow_view_{str(escrow._id)}"
            ))
        
        keyboard = Keyboards.escrow_list_keyboard(items, 0, 1, "escrow_disputed")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בעסקת Escrow בודדת"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_view_", "")
        escrow = await EscrowService.get_escrow_by_id(ObjectId(escrow_id))
        
        if not escrow:
            await query.edit_message_text(
                "❌ עסקת Escrow לא נמצאה",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")
                ]])
            )
            return
        
        # קבלת פרטי משתמשים
        buyer = await UserService.get_user(escrow.buyer_id)
        seller = await UserService.get_user(escrow.seller_id)
        
        buyer_name = buyer.first_name if buyer else str(escrow.buyer_id)
        seller_name = seller.business_name or (seller.first_name if seller else str(escrow.seller_id))
        
        status_display = Keyboards.escrow_status_display(escrow.status.value)
        
        # חישוב זמן שנותר
        if escrow.status == EscrowStatus.HELD and escrow.release_scheduled_at:
            time_left = escrow.release_scheduled_at - datetime.utcnow()
            hours_left = max(0, int(time_left.total_seconds() // 3600))
            minutes_left = max(0, int((time_left.total_seconds() % 3600) // 60))
            time_str = f"{hours_left} שעות ו-{minutes_left} דקות"
        else:
            time_str = "N/A"
        
        text = f"""
🔐 *פרטי עסקת Escrow*

📊 *סטטוס:* {status_display}

💰 *סכומים:*
  • סכום עסקה: {format_price(escrow.amount)}
  • עמלת קונה: {format_price(escrow.buyer_commission)}
  • עמלת מוכר: {format_price(escrow.seller_commission)}
  • נטו למוכר: {format_price(escrow.net_seller_amount)}

👥 *משתתפים:*
  • קונה: {buyer_name} (`{escrow.buyer_id}`)
  • מוכר: {seller_name} (`{escrow.seller_id}`)

📅 *תאריכים:*
  • הוקפא: {escrow.held_at.strftime('%d/%m/%Y %H:%M') if escrow.held_at else 'N/A'}
  • שחרור מתוכנן: {escrow.release_scheduled_at.strftime('%d/%m/%Y %H:%M') if escrow.release_scheduled_at else 'N/A'}
  {"• שוחרר: " + escrow.released_at.strftime('%d/%m/%Y %H:%M') if escrow.released_at else ""}

⏰ *זמן לשחרור:* {time_str}

📝 *הערות:* {escrow.notes or 'אין'}
"""
        
        keyboard = Keyboards.escrow_transaction_keyboard(escrow_id, str(escrow.order_id), escrow.status.value)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שחרור כספים למוכר - אישור"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_release_", "")
        escrow = await EscrowService.get_escrow_by_id(ObjectId(escrow_id))
        
        if not escrow:
            await query.edit_message_text("❌ עסקת Escrow לא נמצאה")
            return
        
        seller = await UserService.get_user(escrow.seller_id)
        seller_name = seller.business_name or (seller.first_name if seller else str(escrow.seller_id))
        
        text = f"""
⚠️ *אישור שחרור כספים*

האם אתה בטוח שברצונך לשחרר:
💰 {format_price(escrow.net_seller_amount)}

למוכר: {seller_name}
"""
        
        keyboard = Keyboards.escrow_confirm_action_keyboard(escrow_id, "release")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """החזר כספים לקונה - אישור"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_refund_", "")
        escrow = await EscrowService.get_escrow_by_id(ObjectId(escrow_id))
        
        if not escrow:
            await query.edit_message_text("❌ עסקת Escrow לא נמצאה")
            return
        
        buyer = await UserService.get_user(escrow.buyer_id)
        buyer_name = buyer.first_name if buyer else str(escrow.buyer_id)
        
        text = f"""
⚠️ *אישור החזר כספים*

האם אתה בטוח שברצונך להחזיר:
💰 {format_price(escrow.total_buyer_paid)}

לקונה: {buyer_name}
"""
        
        keyboard = Keyboards.escrow_confirm_action_keyboard(escrow_id, "refund")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def escrow_confirm_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור שחרור כספים למוכר"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_confirm_release_", "")
        admin_id = update.effective_user.id
        
        escrow = await EscrowService.get_escrow_by_id(ObjectId(escrow_id))
        if not escrow:
            await query.edit_message_text("❌ עסקת Escrow לא נמצאה")
            return
        
        success = await EscrowService.release_to_seller(
            order_id=escrow.order_id,
            admin_id=admin_id,
            notes=f"שוחרר ידנית ע\"י אדמין {admin_id}"
        )
        
        if success:
            # שליחת הודעה למוכר
            try:
                await context.bot.send_message(
                    escrow.seller_id,
                    f"💰 *התקבלו כספים!*\n\n"
                    f"סכום: {format_price(escrow.net_seller_amount)}\n"
                    f"הכספים שוחררו לחשבונך.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ שוחררו {format_price(escrow.net_seller_amount)} למוכר!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                "❌ השחרור נכשל",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"escrow_view_{escrow_id}")
                ]])
            )

    @staticmethod
    async def escrow_confirm_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור החזר כספים לקונה"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_confirm_refund_", "")
        admin_id = update.effective_user.id
        
        escrow = await EscrowService.get_escrow_by_id(ObjectId(escrow_id))
        if not escrow:
            await query.edit_message_text("❌ עסקת Escrow לא נמצאה")
            return
        
        success = await EscrowService.refund_to_buyer(
            order_id=escrow.order_id,
            admin_id=admin_id,
            notes=f"הוחזר ידנית ע\"י אדמין {admin_id}"
        )
        
        if success:
            # עדכון סטטוס ההזמנה
            await OrderService.refund_order(escrow.order_id, admin_id, "החזר כספים מ-Escrow")
            
            # שליחת הודעה לקונה
            try:
                await context.bot.send_message(
                    escrow.buyer_id,
                    f"↩️ *התקבל החזר כספים!*\n\n"
                    f"סכום: {format_price(escrow.total_buyer_paid)}\n"
                    f"הכספים הוחזרו לחשבונך.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ הוחזרו {format_price(escrow.total_buyer_paid)} לקונה!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                "❌ ההחזר נכשל",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"escrow_view_{escrow_id}")
                ]])
            )

    @staticmethod
    async def escrow_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סטטיסטיקות Escrow מפורטות"""
        query = update.callback_query
        await query.answer()
        
        stats = await EscrowService.get_escrow_stats()
        
        text = f"""
📊 *סטטיסטיקות Escrow מפורטות*

💰 *יתרה נוכחית:* {format_price(stats.get('escrow_balance', 0))}

📈 *סטטוס עסקאות:*
⏳ מוחזקות: {stats.get('total_held', 0)}
⚖️ במחלוקת: {stats.get('total_disputed', 0)}
✅ שוחררו למוכרים: {stats.get('total_released', 0)}
↩️ הוחזרו לקונים: {stats.get('total_refunded', 0)}

⚡ *פעילות ב-24 שעות:*
📥 נכנסו ל-Escrow: {stats.get('recent_24h_held', 0)}
📤 שוחררו מ-Escrow: {stats.get('recent_24h_released', 0)}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    @staticmethod
    async def escrow_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דוח התאמה יומי"""
        query = update.callback_query
        await query.answer()
        
        report = await EscrowService.get_daily_reconciliation_report()
        
        text = f"""
📋 *דוח התאמה יומי - {report.get('date', 'N/A')}*

📥 *כניסות:*
  • סכום: {format_price(report.get('funds_in', {}).get('total', 0))}
  • מספר עסקאות: {report.get('funds_in', {}).get('count', 0)}

📤 *יציאות - שחרור למוכרים:*
  • סכום: {format_price(report.get('funds_released', {}).get('total', 0))}
  • מספר עסקאות: {report.get('funds_released', {}).get('count', 0)}

↩️ *יציאות - החזרים לקונים:*
  • סכום: {format_price(report.get('funds_refunded', {}).get('total', 0))}
  • מספר עסקאות: {report.get('funds_refunded', {}).get('count', 0)}

📊 *סיכום:*
  • סה"כ יציאות: {format_price(report.get('total_out', 0))}
  • שינוי נטו: {format_price(report.get('net_change', 0))}
  
💰 *יתרה נוכחית:* {format_price(report.get('current_balance', 0))}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    @staticmethod
    async def escrow_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת לוגים של עסקת Escrow"""
        query = update.callback_query
        await query.answer()
        
        escrow_id = query.data.replace("escrow_logs_", "")
        logs = await EscrowService.get_escrow_logs(ObjectId(escrow_id), limit=20)
        
        if not logs:
            await query.edit_message_text(
                "📋 אין לוגים לעסקה זו",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data=f"escrow_view_{escrow_id}")
                ]])
            )
            return
        
        text = f"📋 *לוג פעולות Escrow*\n\n"
        
        action_names = {
            "hold": "⏳ הקפאה",
            "release": "✅ שחרור אוטומטי",
            "admin_release": "✅ שחרור ידני",
            "refund": "↩️ החזר אוטומטי",
            "admin_refund": "↩️ החזר ידני",
            "dispute": "⚖️ מחלוקת"
        }
        
        for log in logs:
            action = action_names.get(log.action, log.action)
            date = log.created_at.strftime("%d/%m %H:%M") if log.created_at else "N/A"
            
            text += f"{action} | {format_price(log.amount)} | {date}\n"
            if log.notes:
                text += f"   📝 {log.notes[:30]}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data=f"escrow_view_{escrow_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
