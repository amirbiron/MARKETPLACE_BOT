"""
Background Scheduler - משימות רקע אוטומטיות
"""
import asyncio
from datetime import datetime, timedelta
from services.auction_service import AuctionService
from services.favorites_service import FavoritesService
from services.notification_service import NotificationService
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    """מתזמן למשימות רקע"""

    def __init__(self):
        self.running = False
        self.tasks = []

    async def start(self):
        """התחלת המתזמן"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        logger.info("Background scheduler started")

        # יצירת tasks לכל המשימות
        self.tasks = [
            asyncio.create_task(self._check_expired_auctions()),
            asyncio.create_task(self._check_price_drops()),
            asyncio.create_task(self._notify_similar_coupons()),
            asyncio.create_task(self._cleanup_old_notifications()),
            asyncio.create_task(self._check_dispute_deadlines()),
            asyncio.create_task(self._cleanup_favorites()),
            asyncio.create_task(self._check_expired_coupons()),
            asyncio.create_task(self._notify_auction_ending()),
        ]

        logger.info(f"Started {len(self.tasks)} background tasks")

    async def stop(self):
        """עצירת המתזמן"""
        if not self.running:
            return

        self.running = False
        logger.info("Stopping background scheduler...")

        # ביטול כל ה-tasks
        for task in self.tasks:
            task.cancel()

        # המתנה לסיום
        await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks = []
        logger.info("Background scheduler stopped")

    async def _check_expired_auctions(self):
        """בדיקת מכרזים שפג תוקפם - כל 5 דקות"""
        while self.running:
            try:
                logger.debug("Checking expired auctions...")
                count = await AuctionService.check_and_end_expired_auctions()
                if count > 0:
                    logger.info(f"Ended {count} expired auctions")
            except Exception as e:
                logger.error(f"Error checking expired auctions: {e}")

            await asyncio.sleep(300)  # 5 דקות

    async def _check_price_drops(self):
        """בדיקת ירידות מחיר במועדפים - כל שעה"""
        while self.running:
            try:
                logger.debug("Checking price drops...")
                count = await FavoritesService.check_price_drops()
                if count > 0:
                    logger.info(f"Notified {count} users about price drops")
            except Exception as e:
                logger.error(f"Error checking price drops: {e}")

            await asyncio.sleep(3600)  # שעה

    async def _notify_similar_coupons(self):
        """התראה על קופונים דומים - כל 6 שעות"""
        while self.running:
            try:
                logger.debug("Checking similar coupons...")
                count = await FavoritesService.notify_similar_coupons()
                if count > 0:
                    logger.info(f"Notified {count} users about similar coupons")
            except Exception as e:
                logger.error(f"Error notifying similar coupons: {e}")

            await asyncio.sleep(21600)  # 6 שעות

    async def _cleanup_old_notifications(self):
        """ניקוי התראות ישנות - כל יום"""
        while self.running:
            try:
                logger.debug("Cleaning up old notifications...")
                count = await NotificationService.cleanup_old_notifications(days=30)
                if count > 0:
                    logger.info(f"Cleaned up {count} old notifications")
            except Exception as e:
                logger.error(f"Error cleaning up notifications: {e}")

            await asyncio.sleep(86400)  # יום

    async def _check_dispute_deadlines(self):
        """בדיקת תזכורות למועד דיווח על בעיה - כל שעתיים"""
        while self.running:
            try:
                logger.debug("Checking dispute deadlines...")

                # מציאת הזמנות שמתקרבות למועד דיווח (2 שעות לפני)
                warning_time = datetime.utcnow() + timedelta(hours=2)

                orders = await db.orders.find({
                    "status": "completed",
                    "dispute_deadline": {
                        "$gte": datetime.utcnow(),
                        "$lte": warning_time
                    },
                    "notified_deadline": {"$ne": True}
                }).to_list(length=None)

                for order in orders:
                    # חישוב שעות שנותרו
                    time_left = order["dispute_deadline"] - datetime.utcnow()
                    hours_left = int(time_left.total_seconds() // 3600)

                    # שליחת התראה
                    await NotificationService.notify_dispute_deadline(
                        buyer_id=order["buyer_id"],
                        order_id=str(order["_id"]),
                        hours_left=hours_left
                    )

                    # סימון שנשלחה התראה
                    await db.orders.update_one(
                        {"_id": order["_id"]},
                        {"$set": {"notified_deadline": True}}
                    )

                if orders:
                    logger.info(f"Sent {len(orders)} dispute deadline reminders")

            except Exception as e:
                logger.error(f"Error checking dispute deadlines: {e}")

            await asyncio.sleep(7200)  # 2 שעות

    async def _cleanup_favorites(self):
        """ניקוי מועדפים של קופונים שנמחקו - כל יום"""
        while self.running:
            try:
                logger.debug("Cleaning up favorites...")
                count = await FavoritesService.cleanup_deleted_coupons()
                if count > 0:
                    logger.info(f"Cleaned up {count} deleted favorites")
            except Exception as e:
                logger.error(f"Error cleaning up favorites: {e}")

            await asyncio.sleep(86400)  # יום

    async def _check_expired_coupons(self):
        """בדיקת קופונים שפג תוקפם - כל יום"""
        while self.running:
            try:
                logger.debug("Checking expired coupons...")

                # מציאת קופונים שפג תוקפם
                expired = await db.coupons.find({
                    "status": "active",
                    "expires_at": {"$lt": datetime.utcnow()}
                }).to_list(length=None)

                for coupon in expired:
                    await db.coupons.update_one(
                        {"_id": coupon["_id"]},
                        {"$set": {"status": "expired"}}
                    )

                if expired:
                    logger.info(f"Marked {len(expired)} coupons as expired")

            except Exception as e:
                logger.error(f"Error checking expired coupons: {e}")

            await asyncio.sleep(86400)  # יום

    async def _notify_auction_ending(self):
        """התראה על מכרזים שמסתיימים בקרוב - כל שעה"""
        while self.running:
            try:
                logger.debug("Checking auctions ending soon...")

                # מציאת מכרזים שמסתיימים בעוד 2 שעות
                warning_time = datetime.utcnow() + timedelta(hours=2)

                auctions = await db.auctions.find({
                    "status": "active",
                    "end_time": {
                        "$gte": datetime.utcnow(),
                        "$lte": warning_time
                    },
                    "notified_ending": {"$ne": True}
                }).to_list(length=None)

                for auction in auctions:
                    # התראה למוביל הנוכחי
                    if auction.get("current_bidder_id"):
                        time_left = auction["end_time"] - datetime.utcnow()
                        hours_left = int(time_left.total_seconds() // 3600)

                        await NotificationService.notify_auction_ending_soon(
                            user_id=auction["current_bidder_id"],
                            auction_id=str(auction["_id"]),
                            hours_left=hours_left
                        )

                    # סימון שנשלחה התראה
                    await db.auctions.update_one(
                        {"_id": auction["_id"]},
                        {"$set": {"notified_ending": True}}
                    )

                if auctions:
                    logger.info(f"Sent {len(auctions)} auction ending notifications")

            except Exception as e:
                logger.error(f"Error notifying auction ending: {e}")

            await asyncio.sleep(3600)  # שעה


# יצירת instance גלובלי
scheduler = BackgroundScheduler()
