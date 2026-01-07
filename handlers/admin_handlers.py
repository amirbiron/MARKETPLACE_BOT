"""
Handlers לאדמינים - ניהול המערכת
"""
from telegram import Update
from telegram.ext import ContextTypes
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from keyboards import Keyboards
from utils import format_price, format_datetime
from config import Config
import database
import logging

logger = logging.getLogger(__name__)


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
