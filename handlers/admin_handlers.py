"""
Handlers לאדמינים - ניהול המערכת
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
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
        
        if not await UserService.is_admin(user_id):
            await update.message.reply_text("❌ אין לך הרשאות אדמין.")
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
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
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
        
        # TODO: יצירת מערכת pending sellers
        # לעת עתה נציג מוכרים שצריכים אישור
        users = await database.get_users_collection()
        pending = await users.find({
            "role": {"$in": ["seller_verified", "seller_unverified"]},
            "approved": {"$ne": True}  # שדה שיש להוסיף
        }).to_list(10)
        
        if not pending:
            await query.edit_message_text(
                "✅ אין בקשות ממתינות.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        text = "👥 *בקשות רישום מוכרים:*\n\n"
        
        items = []
        for seller_data in pending:
            from models import User
            seller = User.from_dict(seller_data)
            verified = "✅ מאומת" if seller.is_verified else "📝 רגיל"
            items.append((
                f"{seller.business_name or seller.first_name} - {verified}",
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
        
        text = f"""
👤 *פרטי בקשת מוכר*

שם עסק: {seller.business_name}
טלפון: {seller.phone}
{"ת.ז: " + seller.id_number if seller.id_number else ""}

סוג: {verified_str}
Telegram: @{seller.username or 'לא זמין'}
User ID: `{seller.user_id}`

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
        
        # עדכון סטטוס
        users = await database.get_users_collection()
        result = await users.update_one(
            {"user_id": seller_id},
            {"$set": {"approved": True}}
        )
        
        if result.modified_count > 0:
            # שליחת הודעה למוכר
            try:
                await context.bot.send_message(
                    seller_id,
                    "🎉 *מזל טוב!*\n\nבקשתך לרישום כמוכר אושרה!\n"
                    "כעת תוכל להתחיל להעלות קופונים.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await query.edit_message_text(
                "✅ המוכר אושר בהצלחה!",
                reply_markup=Keyboards.back_button()
            )
        else:
            await query.edit_message_text("❌ האישור נכשל.")
    
    @staticmethod
    async def reject_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דחיית מוכר"""
        query = update.callback_query
        await query.answer()
        
        seller_id = int(query.data.replace("reject_seller_", ""))
        
        # מחיקת בקשה
        users = await database.get_users_collection()
        result = await users.update_one(
            {"user_id": seller_id},
            {"$set": {"role": "buyer", "business_name": None, "phone": None, "id_number": None}}
        )
        
        if result.modified_count > 0:
            try:
                await context.bot.send_message(
                    seller_id,
                    "❌ בקשתך לרישום כמוכר נדחתה.\n"
                    "לפרטים נוספים, צור קשר עם התמיכה."
                )
            except:
                pass
            
            await query.edit_message_text(
                "✅ הבקשה נדחתה.",
                reply_markup=Keyboards.back_button()
            )
        else:
            await query.edit_message_text("❌ הדחייה נכשלה.")
    
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
