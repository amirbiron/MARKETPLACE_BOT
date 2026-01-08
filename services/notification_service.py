"""
שירות ניהול התראות למשתמשים
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """שירות לניהול התראות"""

    @staticmethod
    async def send_notification(
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "general",
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        שליחת התראה למשתמש

        Returns:
            notification_id או None
        """
        try:
            notification_data = {
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "data": data or {},
                "read": False,
                "created_at": datetime.utcnow()
            }

            result = await db.notifications.insert_one(notification_data)

            # שליחה גם דרך טלגרם
            try:
                from telegram import Bot
                bot = Bot(Config.BOT_TOKEN)

                text = f"🔔 *{title}*\n\n{message}"
                await bot.send_message(user_id, text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to send telegram notification: {e}")

            logger.info(f"Notification sent to {user_id}: {title}")
            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return None

    @staticmethod
    async def get_user_notifications(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """קבלת התראות של משתמש"""
        try:
            cursor = db.notifications.find({
                "user_id": user_id
            }).sort("created_at", -1).limit(limit)

            notifications = await cursor.to_list(length=None)
            return notifications

        except Exception as e:
            logger.error(f"Error getting user notifications: {e}")
            return []

    @staticmethod
    async def mark_as_read(notification_id: str, user_id: int) -> bool:
        """סימון התראה כנקראה"""
        try:
            result = await db.notifications.update_one(
                {
                    "_id": ObjectId(notification_id),
                    "user_id": user_id
                },
                {
                    "$set": {
                        "read": True,
                        "read_at": datetime.utcnow()
                    }
                }
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False

    @staticmethod
    async def mark_all_as_read(user_id: int) -> int:
        """סימון כל ההתראות כנקראו"""
        try:
            result = await db.notifications.update_many(
                {
                    "user_id": user_id,
                    "read": False
                },
                {
                    "$set": {
                        "read": True,
                        "read_at": datetime.utcnow()
                    }
                }
            )

            return result.modified_count

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return 0

    @staticmethod
    async def get_unread_count(user_id: int) -> int:
        """קבלת מספר התראות שלא נקראו"""
        try:
            count = await db.notifications.count_documents({
                "user_id": user_id,
                "read": False
            })

            return count

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    @staticmethod
    async def delete_notification(notification_id: str, user_id: int) -> bool:
        """מחיקת התראה"""
        try:
            result = await db.notifications.delete_one({
                "_id": ObjectId(notification_id),
                "user_id": user_id
            })

            return result.deleted_count > 0

        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return False

    # ===== התראות ספציפיות =====

    @staticmethod
    async def notify_new_sale(seller_id: int, order_id: str, amount: float):
        """התראה על מכירה חדשה"""
        await NotificationService.send_notification(
            user_id=seller_id,
            title="💰 מכירה חדשה!",
            message=f"מזל טוב! מכרת קופון בסכום {amount:.2f}₪",
            notification_type="sale",
            data={"order_id": order_id}
        )

    @staticmethod
    async def notify_new_purchase(buyer_id: int, order_id: str, coupon_title: str):
        """התראה על רכישה חדשה"""
        await NotificationService.send_notification(
            user_id=buyer_id,
            title="✅ רכישה הושלמה!",
            message=f"רכשת את '{coupon_title}' בהצלחה",
            notification_type="purchase",
            data={"order_id": order_id}
        )

    @staticmethod
    async def notify_auction_won(winner_id: int, auction_id: str, price: float):
        """התראה על זכייה במכרז"""
        await NotificationService.send_notification(
            user_id=winner_id,
            title="🎉 ניצחת במכרז!",
            message=f"ניצחת במכרז במחיר {price:.2f}₪!",
            notification_type="auction_won",
            data={"auction_id": auction_id}
        )

    @staticmethod
    async def notify_auction_outbid(user_id: int, auction_id: str, new_price: float):
        """התראה על עקיפה במכרז"""
        await NotificationService.send_notification(
            user_id=user_id,
            title="⚠️ עוקפו אותך במכרז",
            message=f"המחיר החדש: {new_price:.2f}₪",
            notification_type="auction_outbid",
            data={"auction_id": auction_id}
        )

    @staticmethod
    async def notify_auction_ending_soon(user_id: int, auction_id: str, minutes_left: int, is_leading: bool = False):
        """התראה על סיום מכרז קרוב - עם כפתורים"""
        try:
            from telegram import Bot
            from keyboards import Keyboards
            bot = Bot(Config.BOT_TOKEN)

            if minutes_left >= 60:
                time_text = f"{minutes_left // 60} שעות"
            else:
                time_text = f"{minutes_left} דקות"

            if is_leading:
                title = f"⏰ המכרז שאתה מוביל מסתיים בעוד {time_text}"
                message = "שמור על המיקום שלך - אחרים עשויים להגדיל!"
            else:
                title = f"⏰ המכרז מסתיים בעוד {time_text}"
                message = "זה הזמן להגדיל את ההצעה ולנצח!"

            # שמירה בDB
            notification_data = {
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": "auction_ending",
                "data": {"auction_id": auction_id, "minutes_left": minutes_left},
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification_data)

            # שליחה עם כפתורים
            keyboard = Keyboards.auction_ending_keyboard(auction_id)
            text = f"🔔 *{title}*\n\n{message}"
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

            logger.info(f"Auction ending notification sent to {user_id}")

        except Exception as e:
            logger.error(f"Error sending auction ending notification: {e}")

    @staticmethod
    async def notify_dispute_deadline(buyer_id: int, order_id: str, hours_left: int):
        """התראה על קרבת מועד דיווח על בעיה - עם כפתורי אישור ודיווח"""
        await NotificationService.notify_report_window_closing(
            buyer_id=buyer_id,
            order_id=order_id,
            hours_left=hours_left
        )

    @staticmethod
    async def notify_report_window_closing(buyer_id: int, order_id: str, hours_left: int):
        """התראה 2 שעות לפני סגירת חלון דיווח - עם כפתורי אישור ודיווח"""
        try:
            from telegram import Bot
            from keyboards import Keyboards
            bot = Bot(Config.BOT_TOKEN)

            # קבלת פרטי ההזמנה
            from bson import ObjectId
            order = await db.orders.find_one({"_id": ObjectId(order_id)})
            coupon_title = "הקופון"
            if order:
                coupon = await db.coupons.find_one({"_id": order.get("coupon_id")})
                if coupon:
                    coupon_title = coupon.get("title", "הקופון")

            title = f"⚠️ נותרו {hours_left} שעות לדיווח על בעיה"
            message = (
                f"חלון הדיווח על '{coupon_title}' עומד להיסגר!\n\n"
                f"🕐 נותרו לך {hours_left} שעות לדווח על בעיה.\n"
                f"לאחר מכן, העסקה תושלם אוטומטית.\n\n"
                f"✅ אם הקופון תקין - לחץ 'אשר קופון'\n"
                f"🚨 אם יש בעיה - לחץ 'דווח על בעיה'"
            )

            # שמירה בDB
            notification_data = {
                "user_id": buyer_id,
                "title": title,
                "message": message,
                "type": "report_window_closing",
                "data": {"order_id": order_id, "hours_left": hours_left},
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification_data)

            # שליחה עם כפתורים
            keyboard = Keyboards.report_window_keyboard(order_id)
            text = f"🔔 *{title}*\n\n{message}"
            await bot.send_message(buyer_id, text, reply_markup=keyboard, parse_mode="Markdown")

            logger.info(f"Report window closing notification sent to {buyer_id} for order {order_id}")

        except Exception as e:
            logger.error(f"Error sending report window closing notification: {e}")

    @staticmethod
    async def notify_new_message(user_id: int, sender_name: str, chat_id: str):
        """התראה על הודעה חדשה"""
        await NotificationService.send_notification(
            user_id=user_id,
            title=f"💬 הודעה חדשה מ-{sender_name}",
            message="יש לך הודעה חדשה בצ'אט",
            notification_type="message",
            data={"chat_id": chat_id}
        )

    @staticmethod
    async def notify_price_drop(user_id: int, coupon_id: str, coupon_title: str, old_price: float, new_price: float):
        """התראה על ירידת מחיר בקופון מועדף"""
        discount_pct = ((old_price - new_price) / old_price) * 100

        await NotificationService.send_notification(
            user_id=user_id,
            title=f"📉 ירידת מחיר ב'{coupon_title}'",
            message=f"המחיר ירד ב-{discount_pct:.0f}%! {old_price:.2f}₪ → {new_price:.2f}₪",
            notification_type="price_drop",
            data={"coupon_id": coupon_id}
        )

    @staticmethod
    async def notify_similar_coupon(user_id: int, coupon_id: str, coupon_title: str, category: str):
        """התראה על קופון דומה למועדפים"""
        await NotificationService.send_notification(
            user_id=user_id,
            title=f"✨ קופון חדש בקטגוריה {category}",
            message=f"נוסף קופון חדש: '{coupon_title}' שאולי יעניין אותך",
            notification_type="similar_coupon",
            data={"coupon_id": coupon_id}
        )

    @staticmethod
    async def notify_review_received(seller_id: int, rating: int, buyer_name: str):
        """התראה על קבלת דירוג"""
        stars = "⭐" * rating

        await NotificationService.send_notification(
            user_id=seller_id,
            title="⭐ דירוג חדש!",
            message=f"{buyer_name} דירג אותך: {stars}",
            notification_type="review",
            data={"rating": rating}
        )

    @staticmethod
    async def notify_payout_approved(seller_id: int, amount: float):
        """התראה על אישור משיכה"""
        await NotificationService.send_notification(
            user_id=seller_id,
            title="✅ משיכה אושרה!",
            message=f"משיכת {amount:.2f}₪ אושרה והועברה",
            notification_type="payout_approved",
            data={"amount": amount}
        )

    @staticmethod
    async def notify_seller_approved(seller_id: int):
        """התראה על אישור מוכר"""
        await NotificationService.send_notification(
            user_id=seller_id,
            title="🎉 אושרת כמוכר!",
            message="בקשתך להיות מוכר אושרה! כעת תוכל להעלות קופונים",
            notification_type="seller_approved"
        )

    @staticmethod
    async def notify_seller_rejected(seller_id: int, reason: Optional[str] = None):
        """התראה על דחיית מוכר"""
        message = "בקשתך להיות מוכר נדחתה"
        if reason:
            message += f"\nסיבה: {reason}"

        await NotificationService.send_notification(
            user_id=seller_id,
            title="❌ בקשה נדחתה",
            message=message,
            notification_type="seller_rejected"
        )

    @staticmethod
    async def notify_dispute_resolved(user_id: int, order_id: str, resolution: str):
        """התראה על פתרון מחלוקת"""
        await NotificationService.send_notification(
            user_id=user_id,
            title="✅ מחלוקת נפתרה",
            message=f"המחלוקת נפתרה: {resolution}",
            notification_type="dispute_resolved",
            data={"order_id": order_id}
        )

    @staticmethod
    async def notify_favorite_expiring(user_id: int, coupon_id: str, coupon_title: str, days_left: int):
        """התראה על פקיעת תוקף קופון במועדפים"""
        if days_left == 1:
            time_text = "מחר"
        else:
            time_text = f"בעוד {days_left} ימים"

        await NotificationService.send_notification(
            user_id=user_id,
            title=f"⏰ קופון במועדפים פג תוקף {time_text}",
            message=f"הקופון '{coupon_title}' שבמועדפים שלך עומד לפוג!\n\nכדאי לקנות אותו לפני שייגמר.",
            notification_type="favorite_expiring",
            data={"coupon_id": coupon_id, "days_left": days_left}
        )

    @staticmethod
    async def cleanup_old_notifications(days: int = 30):
        """ניקוי התראות ישנות - לרוץ ב-background"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            result = await db.notifications.delete_many({
                "created_at": {"$lt": cutoff_date},
                "read": True
            })

            logger.info(f"Deleted {result.deleted_count} old notifications")
            return result.deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up notifications: {e}")
            return 0
