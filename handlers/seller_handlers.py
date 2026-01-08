"""
Handlers למוכרים - העלאת קופונים ומכירות + דשבורד מתקדם
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime, timedelta
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from services.analytics_service import AnalyticsService
from services.report_service import ReportService
from keyboards import Keyboards
from utils import format_price, format_datetime
from config import Config
from bson import ObjectId
import database
import logging

logger = logging.getLogger(__name__)

# States
(UPLOAD_TITLE, UPLOAD_CATEGORY, UPLOAD_ORIGINAL_PRICE, UPLOAD_SALE_PRICE,
 UPLOAD_DESCRIPTION, UPLOAD_CODE, UPLOAD_EXPIRY, 
 BUSINESS_NAME, COMMERCIAL_NAME, PHONE, ID_NUMBER) = range(11)


class SellerHandlers:
    """Handlers למוכרים"""
    
    @staticmethod
    async def start_seller_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת רישום כמוכר"""
        user_id = update.effective_user.id
        user = await UserService.get_user(user_id)
        
        if await UserService.is_seller(user_id):
            # בדיקה אם ממתין לאישור
            if user and getattr(user, 'seller_status', None) == 'pending':
                await update.message.reply_text(
                    "⏳ *ממתין לאישור*\n\n"
                    "הבקשה שלך להירשם כמוכר כבר נשלחה וממתינה לאישור אדמינים.\n"
                    "תקבל הודעה כשהבקשה תאושר.",
                    parse_mode="Markdown"
                )
            else:
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
        
        keyboard = Keyboards.back_button()
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
        await update.message.reply_text("📝 שלח את שם העסק שלך (שם מלא/שם חברה):")
        return BUSINESS_NAME
    
    @staticmethod
    async def receive_business_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת שם עסק והמשך לטלפון (לפי ה-flow החדש)"""
        business_name = (update.message.text or "").strip()
        context.user_data["business_name"] = business_name

        # לפי הדרישה: אחרי שם העסק עוברים לבקשת טלפון (ללא שלב שם מסחרי)
        # נשמור גם commercial_name כברירת מחדל = שם העסק, כדי לשמור תאימות לתצוגות קיימות.
        context.user_data["commercial_name"] = business_name

        await update.message.reply_text("📞 שלח מספר טלפון WhatsApp (לדוגמה: 0501234567):")
        return PHONE
    
    @staticmethod
    async def receive_commercial_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת שם מסחרי"""
        commercial_name = update.message.text.strip()
        
        # וולידציה בסיסית
        if len(commercial_name) < 2:
            await update.message.reply_text("❌ שם מסחרי קצר מדי. אנא שלח שם בעל 2 תווים לפחות:")
            return COMMERCIAL_NAME
        
        if len(commercial_name) > 50:
            await update.message.reply_text("❌ שם מסחרי ארוך מדי. אנא שלח שם עד 50 תווים:")
            return COMMERCIAL_NAME
        
        context.user_data['commercial_name'] = commercial_name
        
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
        """קליטת ת.ז ושליחת בקשה לאישור"""
        from services.notification_service import NotificationService
        from config import Config
        
        if update.message.text == "/skip":
            id_number = None
        else:
            id_number = update.message.text.strip()
            if not id_number.isdigit() or len(id_number) != 9:
                await update.message.reply_text("❌ ת.ז לא תקינה. נסה שוב או /skip:")
                return ID_NUMBER
        
        user = update.effective_user
        commercial_name = context.user_data.get('commercial_name', context.user_data['business_name'])
        
        # עדכון המשתמש עם סטטוס ממתין לאישור
        success = await UserService.update_seller_info(
            user_id=user.id,
            business_name=context.user_data['business_name'],
            commercial_name=commercial_name,
            phone=context.user_data['phone'],
            id_number=id_number,
            seller_status='pending'  # סטטוס ממתין לאישור
        )
        
        if success:
            verified_str = "מאומת ✅" if id_number else "רגיל"
            commission = "3%" if id_number else "5%"
            
            # הודעה למוכר
            text = f"""
🎉 *תודה על הרישום!*

🏷️ שם מסחרי: {commercial_name}
סוג מוכר: {verified_str}
עמלה: {commission}

✅ הבקשה שלך נשלחה לאישור אדמינים.
תקבל הודעה כשהבקשה תאושר.
"""
            await update.message.reply_text(text, parse_mode="Markdown")
            
            # שליחת הודעה לאדמינים עם כפתורי אישור/דחייה
            admin_text = f"""
👤 *בקשה חדשה לרישום כמוכר*

🆔 ID: `{user.id}`
👤 שם: {user.first_name or 'לא זמין'}
📛 שם משתמש: @{user.username or 'ללא'}

📋 *פרטי הרישום:*
🏢 שם עסק: {context.user_data['business_name']}
🏷️ שם מסחרי: {commercial_name}
📞 טלפון: {context.user_data['phone']}
🆔 ת.ז: {'✅ סופק' if id_number else '❌ לא סופק'}
📊 סוג: {verified_str}
💰 עמלה: {commission}
"""
            
            admin_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ אשר מוכר", callback_data=f"approve_seller_{user.id}"),
                    InlineKeyboardButton("❌ דחה בקשה", callback_data=f"reject_seller_{user.id}")
                ]
            ])
            
            # שליחה לכל האדמינים
            for admin_id in Config.ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
        else:
            await update.message.reply_text("❌ הרישום נכשל. אנא נסה שוב מאוחר יותר.")
        
        # ניקוי נתוני הקונטקסט
        context.user_data.pop('business_name', None)
        context.user_data.pop('commercial_name', None)
        context.user_data.pop('phone', None)
        
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
    
    # ==================== Advanced Dashboard Handlers ====================
    
    @staticmethod
    async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת דשבורד מתקדם"""
        user_id = update.effective_user.id
        query = update.callback_query
        
        if query:
            await query.answer()
        
        if not await UserService.is_seller(user_id):
            error_text = "❌ הדשבורד זמין רק למוכרים."
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        # Get quick summary
        summary = await AnalyticsService.get_dashboard_summary(user_id)
        month_stats = summary.get("month", {})
        comparison = await AnalyticsService.get_period_comparison(user_id, "month")
        
        # Build text
        sales_change = comparison.get("change", {}).get("sales", 0)
        revenue_change = comparison.get("change", {}).get("revenue", 0)
        sales_arrow = "📈" if sales_change >= 0 else "📉"
        revenue_arrow = "📈" if revenue_change >= 0 else "📉"
        
        text = f"""
📊 *דשבורד מתקדם*

💰 *סיכום החודש:*
• מכירות: {month_stats.get('total_sales', 0)} {sales_arrow} ({sales_change:+.1f}%)
• הכנסות נטו: {month_stats.get('total_revenue', 0):.2f}₪ {revenue_arrow} ({revenue_change:+.1f}%)
• ממוצע למכירה: {month_stats.get('avg_sale_price', 0):.2f}₪

📈 *המרה:*
• צפיות: {summary.get('conversion', {}).get('total_views', 0)}
• אחוז המרה: {summary.get('conversion', {}).get('conversion_rate', 0):.1f}%

⚖️ *מחלוקות:*
• אחוז מחלוקות: {summary.get('disputes', {}).get('dispute_rate', 0):.1f}%

בחר קטגוריה לפרטים נוספים:
"""
        
        keyboard = Keyboards.seller_dashboard_keyboard()
        
        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_advanced_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סטטיסטיקות מתקדמות"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        # Get period from context or default
        period = context.user_data.get("stats_period", "month")
        
        stats = await AnalyticsService.get_sales_by_period(user_id, period)
        comparison = await AnalyticsService.get_period_comparison(user_id, period)
        
        period_names = {
            "day": "היום",
            "week": "השבוע",
            "month": "החודש",
            "year": "השנה"
        }
        
        text = f"""
📊 *סטטיסטיקות מתקדמות - {period_names.get(period, period)}*

💰 *הכנסות:*
• ברוטו: {stats.get('gross_revenue', 0):.2f}₪
• עמלות: {stats.get('total_commission', 0):.2f}₪
• נטו: {stats.get('total_revenue', 0):.2f}₪

📈 *מכירות:*
• סה"כ: {stats.get('total_sales', 0)}
• ממוצע ליום: {stats.get('avg_sales_per_day', 0):.1f}
• ממוצע למכירה: {stats.get('avg_sale_price', 0):.2f}₪

{Keyboards.stats_comparison_display(comparison)}

בחר תקופה:
"""
        
        keyboard = Keyboards.dashboard_period_keyboard("stats")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def change_stats_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שינוי תקופת סטטיסטיקות"""
        query = update.callback_query
        await query.answer()
        
        # Extract period from callback data (stats_period_day, stats_period_week, etc.)
        period = query.data.replace("stats_period_", "")
        context.user_data["stats_period"] = period
        
        # Call show_advanced_stats to refresh
        return await SellerHandlers.show_advanced_stats(update, context)
    
    @staticmethod
    async def show_sales_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """גרף מכירות"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        period = context.user_data.get("graph_period", "month")
        graph_data = await AnalyticsService.get_sales_graph_data(user_id, period)
        
        text = Keyboards.graph_display(graph_data, "מכירות")
        text += "\n\nבחר תקופה:"
        
        keyboard = Keyboards.dashboard_period_keyboard("graph")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def change_graph_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שינוי תקופת גרף"""
        query = update.callback_query
        await query.answer()
        
        period = query.data.replace("graph_period_", "")
        context.user_data["graph_period"] = period
        
        return await SellerHandlers.show_sales_graph(update, context)
    
    @staticmethod
    async def show_top_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מוצרים מובילים"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        top_products = await AnalyticsService.get_top_selling_products(user_id, 10)
        
        text = "🏆 *מוצרים מובילים*\n\n"
        
        if not top_products:
            text += "אין מוצרים להצגה עדיין."
        else:
            for i, product in enumerate(top_products, 1):
                title = product.get("title", "לא זמין")[:30]
                text += f"{i}. *{title}*\n"
                text += f"   📊 {product.get('sales', 0)} מכירות | 💰 {product.get('revenue', 0):.2f}₪\n"
                text += f"   📁 {product.get('category', 'לא זמין')}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדשבורד", callback_data="seller_dashboard")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def show_category_breakdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פילוח לפי קטגוריה"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        categories = await AnalyticsService.get_sales_by_category(user_id)
        
        text = "📁 *פילוח לפי קטגוריה*\n\n"
        
        if not categories:
            text += "אין נתונים להצגה עדיין."
        else:
            total_sales = sum(c.get("sales", 0) for c in categories)
            
            for cat in categories:
                cat_name = cat.get("category", "לא זמין")
                sales = cat.get("sales", 0)
                revenue = cat.get("revenue", 0)
                percentage = (sales / total_sales * 100) if total_sales > 0 else 0
                
                # Progress bar
                bar_length = int(percentage / 10)
                bar = "█" * bar_length + "░" * (10 - bar_length)
                
                text += f"*{cat_name}*\n"
                text += f"[{bar}] {percentage:.1f}%\n"
                text += f"📊 {sales} מכירות | 💰 {revenue:.2f}₪\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדשבורד", callback_data="seller_dashboard")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def show_peak_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """זמני שיא"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        peak_data = await AnalyticsService.get_peak_sales_times(user_id)
        
        text = Keyboards.peak_times_display(peak_data)
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדשבורד", callback_data="seller_dashboard")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    # ==================== Reports Handlers ====================
    
    @staticmethod
    async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט דוחות"""
        query = update.callback_query
        await query.answer()
        
        text = """
📋 *דוחות*

בחר את סוג הדוח שברצונך להפיק:

📊 *דוח מכירות חודשי* - סיכום מלא של החודש
💰 *דוח עמלות* - פירוט עמלות ששולמו
⚖️ *דוח מחלוקות* - סטטוס מחלוקות

📁 *ייצוא CSV* - הורדת נתונים לאקסל
"""
        
        keyboard = Keyboards.dashboard_reports_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def generate_monthly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפקת דוח חודשי"""
        query = update.callback_query
        await query.answer("⏳ מכין דוח...")
        user_id = update.effective_user.id
        
        report_text = await ReportService.generate_monthly_report_text(user_id)
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדוחות", callback_data="dashboard_reports")]]
        await query.edit_message_text(report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def generate_commission_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפקת דוח עמלות"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        report = await AnalyticsService.get_commission_report(user_id, "month")
        
        text = f"""
💰 *דוח עמלות - החודש*

📊 *סיכום:*
• הזמנות: {report.get('order_count', 0)}
• הכנסות ברוטו: {report.get('gross_revenue', 0):.2f}₪
• עמלות ששולמו: {report.get('seller_commission', 0):.2f}₪
• הכנסות נטו: {report.get('net_revenue', 0):.2f}₪

📈 *ממוצעים:*
• עמלה ממוצעת להזמנה: {report.get('avg_commission_per_order', 0):.2f}₪

💡 *טיפ:* מוכרים מאומתים משלמים עמלה נמוכה יותר (3% במקום 5%)
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדוחות", callback_data="dashboard_reports")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def generate_disputes_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפקת דוח מחלוקות"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        report = await AnalyticsService.get_disputes_report(user_id)
        
        # Warning icon based on dispute rate
        rate = report.get('dispute_rate', 0)
        if rate > 20:
            status_icon = "🔴"
            status_text = "גבוה - דורש תשומת לב!"
        elif rate > 10:
            status_icon = "🟡"
            status_text = "בינוני"
        else:
            status_icon = "🟢"
            status_text = "תקין"
        
        text = f"""
⚖️ *דוח מחלוקות*

📊 *סיכום כללי:*
• סה"כ הזמנות: {report.get('total_orders', 0)}
• מחלוקות: {report.get('disputed_orders', 0)}
• אחוז מחלוקות: {rate:.1f}% {status_icon}
• סטטוס: {status_text}

📋 *פירוט:*
• מחלוקות פתוחות: {report.get('open_disputes', 0)}
• מחלוקות שנפתרו: {report.get('resolved_disputes', 0)}
• החזרים שניתנו: {report.get('refunds_given', 0)}

💡 *טיפ:* שמרו על אחוז מחלוקות נמוך לניקוד אמינות גבוה
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה לדוחות", callback_data="dashboard_reports")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def export_sales_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ייצוא מכירות ל-CSV"""
        query = update.callback_query
        await query.answer("⏳ מכין קובץ...")
        user_id = update.effective_user.id
        
        csv_file = await ReportService.generate_sales_csv(user_id, "month")
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_file,
            filename=f"sales_report_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            caption="📊 דוח מכירות - CSV"
        )
    
    @staticmethod
    async def export_products_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ייצוא מוצרים ל-CSV"""
        query = update.callback_query
        await query.answer("⏳ מכין קובץ...")
        user_id = update.effective_user.id
        
        csv_file = await ReportService.generate_products_csv(user_id)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_file,
            filename=f"products_report_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            caption="📦 דוח מוצרים - CSV"
        )
    
    @staticmethod
    async def export_all_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ייצוא כל הנתונים ל-CSV"""
        query = update.callback_query
        await query.answer("⏳ מכין קובץ...")
        user_id = update.effective_user.id
        
        csv_file = await ReportService.generate_full_export_csv(user_id)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_file,
            filename=f"full_export_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            caption="📁 ייצוא מלא של כל הנתונים - CSV"
        )
    
    # ==================== Product Management Handlers ====================
    
    @staticmethod
    async def show_products_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט ניהול מוצרים"""
        query = update.callback_query
        await query.answer()
        
        text = """
📦 *ניהול מוצרים מתקדם*

בחר פעולה:

📋 *כל המוצרים שלי* - צפייה ובחירת מוצרים
✏️ *עריכה מרובה* - עריכת מספר מוצרים בבת אחת
📋 *שכפול קופון* - יצירת עותק של קופון קיים
⏰ *תזמון פרסום* - הגדרת זמן פרסום עתידי
💰 *עדכון מחיר מרובה* - שינוי מחירים בבת אחת
"""
        
        keyboard = Keyboards.dashboard_products_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_products_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """רשימת מוצרים"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        # Get page from context
        page = context.user_data.get("products_page", 0)
        selected_ids = context.user_data.get("selected_products", [])
        
        coupons = await CouponService.get_seller_coupons(user_id)
        
        # Filter only active coupons
        active_coupons = [c for c in coupons if c.status.value == "active"]
        
        if not active_coupons:
            text = "📦 *המוצרים שלי*\n\nאין לך מוצרים פעילים.\n\nהשתמש ב /upload להעלאת קופון חדש."
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        
        # Pagination
        items_per_page = Config.ITEMS_PER_PAGE
        total_pages = (len(active_coupons) + items_per_page - 1) // items_per_page
        start = page * items_per_page
        end = start + items_per_page
        page_coupons = active_coupons[start:end]
        
        text = f"""
📦 *המוצרים שלי* ({len(active_coupons)} פעילים)

{'✅ נבחרו: ' + str(len(selected_ids)) + ' מוצרים' if selected_ids else 'לחץ על מוצר לבחירה'}

בחר מוצרים לפעולות:
"""
        
        products = [(str(c._id), c.title) for c in page_coupons]
        keyboard = Keyboards.products_list_keyboard(products, page, total_pages, selected_ids)
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת/ביטול בחירת מוצר"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = query.data.replace("product_select_", "")
        
        selected = context.user_data.get("selected_products", [])
        
        if coupon_id in selected:
            selected.remove(coupon_id)
        else:
            if len(selected) < Config.BULK_EDIT_MAX_ITEMS:
                selected.append(coupon_id)
            else:
                await query.answer(f"❌ מקסימום {Config.BULK_EDIT_MAX_ITEMS} מוצרים לבחירה", show_alert=True)
                return
        
        context.user_data["selected_products"] = selected
        
        # Refresh list
        return await SellerHandlers.show_products_list(update, context)
    
    @staticmethod
    async def clear_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניקוי בחירת מוצרים"""
        query = update.callback_query
        await query.answer()
        
        context.user_data["selected_products"] = []
        
        return await SellerHandlers.show_products_list(update, context)
    
    @staticmethod
    async def products_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דפדוף ברשימת מוצרים"""
        query = update.callback_query
        await query.answer()
        
        page = int(query.data.replace("products_page_", ""))
        context.user_data["products_page"] = page
        
        return await SellerHandlers.show_products_list(update, context)
    
    @staticmethod
    async def show_duplicate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט שכפול קופון"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        coupons = await CouponService.get_seller_coupons(user_id)
        active_coupons = [c for c in coupons if c.status.value in ["active", "sold"]]
        
        if not active_coupons:
            text = "📋 *שכפול קופון*\n\nאין לך קופונים לשכפול."
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        
        text = "📋 *שכפול קופון*\n\nבחר קופון לשכפול:"
        
        keyboard = []
        for c in active_coupons[:10]:
            title = c.title[:25] + "..." if len(c.title) > 25 else c.title
            keyboard.append([InlineKeyboardButton(
                f"📋 {title}",
                callback_data=f"product_duplicate_{c._id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def duplicate_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """שכפול קופון"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        coupon_id = query.data.replace("product_duplicate_", "")
        
        # Get original coupon
        coupon = await CouponService.get_coupon(ObjectId(coupon_id))
        
        if not coupon or coupon.seller_id != user_id:
            await query.answer("❌ קופון לא נמצא", show_alert=True)
            return
        
        # Create duplicate
        new_coupon = await CouponService.create_coupon(
            seller_id=user_id,
            title=f"{coupon.title} (עותק)",
            category=coupon.category,
            original_price=coupon.original_price,
            sale_price=coupon.sale_price,
            description=coupon.description,
            digital_code=None,  # Don't copy digital code
            expires_at=coupon.expires_at
        )
        
        if new_coupon:
            text = f"""
✅ *הקופון שוכפל בהצלחה!*

📋 קופון חדש: {new_coupon.title}
💰 מחיר: {format_price(new_coupon.sale_price)}

💡 הקופון החדש פורסם כפעיל.
אל תשכח להוסיף קוד דיגיטלי אם נדרש!
"""
        else:
            text = "❌ השכפול נכשל. אנא נסה שוב."
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def show_bulk_price_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """תפריט עדכון מחיר מרובה"""
        query = update.callback_query
        await query.answer()
        
        selected = context.user_data.get("selected_products", [])
        
        if not selected:
            text = """
💰 *עדכון מחיר מרובה*

❌ לא נבחרו מוצרים!

לחץ על "כל המוצרים שלי" ובחר מוצרים לעדכון.
"""
            keyboard = [
                [InlineKeyboardButton("📋 בחר מוצרים", callback_data="products_list")],
                [InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]
            ]
        else:
            text = f"""
💰 *עדכון מחיר מרובה*

✅ נבחרו {len(selected)} מוצרים

בחר פעולה:
"""
            keyboard = Keyboards.bulk_price_update_keyboard()
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    @staticmethod
    async def apply_bulk_price_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """החלת שינוי מחיר מרובה"""
        query = update.callback_query
        await query.answer("⏳ מעדכן מחירים...")
        user_id = update.effective_user.id
        
        selected = context.user_data.get("selected_products", [])
        
        if not selected:
            await query.answer("❌ לא נבחרו מוצרים", show_alert=True)
            return
        
        # Parse action
        action = query.data.replace("bulk_price_", "")
        
        coupons = await database.get_coupons_collection()
        updated = 0
        
        for coupon_id in selected:
            coupon = await CouponService.get_coupon(ObjectId(coupon_id))
            if not coupon or coupon.seller_id != user_id:
                continue
            
            new_price = coupon.sale_price
            
            if action == "discount_5":
                new_price = coupon.sale_price * 0.95
            elif action == "discount_10":
                new_price = coupon.sale_price * 0.90
            elif action == "discount_15":
                new_price = coupon.sale_price * 0.85
            elif action == "increase_5":
                new_price = coupon.sale_price * 1.05
            elif action == "increase_10":
                new_price = coupon.sale_price * 1.10
            
            # Ensure price is still less than original
            if new_price < coupon.original_price:
                await coupons.update_one(
                    {"_id": ObjectId(coupon_id)},
                    {"$set": {"sale_price": round(new_price, 2)}}
                )
                updated += 1
        
        # Clear selection
        context.user_data["selected_products"] = []
        
        text = f"""
✅ *עדכון מחירים הושלם!*

עודכנו {updated} מוצרים.
"""
        
        keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    # ==================== Alert Settings Handlers ====================
    
    @staticmethod
    async def show_alert_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הגדרות התראות"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        # Get or create settings
        settings_col = await database.get_seller_alert_settings_collection()
        settings = await settings_col.find_one({"seller_id": user_id})
        
        if not settings:
            settings = {
                "sales_threshold_enabled": False,
                "sales_threshold_amount": 10,
                "negative_review_alert": True,
                "daily_summary": False,
                "weekly_summary": False,
                "dispute_alert": True
            }
        
        text = """
🔔 *הגדרות התראות*

הפעל/כבה התראות לפי העדפותיך:
"""
        
        keyboard = Keyboards.dashboard_alerts_keyboard(settings)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הפעלה/כיבוי התראה"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        # Get setting to toggle
        setting = query.data.replace("alert_toggle_", "")
        
        setting_map = {
            "sales": "sales_threshold_enabled",
            "review": "negative_review_alert",
            "daily": "daily_summary",
            "weekly": "weekly_summary",
            "dispute": "dispute_alert"
        }
        
        db_field = setting_map.get(setting)
        if not db_field:
            return
        
        settings_col = await database.get_seller_alert_settings_collection()
        
        # Get current value
        current = await settings_col.find_one({"seller_id": user_id})
        current_value = current.get(db_field, False) if current else False
        
        # Toggle
        await settings_col.update_one(
            {"seller_id": user_id},
            {
                "$set": {
                    db_field: not current_value,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Refresh settings view
        return await SellerHandlers.show_alert_settings(update, context)
    
    # ==================== Scheduled Coupons Handlers ====================
    
    @staticmethod
    async def show_scheduled_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """רשימת קופונים מתוזמנים"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        scheduled_col = await database.get_scheduled_coupons_collection()
        cursor = scheduled_col.find({
            "seller_id": user_id,
            "status": "pending"
        }).sort("scheduled_at", 1)
        
        scheduled = await cursor.to_list(length=None)
        
        if not scheduled:
            text = """
⏰ *קופונים מתוזמנים*

אין לך קופונים מתוזמנים.

להוספת קופון מתוזמן, בחר "תזמון פרסום" מתפריט ניהול מוצרים.
"""
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="dashboard_products")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        
        text = f"⏰ *קופונים מתוזמנים* ({len(scheduled)})\n\n"
        
        items = []
        for s in scheduled[:10]:
            title = s.get("coupon_data", {}).get("title", "ללא שם")[:20]
            scheduled_time = s.get("scheduled_at").strftime("%d/%m/%Y %H:%M")
            items.append((str(s["_id"]), title, scheduled_time))
        
        keyboard = Keyboards.scheduled_coupons_keyboard(items, 0, 1)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def cancel_scheduled_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול קופון מתוזמן"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        schedule_id = query.data.replace("scheduled_cancel_", "")
        
        scheduled_col = await database.get_scheduled_coupons_collection()
        
        result = await scheduled_col.update_one(
            {"_id": ObjectId(schedule_id), "seller_id": user_id},
            {"$set": {"status": "cancelled"}}
        )
        
        if result.modified_count > 0:
            await query.answer("✅ התזמון בוטל", show_alert=True)
        else:
            await query.answer("❌ ביטול נכשל", show_alert=True)
        
        return await SellerHandlers.show_scheduled_list(update, context)
