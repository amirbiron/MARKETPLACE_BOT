"""
Handlers למוכרים - העלאת קופונים ומכירות
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime, timedelta
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from keyboards import Keyboards
from utils import format_price, format_datetime
from config import Config
import database
import logging

logger = logging.getLogger(__name__)

# States
(UPLOAD_TITLE, UPLOAD_CATEGORY, UPLOAD_ORIGINAL_PRICE, UPLOAD_SALE_PRICE,
 UPLOAD_DESCRIPTION, UPLOAD_CODE, UPLOAD_EXPIRY, 
 BUSINESS_NAME, PHONE, ID_NUMBER) = range(10)


class SellerHandlers:
    """Handlers למוכרים"""
    
    @staticmethod
    async def start_seller_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת רישום כמוכר"""
        user_id = update.effective_user.id
        user = await UserService.get_user(user_id)
        
        if await UserService.is_seller(user_id):
            await update.message.reply_text("✅ אתה כבר רשום כמוכר!")
            return ConversationHandler.END
        
        text = """
👨‍💼 *רישום כמוכר*

ברוך הבא להליך רישום המוכרים!

📝 בחר סוג רישום:

🔹 *מוכר מאומת* (עם ת.ז)
   • עמלה: 3%
   • ללא הגבלת קופונים
   • סמל "מאומת" בפרופיל

🔹 *מוכר רגיל* (ללא ת.ז)
   • עמלה: 5%
   • עד 10 קופונים ביום
   • ללא סימון מיוחד
"""
        
        keyboard = Keyboards.back_button()  # TODO: add registration type buttons
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
        await update.message.reply_text("📝 שלח את שם העסק שלך:")
        return BUSINESS_NAME
    
    @staticmethod
    async def receive_business_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת שם עסק"""
        context.user_data['business_name'] = update.message.text
        
        await update.message.reply_text("📞 שלח מספר טלפון WhatsApp (לדוגמה: 0501234567):")
        return PHONE
    
    @staticmethod
    async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת טלפון"""
        phone = update.message.text.strip()
        
        # וולידציה בסיסית
        if not phone.isdigit() or len(phone) < 9:
            await update.message.reply_text("❌ מספר טלפון לא תקין. אנא נסה שוב:")
            return PHONE
        
        context.user_data['phone'] = phone
        
        await update.message.reply_text(
            "🆔 האם תרצה להירשם כמוכר מאומת?\n\n"
            "שלח תעודת זהות (9 ספרות) או /skip לדילוג:"
        )
        return ID_NUMBER
    
    @staticmethod
    async def receive_id_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת ת.ז"""
        if update.message.text == "/skip":
            id_number = None
        else:
            id_number = update.message.text.strip()
            if not id_number.isdigit() or len(id_number) != 9:
                await update.message.reply_text("❌ ת.ז לא תקינה. נסה שוב או /skip:")
                return ID_NUMBER
        
        # עדכון המשתמש
        success = await UserService.update_seller_info(
            user_id=update.effective_user.id,
            business_name=context.user_data['business_name'],
            phone=context.user_data['phone'],
            id_number=id_number
        )
        
        if success:
            verified_str = "מאומת ✅" if id_number else "רגיל"
            commission = "3%" if id_number else "5%"
            
            text = f"""
🎉 *הרישום הושלם!*

סוג מוכר: {verified_str}
עמלה: {commission}

✅ הבקשה שלך נשלחה לאישור אדמינים.
תקבל הודעה כשהבקשה תאושר.

בינתיים, תוכל להמשיך להשתמש במערכת כקונה.
"""
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ הרישום נכשל. אנא נסה שוב מאוחר יותר.")
        
        return ConversationHandler.END
    
    @staticmethod
    async def start_coupon_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת העלאת קופון"""
        user_id = update.effective_user.id
        
        if not await UserService.is_seller(user_id):
            await update.message.reply_text("❌ אתה צריך להירשם כמוכר קודם!")
            return ConversationHandler.END
        
        # בדיקת הגבלה יומית
        is_verified = await UserService.is_verified_seller(user_id)
        if not is_verified:
            # בדיקה כמה קופונים העלה היום
            coupons = await database.get_coupons_collection()
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count = await coupons.count_documents({
                "seller_id": user_id,
                "created_at": {"$gte": today_start}
            })
            
            if count >= Config.DAILY_COUPON_LIMIT_UNVERIFIED:
                await update.message.reply_text(
                    f"❌ הגעת למגבלה היומית של {Config.DAILY_COUPON_LIMIT_UNVERIFIED} קופונים.\n"
                    f"נסה שוב מחר או הירשם כמוכר מאומת."
                )
                return ConversationHandler.END
        
        text = """
📦 *העלאת קופון חדש*

בוא נתחיל! שלח את הפרטים הבאים:

📝 1. כותרת הקופון (לדוגמה: ארוחה זוגית במסעדת איטלקיה)
"""
        
        await update.message.reply_text(text, parse_mode="Markdown")
        return UPLOAD_TITLE
    
    @staticmethod
    async def receive_coupon_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת כותרת"""
        context.user_data['coupon_title'] = update.message.text
        
        # הצגת קטגוריות
        categories_text = "\n".join([f"{i+1}. {cat}" for i, cat in enumerate(CouponService.CATEGORIES)])
        
        text = f"""
📁 *בחר קטגוריה*

{categories_text}

שלח מספר (1-{len(CouponService.CATEGORIES)}):
"""
        
        await update.message.reply_text(text, parse_mode="Markdown")
        return UPLOAD_CATEGORY
    
    @staticmethod
    async def receive_coupon_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת קטגוריה"""
        try:
            cat_num = int(update.message.text) - 1
            if 0 <= cat_num < len(CouponService.CATEGORIES):
                context.user_data['coupon_category'] = CouponService.CATEGORIES[cat_num]
            else:
                raise ValueError()
        except:
            await update.message.reply_text("❌ מספר לא תקין. נסה שוב:")
            return UPLOAD_CATEGORY
        
        await update.message.reply_text("💰 שלח מחיר מקורי (לדוגמה: 250):")
        return UPLOAD_ORIGINAL_PRICE
    
    @staticmethod
    async def receive_original_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת מחיר מקורי"""
        try:
            price = float(update.message.text)
            if price <= 0:
                raise ValueError()
            context.user_data['original_price'] = price
        except:
            await update.message.reply_text("❌ מחיר לא תקין. נסה שוב:")
            return UPLOAD_ORIGINAL_PRICE
        
        await update.message.reply_text("💵 שלח מחיר מכירה (לדוגמה: 150):")
        return UPLOAD_SALE_PRICE
    
    @staticmethod
    async def receive_sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת מחיר מכירה"""
        try:
            price = float(update.message.text)
            if price <= 0 or price >= context.user_data['original_price']:
                await update.message.reply_text("❌ מחיר המכירה חייב להיות נמוך מהמחיר המקורי. נסה שוב:")
                return UPLOAD_SALE_PRICE
            context.user_data['sale_price'] = price
        except:
            await update.message.reply_text("❌ מחיר לא תקין. נסה שוב:")
            return UPLOAD_SALE_PRICE
        
        await update.message.reply_text("📝 שלח תיאור (או /skip לדילוג):")
        return UPLOAD_DESCRIPTION
    
    @staticmethod
    async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת תיאור"""
        if update.message.text == "/skip":
            context.user_data['description'] = None
        else:
            context.user_data['description'] = update.message.text
        
        await update.message.reply_text("🔐 שלח קוד דיגיטלי/ברקוד של הקופון (או /skip):")
        return UPLOAD_CODE
    
    @staticmethod
    async def receive_digital_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת קוד דיגיטלי"""
        if update.message.text == "/skip":
            context.user_data['digital_code'] = None
        else:
            context.user_data['digital_code'] = update.message.text
        
        await update.message.reply_text(
            "📅 שלח תאריך תפוגה (DD/MM/YYYY) או /skip:\n"
            "(לדוגמה: 31/12/2026)"
        )
        return UPLOAD_EXPIRY
    
    @staticmethod
    async def receive_expiry_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת תפוגה וסיום"""
        expiry_date = None
        
        if update.message.text != "/skip":
            try:
                expiry_date = datetime.strptime(update.message.text, "%d/%m/%Y")
            except:
                await update.message.reply_text("❌ תאריך לא תקין. נסה שוב או /skip:")
                return UPLOAD_EXPIRY
        
        # יצירת הקופון
        coupon = await CouponService.create_coupon(
            seller_id=update.effective_user.id,
            title=context.user_data['coupon_title'],
            category=context.user_data['coupon_category'],
            original_price=context.user_data['original_price'],
            sale_price=context.user_data['sale_price'],
            description=context.user_data.get('description'),
            digital_code=context.user_data.get('digital_code'),
            expires_at=expiry_date
        )
        
        if coupon:
            text = f"""
✅ *הקופון הועלה בהצלחה!*

🎫 {coupon.title}
💰 מחיר: {format_price(coupon.sale_price)}
📁 קטגוריה: {coupon.category}

הקופון זמין כעת לקנייה במערכת.
"""
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ ההעלאה נכשלה. אנא נסה שוב.")
        
        return ConversationHandler.END
    
    @staticmethod
    async def show_my_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת המכירות שלי"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        user_id = update.effective_user.id
        query = update.callback_query
        
        if not await UserService.is_seller(user_id):
            error_text = "❌ אתה צריך להיות מוכר כדי לראות מכירות."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        orders = await OrderService.get_seller_orders(user_id)
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]]
        
        if not orders:
            text = "📊 *המכירות שלי*\n\nאין לך מכירות עדיין.\n\nהעלה קופונים והמתן לקונים!"
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        
        # חישוב סטטיסטיקות
        total_sales = len(orders)
        total_revenue = sum(o.price_paid - o.buyer_commission - o.seller_commission for o in orders)
        
        text = f"""
📊 *המכירות שלי*

📈 סה"כ מכירות: {total_sales}
💰 סה"כ הכנסות: {format_price(total_revenue)}

*עסקאות אחרונות:*
"""
        
        for order in orders[:10]:
            coupon = await CouponService.get_coupon(order.coupon_id)
            status = "✅" if order.status.value == "completed" else "⏳"
            net = order.price_paid - order.buyer_commission - order.seller_commission
            
            text += f"\n{status} {coupon.title if coupon else 'קופון'} | {format_price(net)} | {format_datetime(order.created_at)}"
        
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def show_seller_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סטטיסטיקות מוכר"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        user_id = update.effective_user.id
        query = update.callback_query
        
        if not await UserService.is_seller(user_id):
            error_text = "❌ פונקציה זמינה רק למוכרים."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        user = await UserService.get_user(user_id)
        coupons = await CouponService.get_seller_coupons(user_id)
        orders = await OrderService.get_seller_orders(user_id)
        
        active_coupons = sum(1 for c in coupons if c.status.value == "active")
        sold_coupons = sum(1 for c in coupons if c.status.value == "sold")
        
        total_revenue = sum(
            o.price_paid - o.buyer_commission - o.seller_commission 
            for o in orders if o.status.value in ["completed", "confirmed"]
        )
        
        # מכירות החודש
        this_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_sales = sum(1 for o in orders if o.created_at >= this_month_start)
        
        text = f"""
📈 *סטטיסטיקות המוכר*

👤 שם עסק: {user.business_name or 'לא מוגדר'}
⭐ דירוג: {user.rating_average:.1f} ({user.rating_count} ביקורות)

📦 קופונים:
  • פעילים: {active_coupons}
  • נמכרו: {sold_coupons}

💰 הכנסות:
  • סה"כ: {format_price(total_revenue)}
  • מכירות חודש זה: {monthly_sales}

💳 יתרה:
  • זמינה: {format_price(user.balance - user.frozen_balance)}
  • מוקפאת: {format_price(user.frozen_balance)}
  • סה"כ: {format_price(user.balance)}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]]
        
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def request_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בקשת משיכת כספים"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        user_id = update.effective_user.id
        query = update.callback_query
        
        if not await UserService.is_seller(user_id):
            error_text = "❌ משיכה זמינה רק למוכרים."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return ConversationHandler.END
        
        user = await UserService.get_user(user_id)
        available = user.balance - user.frozen_balance
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]]
        
        if available < Config.MIN_WITHDRAWAL_AMOUNT:
            text = f"""
❌ *לא ניתן למשוך כספים*

סכום מינימלי למשיכה: {format_price(Config.MIN_WITHDRAWAL_AMOUNT)}
יתרתך הזמינה: {format_price(available)}

חסר: {format_price(Config.MIN_WITHDRAWAL_AMOUNT - available)}
"""
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return ConversationHandler.END
        
        commission = available * Config.WITHDRAWAL_COMMISSION
        net = available - commission
        
        text = f"""
💸 *בקשת משיכת כספים*

💰 יתרה זמינה: {format_price(available)}
➖ עמלת משיכה (1%): {format_price(commission)}
✅ תקבל: {format_price(net)}

📝 הבקשה תישלח לאדמינים לאישור.
הכספים יועברו תוך 1-3 ימי עסקים.

לביצוע משיכה, השתמש בפקודה:
/withdraw
"""
        
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        return ConversationHandler.END
