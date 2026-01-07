"""
Handlers למערכת מכרזים (Auctions)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.auction_service import AuctionService
from services.user_service import UserService
from database import db
from config import Config
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# States for conversation
SELECT_AUCTION_COUPON, SET_STARTING_PRICE, SET_DURATION, PLACE_BID_AMOUNT = range(4)


class AuctionHandlers:
    """Handlers עבור מכרזים"""

    @staticmethod
    async def view_auctions(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה במכרזים פעילים"""
        query = update.callback_query
        await query.answer()

        page = int(context.user_data.get("auction_page", 0))

        auctions = await AuctionService.get_active_auctions(page=page)

        if not auctions:
            await query.edit_message_text(
                "🎪 אין מכרזים פעילים כרגע\n\n"
                "💡 מכרזים מאפשרים לך להשיג קופונים במחיר נמוך!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 חזרה", callback_data="main_menu")
                ]])
            )
            return

        text = "🎪 *מכרזים פעילים*\n\n"

        for i, auction in enumerate(auctions, 1):
            coupon = auction.get("coupon", {})
            time_left = auction["end_time"] - datetime.utcnow()
            hours_left = int(time_left.total_seconds() // 3600)
            minutes_left = int((time_left.total_seconds() % 3600) // 60)

            text += f"{i}. *{coupon.get('title', 'קופון')}*\n"
            text += f"   💰 מחיר נוכחי: {auction['current_price']:.2f}₪\n"
            text += f"   📊 מחיר מקורי: {coupon.get('original_price', 0):.2f}₪\n"
            text += f"   ⏰ נותרו: {hours_left}ש' {minutes_left}ד'\n"
            text += f"   🔢 הצעות: {auction.get('bid_count', 0)}\n\n"

        keyboard = []
        for i, auction in enumerate(auctions, 1):
            keyboard.append([InlineKeyboardButton(
                f"#{i} - פרטים והצעה",
                callback_data=f"auction_view_{auction['_id']}"
            )])

        # Pagination
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ הקודם", callback_data=f"auctions_page_{page-1}"))
        if len(auctions) >= Config.ITEMS_PER_PAGE:
            nav_buttons.append(InlineKeyboardButton("הבא ▶️", callback_data=f"auctions_page_{page+1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="main_menu")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def view_auction_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בפרטי מכרז ספציפי"""
        query = update.callback_query
        await query.answer()

        auction_id = query.data.split("_")[-1]
        auction = await AuctionService.get_auction_by_id(auction_id)

        if not auction:
            await query.edit_message_text("❌ מכרז לא נמצא")
            return

        coupon = auction.get("coupon", {})
        seller = auction.get("seller", {})

        time_left = auction["end_time"] - datetime.utcnow()
        hours_left = int(time_left.total_seconds() // 3600)
        minutes_left = int((time_left.total_seconds() % 3600) // 60)

        text = f"🎪 *מכרז: {coupon.get('title', 'קופון')}*\n\n"
        text += f"📦 *פרטי הקופון:*\n"
        text += f"קטגוריה: {coupon.get('category', 'לא צוין')}\n"
        text += f"מחיר מקורי: {coupon.get('original_price', 0):.2f}₪\n"
        text += f"תיאור: {coupon.get('description', 'אין תיאור')}\n\n"

        text += f"💼 *המוכר:*\n"
        text += f"עסק: {seller.get('business_name', 'לא ידוע')}\n"
        text += f"{'✅ מאומת' if seller.get('verified') else '⚠️ לא מאומת'}\n\n"

        text += f"💰 *מצב המכרז:*\n"
        text += f"מחיר התחלתי: {auction['starting_price']:.2f}₪\n"
        text += f"מחיר נוכחי: {auction['current_price']:.2f}₪\n"
        text += f"מספר הצעות: {auction.get('bid_count', 0)}\n\n"

        text += f"⏰ *זמן נותר:* {hours_left}ש' {minutes_left}ד'\n"

        min_bid = auction['current_price'] + Config.MIN_BID_INCREMENT
        text += f"\n💡 הצעה מינימלית הבאה: {min_bid:.2f}₪"

        keyboard = [[
            InlineKeyboardButton("💸 הצע מחיר", callback_data=f"auction_bid_{auction_id}")
        ], [
            InlineKeyboardButton("📊 היסטוריית הצעות", callback_data=f"auction_history_{auction_id}")
        ], [
            InlineKeyboardButton("🔙 חזרה למכרזים", callback_data="view_auctions")
        ]]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

        # שמירת auction_id להצעה
        context.user_data["current_auction"] = auction_id

    @staticmethod
    async def start_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך הצבת הצעה"""
        query = update.callback_query
        await query.answer()

        auction_id = query.data.split("_")[-1]
        auction = await AuctionService.get_auction_by_id(auction_id)

        if not auction:
            await query.edit_message_text("❌ מכרז לא נמצא")
            return ConversationHandler.END

        min_bid = auction['current_price'] + Config.MIN_BID_INCREMENT

        await query.edit_message_text(
            f"💸 *הצבת הצעה*\n\n"
            f"מחיר נוכחי: {auction['current_price']:.2f}₪\n"
            f"הצעה מינימלית: {min_bid:.2f}₪\n\n"
            f"אנא שלח את סכום ההצעה שלך (מספר בלבד):",
            parse_mode="Markdown"
        )

        context.user_data["current_auction"] = auction_id
        return PLACE_BID_AMOUNT

    @staticmethod
    async def process_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד הצבת הצעה"""
        user_id = update.effective_user.id
        auction_id = context.user_data.get("current_auction")

        try:
            bid_amount = float(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין")
            return PLACE_BID_AMOUNT

        # הצבת הצעה
        error = await AuctionService.place_bid(auction_id, user_id, bid_amount)

        if error:
            await update.message.reply_text(error)
            return ConversationHandler.END

        await update.message.reply_text(
            f"✅ *ההצעה נקלטה בהצלחה!*\n\n"
            f"💰 הצעתך: {bid_amount:.2f}₪\n"
            f"💳 יתרה הוקפאה עד לסיום המכרז\n\n"
            f"🔔 נעדכן אותך אם תעקוף או אם תזכה!",
            parse_mode="Markdown"
        )

        return ConversationHandler.END

    @staticmethod
    async def view_bid_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """צפייה בהיסטוריית הצעות"""
        query = update.callback_query
        await query.answer()

        auction_id = query.data.split("_")[-1]
        bids = await AuctionService.get_auction_bids(auction_id, limit=10)

        if not bids:
            text = "📊 *היסטוריית הצעות*\n\nאין הצעות עדיין"
        else:
            text = "📊 *היסטוריית הצעות* (10 אחרונות)\n\n"
            for i, bid in enumerate(bids, 1):
                time_str = bid["created_at"].strftime("%H:%M")
                text += f"{i}. {bid['amount']:.2f}₪ - {time_str}\n"

        keyboard = [[
            InlineKeyboardButton("🔙 חזרה למכרז", callback_data=f"auction_view_{auction_id}")
        ]]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def create_auction_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך יצירת מכרז (למוכרים)"""
        user_id = update.effective_user.id

        # בדיקה שהמשתמש הוא מוכר
        user = await UserService.get_user(user_id)
        if not user or user.role not in ["seller_unverified", "seller_verified"]:
            await update.message.reply_text("❌ רק מוכרים יכולים ליצור מכרזים")
            return ConversationHandler.END

        # קבלת קופונים פעילים של המוכר
        coupons = await db.coupons.find({
            "seller_id": user_id,
            "status": "active"
        }).to_list(length=None)

        if not coupons:
            await update.message.reply_text(
                "❌ אין לך קופונים פעילים\n"
                "העלה קופון תחילה כדי ליצור מכרז"
            )
            return ConversationHandler.END

        text = "🎪 *יצירת מכרז*\n\n"
        text += "בחר קופון למכרז:\n\n"

        keyboard = []
        for i, coupon in enumerate(coupons, 1):
            text += f"{i}. {coupon['title']} - {coupon['sale_price']:.2f}₪\n"
            keyboard.append([InlineKeyboardButton(
                f"#{i} - {coupon['title'][:20]}",
                callback_data=f"auction_create_{coupon['_id']}"
            )])

        keyboard.append([InlineKeyboardButton("❌ ביטול", callback_data="cancel")])

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

        return SELECT_AUCTION_COUPON

    @staticmethod
    async def select_coupon_for_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """בחירת קופון למכרז"""
        query = update.callback_query
        await query.answer()

        if query.data == "cancel":
            await query.edit_message_text("❌ ביטול יצירת מכרז")
            return ConversationHandler.END

        coupon_id = query.data.split("_")[-1]
        context.user_data["auction_coupon_id"] = coupon_id

        await query.edit_message_text(
            "💰 *קביעת מחיר התחלתי*\n\n"
            "אנא שלח את מחיר ההתחלה למכרז (בשקלים):"
        )

        return SET_STARTING_PRICE

    @staticmethod
    async def set_starting_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קביעת מחיר התחלתי למכרז"""
        try:
            price = float(update.message.text)
            if price <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ אנא שלח מספר תקין")
            return SET_STARTING_PRICE

        context.user_data["auction_starting_price"] = price

        keyboard = [
            [InlineKeyboardButton("12 שעות", callback_data="duration_12")],
            [InlineKeyboardButton("24 שעות (מומלץ)", callback_data="duration_24")],
            [InlineKeyboardButton("48 שעות", callback_data="duration_48")],
            [InlineKeyboardButton("72 שעות", callback_data="duration_72")],
            [InlineKeyboardButton("❌ ביטול", callback_data="cancel")]
        ]

        await update.message.reply_text(
            "⏰ *משך המכרז*\n\n"
            "בחר כמה זמן המכרז יהיה פעיל:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

        return SET_DURATION

    @staticmethod
    async def set_duration_and_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קביעת משך זמן ויצירת המכרז"""
        query = update.callback_query
        await query.answer()

        if query.data == "cancel":
            await query.edit_message_text("❌ ביטול יצירת מכרז")
            return ConversationHandler.END

        duration_hours = int(query.data.split("_")[-1])

        user_id = update.effective_user.id
        coupon_id = context.user_data.get("auction_coupon_id")
        starting_price = context.user_data.get("auction_starting_price")

        # יצירת המכרז
        auction_id, error = await AuctionService.create_auction(
            seller_id=user_id,
            coupon_id=coupon_id,
            starting_price=starting_price,
            duration_hours=duration_hours
        )

        if error:
            await query.edit_message_text(f"❌ {error}")
            return ConversationHandler.END

        end_time = datetime.utcnow() + timedelta(hours=duration_hours)

        await query.edit_message_text(
            f"✅ *מכרז נוצר בהצלחה!*\n\n"
            f"💰 מחיר התחלתי: {starting_price:.2f}₪\n"
            f"⏰ זמן סיום: {end_time.strftime('%d/%m %H:%M')}\n\n"
            f"המכרז מופיע כעת ברשימת המכרזים הפעילים!",
            parse_mode="Markdown"
        )

        return ConversationHandler.END

    @staticmethod
    async def my_auctions(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """המכרזים שלי (למוכרים)"""
        user_id = update.effective_user.id

        auctions = await AuctionService.get_seller_auctions(user_id)

        if not auctions:
            await update.message.reply_text(
                "📭 אין לך מכרזים\n\n"
                "💡 תוכל ליצור מכרז על ידי שליחת /create_auction"
            )
            return

        text = "🎪 *המכרזים שלי*\n\n"

        for i, auction in enumerate(auctions[:10], 1):
            coupon = auction.get("coupon", {})
            status_emoji = {
                "active": "🟢",
                "ended": "⏹️",
                "cancelled": "❌"
            }.get(auction["status"], "❓")

            text += f"{status_emoji} *{coupon.get('title', 'קופון')}*\n"
            text += f"   מחיר נוכחי: {auction['current_price']:.2f}₪\n"
            text += f"   הצעות: {auction.get('bid_count', 0)}\n"

            if auction["status"] == "active":
                time_left = auction["end_time"] - datetime.utcnow()
                hours_left = int(time_left.total_seconds() // 3600)
                text += f"   נותרו: {hours_left}ש'\n"

            if auction.get("winner_id"):
                text += f"   🏆 זוכה: משתמש {auction['winner_id']}\n"

            text += "\n"

        keyboard = [[InlineKeyboardButton("➕ יצירת מכרז חדש", callback_data="create_auction_start")]]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    @staticmethod
    async def my_bids(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ההצעות שלי (לקונים)"""
        user_id = update.effective_user.id

        bids = await AuctionService.get_user_bids(user_id)

        if not bids:
            await update.message.reply_text(
                "📭 אין לך הצעות במכרזים\n\n"
                "💡 צפה במכרזים הפעילים: /auctions"
            )
            return

        text = "💸 *ההצעות שלי*\n\n"

        for i, bid in enumerate(bids[:10], 1):
            auction = bid.get("auction", {})
            coupon = bid.get("coupon", {})
            is_leading = auction.get("current_bidder_id") == user_id

            status_emoji = "🏆" if is_leading else "📊"

            text += f"{status_emoji} *{coupon.get('title', 'קופון')}*\n"
            text += f"   ההצעה שלי: {bid['amount']:.2f}₪\n"
            text += f"   מחיר נוכחי: {auction.get('current_price', 0):.2f}₪\n"

            if auction.get("status") == "active":
                if is_leading:
                    text += "   ✅ מוביל במכרז!\n"
                else:
                    text += "   ⚠️ עוקפו אותך\n"

            text += "\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    @staticmethod
    async def cancel_bid_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול שיחה"""
        await update.message.reply_text("❌ פעולה בוטלה")
        return ConversationHandler.END


def get_auction_handlers():
    """החזרת handlers למכרזים"""

    # Conversation handler ליצירת מכרז
    create_auction_conv = ConversationHandler(
        entry_points=[
            CommandHandler("create_auction", AuctionHandlers.create_auction_start),
            CallbackQueryHandler(AuctionHandlers.create_auction_start, pattern="^create_auction_start$")
        ],
        states={
            SELECT_AUCTION_COUPON: [
                CallbackQueryHandler(AuctionHandlers.select_coupon_for_auction)
            ],
            SET_STARTING_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, AuctionHandlers.set_starting_price)
            ],
            SET_DURATION: [
                CallbackQueryHandler(AuctionHandlers.set_duration_and_create)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", AuctionHandlers.cancel_bid_conversation)
        ],
    )

    # Conversation handler להצבת הצעה
    bid_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(AuctionHandlers.start_bid, pattern="^auction_bid_")
        ],
        states={
            PLACE_BID_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, AuctionHandlers.process_bid)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", AuctionHandlers.cancel_bid_conversation)
        ],
    )

    return [
        # Commands
        CommandHandler("auctions", AuctionHandlers.view_auctions),
        CommandHandler("my_auctions", AuctionHandlers.my_auctions),
        CommandHandler("my_bids", AuctionHandlers.my_bids),

        # Callbacks
        CallbackQueryHandler(AuctionHandlers.view_auctions, pattern="^view_auctions$"),
        CallbackQueryHandler(AuctionHandlers.view_auctions, pattern="^auctions_page_"),
        CallbackQueryHandler(AuctionHandlers.view_auction_details, pattern="^auction_view_"),
        CallbackQueryHandler(AuctionHandlers.view_bid_history, pattern="^auction_history_"),

        # Conversations
        create_auction_conv,
        bid_conv,
    ]
