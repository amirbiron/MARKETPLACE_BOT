"""
Handlers לקונים - רכישת קופונים
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from keyboards import Keyboards
from utils import format_price, format_datetime, get_star_rating, calculate_discount_percent
from config import Config
import logging

logger = logging.getLogger(__name__)

# States for conversation
SEARCH_TEXT = 1


class BuyerHandlers:
    """Handler לפעולות קונים"""
    
    @staticmethod
    async def browse_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת קטגוריות"""
        query = update.callback_query
        if query:
            await query.answer()
        
        text = "🛒 *בחר קטגוריה:*\n\nמה מעניין אותך?"
        keyboard = Keyboards.categories_keyboard()
        
        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_category_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת קופונים בקטגוריה"""
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("cat_", "")
        page = context.user_data.get(f"page_{category}", 0)
        
        # קבלת קופונים
        coupons, total = await CouponService.get_coupons_by_category(
            category=category,
            page=page
        )
        
        if not coupons:
            await query.edit_message_text(
                f"😔 אין קופונים זמינים ב{category}\n\nנסה קטגוריה אחרת.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        # בניית רשימת קופונים
        items = []
        for coupon in coupons:
            discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
            seller = await UserService.get_user(coupon.seller_id)
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"
            rating_str = get_star_rating(seller.rating_average) if seller else "⭐ חדש"
            
            text = f"{coupon.title} - {format_price(coupon.sale_price)} ({discount}% הנחה) | {seller_name} {rating_str}"
            items.append((text, f"coupon_{str(coupon._id)}"))
        
        # יצירת מקלדת עם פגינציה
        total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE
        keyboard = Keyboards.pagination_keyboard(items, page, total_pages, f"cat_{category}")
        
        text = f"📦 *{category}*\n\nבחר קופון לצפייה:"
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_coupon_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת פרטי קופון"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = ObjectId(query.data.replace("coupon_", ""))
        coupon = await CouponService.get_coupon(coupon_id)
        
        if not coupon or coupon.status.value != "active":
            await query.edit_message_text(
                "❌ הקופון לא זמין יותר.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        # קבלת פרטי מוכר
        seller = await UserService.get_user(coupon.seller_id)
        seller_name = seller.business_name if seller and seller.business_name else "מוכר"
        rating = get_star_rating(seller.rating_average) if seller else "⭐ חדש"
        
        # חישוב מחיר סופי
        buyer_commission = coupon.sale_price * Config.BUYER_COMMISSION
        total_price = coupon.sale_price + buyer_commission
        discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
        
        text = f"""
🎫 *{coupon.title}*

📁 קטגוריה: {coupon.category}
💰 מחיר מקורי: ~{format_price(coupon.original_price)}~
💵 מחיר מבצע: *{format_price(coupon.sale_price)}*
🏷️ הנחה: *{discount}%*

➕ עמלת קנייה (2%): {format_price(buyer_commission)}
💳 *סה"כ לתשלום: {format_price(total_price)}*

👤 מוכר: {seller_name}
⭐ דירוג: {rating} ({seller.rating_count} ביקורות)

📝 תיאור:
{coupon.description or 'אין תיאור'}
"""
        
        # בדיקה אם בmועדפים (TODO: implement favorites)
        is_favorite = False
        
        keyboard = Keyboards.coupon_details_keyboard(
            str(coupon._id),
            coupon.seller_id,
            update.effective_user.id,
            is_favorite
        )
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def initiate_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך קנייה"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = ObjectId(query.data.replace("buy_", ""))
        coupon = await CouponService.get_coupon(coupon_id)
        
        if not coupon or coupon.status.value != "active":
            await query.edit_message_text(
                "❌ הקופון לא זמין יותר.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        user_id = update.effective_user.id
        user = await UserService.get_user(user_id)
        
        # חישוב עלות
        buyer_commission = coupon.sale_price * Config.BUYER_COMMISSION
        total_price = coupon.sale_price + buyer_commission
        
        # בדיקת יתרה
        if user.balance < total_price:
            await query.edit_message_text(
                f"❌ *יתרה לא מספיקה!*\n\n"
                f"נדרש: {format_price(total_price)}\n"
                f"יתרתך: {format_price(user.balance)}\n\n"
                f"חסר: {format_price(total_price - user.balance)}\n\n"
                f"אנא טען יתרה ונסה שוב.",
                reply_markup=Keyboards.back_button(),
                parse_mode="Markdown"
            )
            return
        
        # הצגת אישור
        text = f"""
✅ *אישור קנייה*

🎫 {coupon.title}
💰 מחיר: {format_price(coupon.sale_price)}
➕ עמלה: {format_price(buyer_commission)}
💳 סה"כ: *{format_price(total_price)}*

📊 יתרתך לאחר הקנייה: {format_price(user.balance - total_price)}

האם לאשר את הקנייה?
"""
        
        keyboard = Keyboards.confirm_purchase_keyboard(str(coupon._id), total_price)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור סופי של קנייה"""
        query = update.callback_query
        await query.answer()
        
        coupon_id = ObjectId(query.data.replace("confirm_buy_", ""))
        user_id = update.effective_user.id
        
        # ביצוע הרכישה
        order = await OrderService.create_order(user_id, coupon_id)
        
        if not order:
            await query.edit_message_text(
                "❌ הרכישה נכשלה. אנא נסה שוב.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        # קבלת פרטי הקופון
        coupon = await CouponService.get_coupon(coupon_id)
        
        text = f"""
🎉 *רכישה בוצעה בהצלחה!*

🎫 {coupon.title}
💳 שולם: {format_price(order.price_paid)}

🔐 *קוד הקופון:*
`{coupon.digital_code or 'הקוד נשלח למוכר'}`

⏰ *חשוב!*
יש לך *12 שעות* לדווח על בעיה עם הקופון.
לאחר מכן, העסקה תושלם אוטומטית.

📊 ניתן לצפות בהזמנה ב"ההזמנות שלי"
"""
        
        can_report = await OrderService.can_report_issue(order._id)
        keyboard = Keyboards.order_actions_keyboard(str(order._id), can_report)
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת ההזמנות שלי"""
        user_id = update.effective_user.id
        orders = await OrderService.get_buyer_orders(user_id)
        
        if not orders:
            text = "📜 אין לך הזמנות עדיין.\n\nהתחל לקנות קופונים!"
            keyboard = Keyboards.back_button()
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=keyboard)
            else:
                await update.message.reply_text(text, reply_markup=keyboard)
            return
        
        # בניית רשימה
        items = []
        for order in orders[:10]:  # מגבלה של 10 אחרונים
            coupon = await CouponService.get_coupon(order.coupon_id)
            seller = await UserService.get_user(order.seller_id)
            
            status_emoji = {
                "pending": "⏳",
                "completed": "✅",
                "confirmed": "✅",
                "disputed": "⚠️",
                "refunded": "💰"
            }.get(order.status.value, "❓")
            
            coupon_title = coupon.title if coupon else "קופון"
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"
            
            text = f"{status_emoji} {coupon_title} | {seller_name} | {format_price(order.price_paid)}"
            items.append((text, f"order_{str(order._id)}"))
        
        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "orders")
        text = "📜 *ההזמנות שלי:*\n\nבחר הזמנה לצפייה:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת פרטי הזמנה"""
        query = update.callback_query
        await query.answer()
        
        order_id = ObjectId(query.data.replace("order_", ""))
        order = await OrderService.get_order(order_id)
        
        if not order:
            await query.edit_message_text(
                "❌ ההזמנה לא נמצאה.",
                reply_markup=Keyboards.back_button()
            )
            return
        
        coupon = await CouponService.get_coupon(order.coupon_id)
        seller = await UserService.get_user(order.seller_id)
        
        status_text = {
            "pending": "⏳ ממתין",
            "completed": "✅ הושלם",
            "confirmed": "✅ אושר",
            "disputed": "⚠️ במחלוקת",
            "refunded": "💰 הוחזר"
        }.get(order.status.value, "❓")
        
        text = f"""
📦 *פרטי הזמנה*

🎫 {coupon.title if coupon else 'קופון'}
👤 מוכר: {seller.business_name if seller and seller.business_name else 'מוכר'}
📅 תאריך: {format_datetime(order.created_at)}

💰 מחיר: {format_price(order.price_paid)}
📊 סטטוס: {status_text}

🔐 קוד הקופון:
`{coupon.digital_code if coupon else 'לא זמין'}`
"""
        
        can_report = await OrderService.can_report_issue(order._id)
        keyboard = Keyboards.order_actions_keyboard(str(order._id), can_report)
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def confirm_order_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור קבלת קופון"""
        query = update.callback_query
        await query.answer()
        
        order_id = ObjectId(query.data.replace("confirm_order_", ""))
        success = await OrderService.confirm_order(order_id)
        
        if success:
            await query.edit_message_text(
                "✅ *תודה על האישור!*\n\n"
                "הקופון אושר בהצלחה.\n"
                "הכספים שוחררו למוכר.\n\n"
                "נשמח אם תדרג את המוכר! 😊",
                reply_markup=Keyboards.back_button(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ האישור נכשל. אנא נסה שוב.",
                reply_markup=Keyboards.back_button()
            )
    
    @staticmethod
    async def start_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך דירוג"""
        query = update.callback_query
        await query.answer()
        
        order_id = query.data.replace("rate_", "")
        context.user_data['rating_order_id'] = order_id
        
        text = "⭐ *דרג את המוכר*\n\nבחר דירוג:"
        keyboard = Keyboards.rating_keyboard(order_id)
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    @staticmethod
    async def submit_rating_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת דירוג"""
        query = update.callback_query
        await query.answer()

        parts = query.data.split("_")
        rating = int(parts[1])
        order_id = parts[2]

        context.user_data['rating_score'] = rating
        context.user_data['rating_order_id'] = order_id

        text = f"""
⭐ דירוג: {get_star_rating(rating)}

📝 כעת, שלח הערה קצרה על המוכר (עד 15 תווים)
או לחץ "דלג" לסיום ללא הערה.
"""

        await query.edit_message_text(text, parse_mode="Markdown")
        await query.message.reply_text("⏳ ממתין להערה או /skip לדילוג...")

        return SEARCH_TEXT  # Conversation state

    @staticmethod
    async def show_hot_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת קופונים חמים (נמכרים ביותר)"""
        query = update.callback_query
        if query:
            await query.answer()

        # קבלת קופונים חמים
        hot_coupons = await CouponService.get_hot_coupons(limit=10)

        if not hot_coupons:
            text = "🔥 *קופונים חמים*\n\nאין מספיק נתונים עדיין.\nחזור אחרי כמה ימים!"
            keyboard = Keyboards.back_button()

            if query:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return

        # בניית רשימת קופונים
        items = []
        for coupon in hot_coupons:
            discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
            seller = await UserService.get_user(coupon.seller_id)
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"
            rating_str = get_star_rating(seller.rating_average) if seller else "⭐ חדש"

            text_item = f"🔥 {coupon.title} - {format_price(coupon.sale_price)} ({discount}% הנחה) | {seller_name} {rating_str}"
            items.append((text_item, f"coupon_{str(coupon._id)}"))

        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "hot_coupons")
        text = "🔥 *קופונים חמים*\n\nהקופונים הנמכרים ביותר השבוע:"

        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת חיפוש"""
        query = update.callback_query
        if query:
            await query.answer()

        text = """
🔍 *חיפוש קופונים*

שלח מילת חיפוש (למשל: "מסעדה", "ספא", "קולנוע")
או השתמש ב-/filters לחיפוש מתקדם עם פילטרים.

לביטול: /cancel
"""

        if query:
            await query.edit_message_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, parse_mode="Markdown")

        return SEARCH_TEXT

    @staticmethod
    async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד שאילתת חיפוש"""
        search_text = update.message.text

        # חיפוש קופונים
        coupons, total = await CouponService.search_coupons(search_text, page=0)

        if not coupons:
            await update.message.reply_text(
                f"😔 לא נמצאו תוצאות עבור: *{search_text}*\n\n"
                f"נסה מילים אחרות או השתמש ב-/filters",
                parse_mode="Markdown"
            )
            return ConversationHandler.END

        # בניית רשימת תוצאות
        items = []
        for coupon in coupons[:10]:
            discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
            seller = await UserService.get_user(coupon.seller_id)
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"

            text_item = f"{coupon.title} - {format_price(coupon.sale_price)} ({discount}% הנחה) | {seller_name}"
            items.append((text_item, f"coupon_{str(coupon._id)}"))

        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "search")
        text = f"🔍 *תוצאות חיפוש עבור: {search_text}*\n\nנמצאו {total} תוצאות:"

        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return ConversationHandler.END

    @staticmethod
    async def show_search_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת פילטרים לחיפוש מתקדם"""
        text = """
🔍 *חיפוש מתקדם*

בחר פילטרים:
• קטגוריה - בחר קטגוריה ספציפית
• טווח מחיר - הגדר מחיר מינימלי/מקסימלי
• אחוז הנחה - מינימום X% הנחה
• דירוג מוכר - רק מוכרים מעל X כוכבים

לחץ על הכפתורים מטה להגדרת הפילטרים:
"""

        keyboard = [
            [{"text": "🗂️ בחר קטגוריה", "callback_data": "filter_category"}],
            [{"text": "💰 טווח מחיר", "callback_data": "filter_price"}],
            [{"text": "🏷️ אחוז הנחה מינימלי", "callback_data": "filter_discount"}],
            [{"text": "⭐ דירוג מוכר מינימלי", "callback_data": "filter_rating"}],
            [{"text": "🔍 חפש עם הפילטרים", "callback_data": "apply_filters"}],
            [{"text": "🔙 חזרה", "callback_data": "back"}]
        ]

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"])] for btn in keyboard])

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    @staticmethod
    async def apply_search_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """החלת פילטרי חיפוש"""
        query = update.callback_query
        await query.answer()

        # קבלת פילטרים מהקונטקסט
        search_text = context.user_data.get("filter_search_text")
        category = context.user_data.get("filter_category")
        min_price = context.user_data.get("filter_min_price")
        max_price = context.user_data.get("filter_max_price")
        min_discount = context.user_data.get("filter_min_discount")
        min_seller_rating = context.user_data.get("filter_min_rating")

        # חיפוש עם פילטרים
        coupons, total = await CouponService.advanced_search(
            search_text=search_text,
            category=category,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            min_seller_rating=min_seller_rating,
            page=0
        )

        if not coupons:
            await query.edit_message_text(
                "😔 לא נמצאו תוצאות עם הפילטרים שנבחרו.\n\nנסה להרחיב את הפילטרים.",
                reply_markup=Keyboards.back_button()
            )
            return

        # בניית רשימת תוצאות
        items = []
        for coupon in coupons[:10]:
            discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
            seller = await UserService.get_user(coupon.seller_id)
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"

            text_item = f"{coupon.title} - {format_price(coupon.sale_price)} ({discount}% הנחה) | {seller_name}"
            items.append((text_item, f"coupon_{str(coupon._id)}"))

        keyboard = Keyboards.pagination_keyboard(items, 0, 1, "filtered_search")

        # בניית טקסט פילטרים
        filters_applied = []
        if search_text:
            filters_applied.append(f"טקסט: {search_text}")
        if category:
            filters_applied.append(f"קטגוריה: {category}")
        if min_price:
            filters_applied.append(f"מחיר מינימלי: {format_price(min_price)}")
        if max_price:
            filters_applied.append(f"מחיר מקסימלי: {format_price(max_price)}")
        if min_discount:
            filters_applied.append(f"הנחה: {min_discount}%+")
        if min_seller_rating:
            filters_applied.append(f"דירוג: {min_seller_rating}⭐+")

        filters_text = "\n• ".join(filters_applied) if filters_applied else "אין"

        text = f"""
🔍 *תוצאות חיפוש מתקדם*

📋 פילטרים:
• {filters_text}

נמצאו {total} תוצאות:
"""

        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
