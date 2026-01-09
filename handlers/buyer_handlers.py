"""
Handlers לקונים - רכישת קופונים
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bson import ObjectId
from services.user_service import UserService
from services.coupon_service import CouponService
from services.order_service import OrderService
from services.favorites_service import FavoritesService
from keyboards import Keyboards
from utils import format_price, format_datetime, get_star_rating, calculate_discount_percent
from config import Config
import logging

logger = logging.getLogger(__name__)

# States for conversation
SEARCH_TEXT = 1
RATING_COMMENT = 2
SELECT_RATING = 3


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
        discount = calculate_discount_percent(coupon.original_price, coupon.sale_price)
        
        # במודל P2P (Classifieds) - אין עמלת קנייה
        if Config.CLASSIFIEDS_MODEL_ENABLED:
            text = f"""
🎫 *{coupon.title}*

📁 קטגוריה: {coupon.category}
💰 מחיר מקורי: ~{format_price(coupon.original_price)}~
💵 מחיר לתשלום: *{format_price(coupon.sale_price)}*
🏷️ הנחה: *{discount}%*

👤 מוכר: {seller_name}
⭐ דירוג: {rating} ({seller.rating_count} ביקורות)

📝 תיאור:
{coupon.description or 'אין תיאור'}

━━━━━━━━━━━━━━━━━━━━
💡 *תשלום ישיר למוכר* (P2P)
התשלום מתבצע ישירות למוכר באמצעות ביט/פייבוקס.
לחץ "קנה עכשיו" לצפייה בפרטי התשלום.
"""
        else:
            # מודל ארנק ישן - כולל עמלת קנייה
            buyer_commission = coupon.sale_price * Config.BUYER_COMMISSION
            total_price = coupon.sale_price + buyer_commission
            
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
        
        # בדיקה אם במועדפים
        is_favorite = await FavoritesService.is_favorite(
            user_id=update.effective_user.id,
            coupon_id=str(coupon._id)
        )

        # שמירה לניווט עתידי (למשל פרופיל/דירוגים)
        context.user_data["last_viewed_coupon_id"] = str(coupon._id)
        context.user_data["last_viewed_seller_id"] = coupon.seller_id
        
        keyboard = Keyboards.coupon_details_keyboard(
            str(coupon._id),
            coupon.seller_id,
            update.effective_user.id,
            is_favorite
        )
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def show_seller_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת פרופיל מוכר (callback_data: seller_<seller_id>)"""
        query = update.callback_query
        await query.answer()

        from services.review_service import ReviewService
        from telegram import InlineKeyboardMarkup

        parts = (query.data or "").split("_", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            await query.edit_message_text("❌ מזהה מוכר לא תקין.")
            return

        seller_id = int(parts[1])
        seller = await UserService.get_user(seller_id)
        if not seller:
            await query.edit_message_text("❌ המוכר לא נמצא.")
            return

        stats = await ReviewService.get_seller_rating_stats(seller_id)
        avg = float(stats.get("average", 0.0) or 0.0)
        count = int(stats.get("count", 0) or 0)
        rating_str = get_star_rating(avg) if count > 0 else "⭐ ללא דירוג"

        verified_badge = "✅ מאומת" if getattr(seller, "is_verified", False) or getattr(seller, "role", None).value == "seller_verified" else "⚠️ לא מאומת"
        seller_name = getattr(seller, "display_name", None) or seller.business_name or seller.first_name or "מוכר"

        # Trust score (optional; ignore failures)
        trust_line = ""
        try:
            trust = await UserService.get_trust_score(seller_id)
            trust_line = f"\n🛡️ ניקוד אמינות: {trust}/100"
        except Exception:
            trust_line = ""

        text = (
            f"👤 *פרופיל המוכר*\n\n"
            f"🏷️ שם: {seller_name}\n"
            f"{verified_badge}\n"
            f"⭐ דירוג: {rating_str} ({count})"
            f"{trust_line}\n\n"
            f"💬 לשיחה עם המוכר השתמש בכפתור למטה."
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 צפה בדירוגים", callback_data=f"reviews_{seller_id}")],
            [InlineKeyboardButton("💬 פתח צ'אט עם המוכר", callback_data=f"chat_seller_{seller_id}")],
            [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")],
        ])

        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def show_seller_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת דירוגים וביקורות של מוכר (reviews_<seller_id>[_page_<n>])"""
        query = update.callback_query
        await query.answer()

        from services.review_service import ReviewService
        from telegram import InlineKeyboardMarkup
        from database import db

        parts = (query.data or "").split("_")
        # Expected: ["reviews", "<seller_id>"] or ["reviews", "<seller_id>", "page", "<n>"]
        if len(parts) < 2 or parts[0] != "reviews" or not parts[1].isdigit():
            await query.edit_message_text("❌ בקשה לא תקינה.")
            return

        seller_id = int(parts[1])
        page = 0
        if len(parts) >= 4 and parts[2] == "page" and parts[3].isdigit():
            page = max(0, int(parts[3]))

        seller = await UserService.get_user(seller_id)
        if not seller:
            await query.edit_message_text("❌ המוכר לא נמצא.")
            return

        total_count = await db.reviews.count_documents({"seller_id": seller_id})
        total_pages = max(1, (total_count + Config.REVIEWS_PER_PAGE - 1) // Config.REVIEWS_PER_PAGE)
        page = min(page, total_pages - 1)

        stats = await ReviewService.get_seller_rating_stats(seller_id)
        avg = float(stats.get("average", 0.0) or 0.0)
        count = int(stats.get("count", 0) or 0)
        dist = stats.get("stars_distribution", {}) or {}

        reviews = await ReviewService.get_seller_reviews(seller_id, page=page)

        seller_name = getattr(seller, "display_name", None) or seller.business_name or seller.first_name or "מוכר"
        rating_display = get_star_rating(avg) if count > 0 else "⭐ ללא דירוג"

        dist_lines = []
        for stars in range(5, 0, -1):
            dist_lines.append(f"{'⭐' * stars}: {int(dist.get(stars, 0) or 0)}")
        dist_text = "\n".join(dist_lines)

        text = (
            f"📊 *דירוגים וביקורות*\n\n"
            f"👤 מוכר: {seller_name}\n"
            f"⭐ ממוצע: {rating_display} ({count})\n\n"
            f"*התפלגות:*\n{dist_text}\n\n"
        )

        if not reviews:
            text += "אין ביקורות להצגה עדיין."
        else:
            text += "*ביקורות אחרונות:*\n\n"
            for r in reviews:
                buyer_name = r.get("buyer_name", "קונה")
                rating = int(r.get("rating", 0) or 0)
                comment = (r.get("comment") or "").strip()
                created_at = r.get("created_at")
                date_str = created_at.strftime("%d/%m/%y") if created_at else ""

                line = f"{'⭐' * max(0, min(5, rating))} {buyer_name}"
                if date_str:
                    line += f" ({date_str})"
                if comment:
                    line += f" — {comment}"
                text += f"• {line}\n"

            text += f"\nעמוד {page + 1}/{total_pages}"

        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"reviews_{seller_id}_page_{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"reviews_{seller_id}_page_{page + 1}"))

        keyboard_rows = []
        if nav_row:
            keyboard_rows.append(nav_row)
        keyboard_rows.extend([
            [InlineKeyboardButton("👤 פרופיל המוכר", callback_data=f"seller_{seller_id}")],
            [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")],
        ])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="Markdown")
    
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
        return SELECT_RATING
    
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

        return RATING_COMMENT  # Conversation state

    @staticmethod
    async def process_rating_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת הערה לדירוג (עד 15 תווים)"""
        from services.review_service import ReviewService
        from services.order_service import OrderService
        from bson import ObjectId

        user_id = update.effective_user.id
        order_id = context.user_data.get("rating_order_id")
        rating = context.user_data.get("rating_score")

        if not order_id or not rating:
            await update.message.reply_text("❌ משהו השתבש בתהליך הדירוג. נסה שוב מההזמנות שלי.")
            return ConversationHandler.END

        comment = update.message.text
        if comment == "/skip":
            comment = None

        order = await OrderService.get_order(ObjectId(order_id))
        if not order:
            await update.message.reply_text("❌ ההזמנה לא נמצאה.")
            return ConversationHandler.END

        error = await ReviewService.create_review(
            buyer_id=user_id,
            seller_id=order.seller_id,
            order_id=order_id,
            rating=int(rating),
            comment=comment,
        )

        if error:
            await update.message.reply_text(error)
        else:
            await update.message.reply_text("✅ תודה! הדירוג נשמר בהצלחה.")

        context.user_data.pop("rating_score", None)
        context.user_data.pop("rating_order_id", None)
        return ConversationHandler.END

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

    # ===== מערכת מועדפים =====

    @staticmethod
    async def show_my_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת המועדפים שלי"""
        query = update.callback_query
        if query:
            await query.answer()

        user_id = update.effective_user.id
        page = context.user_data.get("favorites_page", 0)

        # קבלת מועדפים
        favorites = await FavoritesService.get_user_favorites(user_id, page)
        total_count = await FavoritesService.get_favorites_count(user_id)

        if not favorites:
            text = "⭐ *המועדפים שלי*\n\nאין לך קופונים במועדפים עדיין.\n\nלחץ על ⭐ בדף קופון כדי להוסיף למועדפים!"
            keyboard = Keyboards.back_button()

            if query:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return

        # בניית רשימת מועדפים
        items = []
        for fav_data in favorites:
            coupon = fav_data["coupon"]
            price_dropped = fav_data.get("price_dropped", False)
            price_change = fav_data.get("price_change", 0)

            discount = calculate_discount_percent(coupon.get("original_price", 0), coupon.get("sale_price", 0))

            # אינדיקטור לירידת מחיר
            price_indicator = ""
            if price_dropped and price_change > 0:
                price_indicator = f" 📉-{format_price(price_change)}"

            text_item = f"⭐ {coupon.get('title', 'קופון')} - {format_price(coupon.get('sale_price', 0))} ({discount}% הנחה){price_indicator}"
            items.append((text_item, f"coupon_{str(coupon['_id'])}"))

        # חישוב עמודים
        total_pages = (total_count + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

        # יצירת מקלדת עם פגינציה
        keyboard = Keyboards.favorites_list_keyboard(items, page, total_pages)

        text = f"⭐ *המועדפים שלי*\n\n📊 סה\"כ: {total_count} קופונים\n\nבחר קופון לצפייה:"

        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def add_to_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הוספת קופון למועדפים"""
        query = update.callback_query
        await query.answer()

        coupon_id = query.data.replace("fav_", "")
        user_id = update.effective_user.id

        # הוספה למועדפים
        error = await FavoritesService.add_favorite(user_id, coupon_id)

        if error:
            await query.answer(error, show_alert=True)
        else:
            await query.answer("⭐ נוסף למועדפים!", show_alert=True)

            # רענון דף הקופון עם הכפתור המעודכן
            coupon = await CouponService.get_coupon(ObjectId(coupon_id))

            if coupon and coupon.status.value == "active":
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

                keyboard = Keyboards.coupon_details_keyboard(
                    coupon_id,
                    coupon.seller_id,
                    user_id,
                    is_favorite=True
                )

                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def remove_from_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הסרת קופון ממועדפים"""
        query = update.callback_query
        await query.answer()

        coupon_id = query.data.replace("unfav_", "")
        user_id = update.effective_user.id

        # הסרה ממועדפים
        error = await FavoritesService.remove_favorite(user_id, coupon_id)

        if error:
            await query.answer(error, show_alert=True)
        else:
            await query.answer("💔 הוסר מהמועדפים", show_alert=True)

            # רענון דף הקופון עם הכפתור המעודכן
            coupon = await CouponService.get_coupon(ObjectId(coupon_id))

            if coupon and coupon.status.value == "active":
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

                keyboard = Keyboards.coupon_details_keyboard(
                    coupon_id,
                    coupon.seller_id,
                    user_id,
                    is_favorite=False
                )

                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def favorites_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניווט בין עמודי מועדפים"""
        query = update.callback_query
        await query.answer()

        # חילוץ מספר העמוד מה-callback_data
        page = int(query.data.replace("favorites_page_", ""))
        context.user_data["favorites_page"] = page

        # הצגת העמוד המבוקש
        await BuyerHandlers.show_my_favorites(update, context)

    # ===== התראות - אישור ודיווח מהתראה =====

    @staticmethod
    async def confirm_from_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """אישור קבלת קופון מתוך התראה"""
        query = update.callback_query
        await query.answer()

        order_id = ObjectId(query.data.replace("confirm_from_notif_", ""))
        success = await OrderService.confirm_order(order_id)

        if success:
            await query.edit_message_text(
                "✅ *תודה על האישור!*\n\n"
                "הקופון אושר בהצלחה.\n"
                "הכספים שוחררו למוכר.\n\n"
                "נשמח אם תדרג את המוכר! 😊\n\n"
                "לדירוג לחץ /myorders ובחר את ההזמנה",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ האישור נכשל.\n\nייתכן שההזמנה כבר אושרה או שיש בעיה אחרת.\n\nלצפייה בהזמנות: /myorders"
            )

    @staticmethod
    async def report_from_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דיווח על בעיה מתוך התראה"""
        query = update.callback_query
        await query.answer()

        order_id = query.data.replace("report_from_notif_", "")

        # בדיקה אם עדיין ניתן לדווח
        can_report = await OrderService.can_report_issue(ObjectId(order_id))

        if not can_report:
            await query.edit_message_text(
                "❌ חלון הדיווח נסגר.\n\n"
                "לא ניתן יותר לדווח על בעיה בהזמנה זו.\n"
                "העסקה הושלמה אוטומטית."
            )
            return

        # הפניה לפתיחת מחלוקת
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("🚨 פתח מחלוקת", callback_data=f"report_issue_{order_id}")],
            [InlineKeyboardButton("💬 צ'אט עם המוכר", callback_data=f"chat_{order_id}")],
            [InlineKeyboardButton("🔙 ביטול", callback_data=f"order_{order_id}")]
        ]

        await query.edit_message_text(
            "🚨 *דיווח על בעיה*\n\n"
            "מה תרצה לעשות?\n\n"
            "• *פתח מחלוקת* - יפתח טיפול של צוות התמיכה\n"
            "• *צ'אט עם המוכר* - נסה לפתור ישירות עם המוכר",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # ===== היסטוריית קופונים שנמכרו (שקיפות) =====

    @staticmethod
    async def show_sold_coupons_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת היסטוריית קופונים שנמכרו - לשקיפות ובניית אמון"""
        query = update.callback_query
        if query:
            await query.answer()

        page = context.user_data.get("sold_coupons_page", 0)
        items_per_page = 10
        max_total = 100  # מקסימום 100 עסקאות אחרונות

        # קבלת הזמנות שהושלמו
        from database import db
        from services.coupon_service import CouponService

        orders_collection = db.orders
        cursor = orders_collection.find({
            "status": {"$in": ["completed", "confirmed"]}
        }).sort("created_at", -1).skip(page * items_per_page).limit(items_per_page)

        orders = await cursor.to_list(length=items_per_page)

        # ספירת סה"כ הזמנות
        total_count = await orders_collection.count_documents({
            "status": {"$in": ["completed", "confirmed"]}
        })
        total_count = min(total_count, max_total)
        total_pages = (total_count + items_per_page - 1) // items_per_page

        if not orders:
            text = "📜 *קופונים שנמכרו*\n\nאין עסקאות עדיין במערכת."
            keyboard = Keyboards.back_button()

            if query:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return

        # בניית רשימת העסקאות
        items = []
        transactions_text = ""

        for i, order in enumerate(orders):
            # קבלת פרטי קופון
            coupon = await CouponService.get_coupon(order["coupon_id"])
            coupon_title = coupon.title if coupon else "קופון"
            category = coupon.category if coupon else "כללי"
            original_price = coupon.original_price if coupon else 0

            # קבלת פרטי מוכר
            seller = await UserService.get_user(order["seller_id"])
            seller_name = seller.business_name if seller and seller.business_name else "מוכר"

            # שם קונה אנונימי (י***)
            buyer = await UserService.get_user(order["buyer_id"])
            if buyer and buyer.first_name:
                first_char = buyer.first_name[0] if buyer.first_name else "?"
                buyer_name = f"{first_char}***"
            else:
                buyer_name = "?***"

            # מחיר מכירה (ללא עמלות)
            sale_price = order.get("price_paid", 0) - order.get("buyer_commission", 0)

            # תאריך
            created_at = order.get("created_at")
            date_str = created_at.strftime("%d/%m/%y %H:%M") if created_at else ""

            # הוספת פרטי עסקה לטקסט
            transactions_text += f"\n*{i+1 + (page * items_per_page)}.* {coupon_title}\n"
            transactions_text += f"   👤 {buyer_name} ← {seller_name}\n"
            transactions_text += f"   📁 {category} | 💰 ~{format_price(original_price)}~ → *{format_price(sale_price)}*\n"
            transactions_text += f"   📅 {date_str}\n"

            # יצירת item לכפתור (קצר)
            text_item = f"📜 {coupon_title[:20]}... | {format_price(sale_price)}"
            items.append((text_item, str(order["_id"])))

        # יצירת מקלדת פגינציה בלבד (בלי כפתורי עסקאות)
        keyboard = Keyboards.sold_coupons_pagination_keyboard(page, total_pages)

        # טקסט ראשי
        text = f"""📜 *קופונים שנמכרו לאחרונה*

💡 *שקיפות מלאה* - כל העסקאות האחרונות במערכת
📊 סה"כ: {total_count} עסקאות | עמוד {page + 1}/{total_pages}
{transactions_text}"""

        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    @staticmethod
    async def sold_coupons_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניווט בין עמודי היסטוריית קופונים שנמכרו"""
        query = update.callback_query
        await query.answer()

        # חילוץ מספר העמוד
        page = int(query.data.replace("sold_page_", ""))
        context.user_data["sold_coupons_page"] = page

        # הצגת העמוד המבוקש
        await BuyerHandlers.show_sold_coupons_history(update, context)

    @staticmethod
    async def sold_coupon_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הודעה כשלוחצים על פריט בהיסטוריה"""
        query = update.callback_query
        await query.answer(
            "📜 היסטוריית עסקאות לשקיפות בלבד",
            show_alert=False
        )
