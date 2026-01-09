"""
Background Scheduler - משימות רקע אוטומטיות
"""
import asyncio
from datetime import datetime, timedelta
from services.auction_service import AuctionService
from services.favorites_service import FavoritesService
from services.notification_service import NotificationService
from services.fraud_detection_service import FraudDetectionService
from services.escrow_service import EscrowService
from services.payment_gateway_service import PaymentGatewayService
from services.analytics_service import AnalyticsService
from services.coupon_service import CouponService
from database import db
from config import Config
import logging

# Import P2P timeout processor (only if classifieds model is enabled)
try:
    from handlers.p2p_handlers import process_p2p_timeouts
except ImportError:
    process_p2p_timeouts = None

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
            asyncio.create_task(self._notify_expiring_coupons()),
            asyncio.create_task(self._notify_expiring_favorites()),
            # Anti-Fraud Tasks
            asyncio.create_task(self._run_fraud_detection()),
            asyncio.create_task(self._check_duplicate_coupons()),
            asyncio.create_task(self._update_trust_scores()),
            # Escrow Tasks
            asyncio.create_task(self._process_escrow_releases()),
            asyncio.create_task(self._escrow_daily_reconciliation()),
            # Payment Gateway Tasks
            asyncio.create_task(self._expire_old_payment_transactions()),
            # Seller Dashboard Tasks
            asyncio.create_task(self._record_daily_analytics()),
            asyncio.create_task(self._publish_scheduled_coupons()),
            asyncio.create_task(self._send_seller_daily_summaries()),
        ]
        
        # Classifieds Model (P2P) Tasks - conditional
        if Config.CLASSIFIEDS_MODEL_ENABLED and process_p2p_timeouts:
            self.tasks.append(asyncio.create_task(self._check_p2p_timeouts()))
            logger.info("P2P timeout task enabled (Classifieds Model)")

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
        """בדיקת תזכורות למועד דיווח על בעיה - כל 30 דקות"""
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
                    hours_left = max(1, int(time_left.total_seconds() // 3600))

                    # שליחת התראה עם כפתורים
                    await NotificationService.notify_report_window_closing(
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
                    logger.info(f"Sent {len(orders)} report window closing reminders")

            except Exception as e:
                logger.error(f"Error checking dispute deadlines: {e}")

            await asyncio.sleep(1800)  # 30 דקות

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
        """התראה על מכרזים שמסתיימים בקרוב - כל 15 דקות"""
        while self.running:
            try:
                logger.debug("Checking auctions ending soon...")

                # === התראה 2 שעות לפני סיום ===
                warning_time_2h = datetime.utcnow() + timedelta(hours=2)

                auctions_2h = await db.auctions.find({
                    "status": "active",
                    "end_time": {
                        "$gte": datetime.utcnow(),
                        "$lte": warning_time_2h
                    },
                    "notified_ending_2h": {"$ne": True}
                }).to_list(length=None)

                for auction in auctions_2h:
                    time_left = auction["end_time"] - datetime.utcnow()
                    minutes_left = int(time_left.total_seconds() // 60)

                    # קבלת כל המשתתפים במכרז (כל מי שהציע)
                    bidders = await db.auction_bids.distinct(
                        "bidder_id",
                        {"auction_id": auction["_id"]}
                    )

                    current_leader = auction.get("current_bidder_id")

                    # התראה לכל המשתתפים
                    for bidder_id in bidders:
                        is_leading = (bidder_id == current_leader)
                        await NotificationService.notify_auction_ending_soon(
                            user_id=bidder_id,
                            auction_id=str(auction["_id"]),
                            minutes_left=minutes_left,
                            is_leading=is_leading
                        )

                    # סימון שנשלחה התראה 2 שעות
                    await db.auctions.update_one(
                        {"_id": auction["_id"]},
                        {"$set": {"notified_ending_2h": True}}
                    )

                if auctions_2h:
                    logger.info(f"Sent 2-hour auction ending notifications for {len(auctions_2h)} auctions")

                # === התראה 30 דקות לפני סיום ===
                warning_time_30m = datetime.utcnow() + timedelta(minutes=30)

                auctions_30m = await db.auctions.find({
                    "status": "active",
                    "end_time": {
                        "$gte": datetime.utcnow(),
                        "$lte": warning_time_30m
                    },
                    "notified_ending_30m": {"$ne": True}
                }).to_list(length=None)

                for auction in auctions_30m:
                    time_left = auction["end_time"] - datetime.utcnow()
                    minutes_left = int(time_left.total_seconds() // 60)

                    # קבלת כל המשתתפים במכרז
                    bidders = await db.auction_bids.distinct(
                        "bidder_id",
                        {"auction_id": auction["_id"]}
                    )

                    current_leader = auction.get("current_bidder_id")

                    # התראה לכל המשתתפים
                    for bidder_id in bidders:
                        is_leading = (bidder_id == current_leader)
                        await NotificationService.notify_auction_ending_soon(
                            user_id=bidder_id,
                            auction_id=str(auction["_id"]),
                            minutes_left=minutes_left,
                            is_leading=is_leading
                        )

                    # סימון שנשלחה התראה 30 דקות
                    await db.auctions.update_one(
                        {"_id": auction["_id"]},
                        {"$set": {"notified_ending_30m": True}}
                    )

                if auctions_30m:
                    logger.info(f"Sent 30-minute auction ending notifications for {len(auctions_30m)} auctions")

            except Exception as e:
                logger.error(f"Error notifying auction ending: {e}")

            await asyncio.sleep(900)  # 15 דקות

    async def _notify_expiring_coupons(self):
        """התראה למוכרים על קופונים שעומדים לפוג - כל 12 שעות"""
        while self.running:
            try:
                logger.debug("Checking expiring coupons...")

                # מציאת קופונים שפוגים בעוד 3 ימים או פחות
                expiry_warning_time = datetime.utcnow() + timedelta(days=3)

                coupons = await db.coupons.find({
                    "status": "active",
                    "expires_at": {
                        "$gte": datetime.utcnow(),
                        "$lte": expiry_warning_time
                    },
                    "notified_expiring": {"$ne": True}
                }).to_list(length=None)

                for coupon in coupons:
                    # חישוב ימים שנותרו
                    time_left = coupon["expires_at"] - datetime.utcnow()
                    days_left = int(time_left.total_seconds() // 86400)

                    # שליחת התראה למוכר
                    await NotificationService.send_notification(
                        user_id=coupon["seller_id"],
                        title="⚠️ קופון עומד לפוג",
                        message=f"הקופון '{coupon.get('title', 'ללא שם')}' יפוג בעוד {days_left} ימים!\n\n"
                                f"שקול להאריך את תוקפו או לעדכן את המחיר.",
                        notification_type="coupon_expiring",
                        data={
                            "coupon_id": str(coupon["_id"]),
                            "days_left": days_left
                        }
                    )

                    # סימון שנשלחה התראה
                    await db.coupons.update_one(
                        {"_id": coupon["_id"]},
                        {"$set": {"notified_expiring": True}}
                    )

                if coupons:
                    logger.info(f"Sent {len(coupons)} coupon expiry notifications to sellers")

            except Exception as e:
                logger.error(f"Error notifying expiring coupons: {e}")

            await asyncio.sleep(43200)  # 12 שעות


    async def _notify_expiring_favorites(self):
        """התראה למשתמשים על קופונים במועדפים שעומדים לפוג - כל 12 שעות"""
        while self.running:
            try:
                logger.debug("Checking expiring favorites...")
                count = await FavoritesService.notify_expiring_favorites()
                if count > 0:
                    logger.info(f"Notified {count} users about expiring favorites")
            except Exception as e:
                logger.error(f"Error notifying expiring favorites: {e}")

            await asyncio.sleep(43200)  # 12 שעות

    # ==================== Anti-Fraud Tasks ====================

    async def _run_fraud_detection(self):
        """הרצת בדיקות הונאה תקופתיות - כל 6 שעות"""
        while self.running:
            try:
                logger.info("Running periodic fraud detection...")
                result = await FraudDetectionService.run_periodic_checks()
                
                if result and not result.get("error"):
                    logger.info(
                        f"Fraud detection completed: "
                        f"{result.get('checked', 0)} checked, "
                        f"{result.get('flagged', 0)} flagged, "
                        f"{result.get('blocked', 0)} blocked"
                    )
                elif result and result.get("error"):
                    logger.error(f"Fraud detection error: {result['error']}")
                    
            except Exception as e:
                logger.error(f"Error running fraud detection: {e}")

            await asyncio.sleep(21600)  # 6 שעות

    async def _check_duplicate_coupons(self):
        """בדיקת קופונים כפולים - כל 12 שעות"""
        while self.running:
            try:
                logger.debug("Checking for duplicate coupons...")
                duplicates = await FraudDetectionService.check_all_duplicate_coupons()
                
                if duplicates > 0:
                    logger.warning(f"Found {duplicates} duplicate coupon codes")
                    
            except Exception as e:
                logger.error(f"Error checking duplicate coupons: {e}")

            await asyncio.sleep(43200)  # 12 שעות

    async def _update_trust_scores(self):
        """עדכון ניקוד אמינות לכל המוכרים - כל יום"""
        while self.running:
            try:
                logger.info("Updating trust scores for all sellers...")
                
                # מציאת כל המוכרים הפעילים
                sellers = await db.users.find({
                    "role": {"$in": ["seller_verified", "seller_unverified"]},
                    "blocked": {"$ne": True}
                }).to_list(length=None)
                
                updated = 0
                for seller in sellers:
                    try:
                        await FraudDetectionService.calculate_trust_score(seller["user_id"])
                        updated += 1
                    except Exception as e:
                        logger.warning(f"Failed to update trust score for seller {seller['user_id']}: {e}")
                
                logger.info(f"Updated trust scores for {updated} sellers")
                
            except Exception as e:
                logger.error(f"Error updating trust scores: {e}")

            await asyncio.sleep(86400)  # יום

    # ==================== Escrow Tasks ====================

    async def _process_escrow_releases(self):
        """
        שחרור אוטומטי של כספים מ-Escrow - כל 15 דקות
        
        מחפש עסקאות Escrow שעבר זמן ההמתנה שלהן (24 שעות)
        ומשחרר את הכספים אוטומטית למוכרים
        """
        while self.running:
            try:
                logger.debug("Processing escrow auto-releases...")
                
                released_count = await EscrowService.process_auto_releases()
                
                if released_count > 0:
                    logger.info(f"Auto-released {released_count} escrow transactions to sellers")
                    
            except Exception as e:
                logger.error(f"Error processing escrow releases: {e}")

            await asyncio.sleep(900)  # 15 דקות

    async def _escrow_daily_reconciliation(self):
        """
        דוח התאמה יומי ל-Escrow - כל יום בחצות
        
        מייצר דוח התאמה יומי ושולח התראה לאדמינים
        אם יש חוסר התאמה
        """
        while self.running:
            try:
                logger.info("Running daily escrow reconciliation...")
                
                # קבלת דוח יומי
                report = await EscrowService.get_daily_reconciliation_report()
                
                # בדיקת חוסר התאמה
                net_change = report.get("net_change", 0)
                current_balance = report.get("current_balance", 0)
                
                logger.info(
                    f"Escrow daily report: "
                    f"in={report.get('funds_in', {}).get('total', 0):.2f}, "
                    f"out={report.get('total_out', 0):.2f}, "
                    f"net={net_change:.2f}, "
                    f"balance={current_balance:.2f}"
                )
                
                # אפשר להוסיף כאן שליחת התראות לאדמינים אם יש בעיות
                
            except Exception as e:
                logger.error(f"Error in escrow daily reconciliation: {e}")

            await asyncio.sleep(86400)  # יום

    # ==================== Payment Gateway Tasks ====================

    async def _expire_old_payment_transactions(self):
        """
        סימון עסקאות תשלום שפג תוקפן - כל 10 דקות
        
        עסקאות שלא הושלמו בזמן הקצוב מסומנות כ-expired
        """
        while self.running:
            try:
                logger.debug("Checking for expired payment transactions...")
                
                expired_count = await PaymentGatewayService.expire_old_transactions()
                
                if expired_count > 0:
                    logger.info(f"Expired {expired_count} old payment transactions")
                    
            except Exception as e:
                logger.error(f"Error expiring payment transactions: {e}")

            await asyncio.sleep(600)  # 10 דקות

    # ==================== Seller Dashboard Tasks ====================

    async def _record_daily_analytics(self):
        """
        תיעוד אנליטיקס יומי לכל המוכרים - כל יום בחצות
        
        שומר נתונים היסטוריים לגרפים ודוחות
        """
        while self.running:
            try:
                logger.info("Recording daily analytics for sellers...")
                
                # מציאת כל המוכרים הפעילים
                sellers = await db.users.find({
                    "role": {"$in": ["seller_verified", "seller_unverified"]},
                    "blocked": {"$ne": True}
                }).to_list(length=None)
                
                recorded = 0
                for seller in sellers:
                    try:
                        await AnalyticsService.record_daily_analytics(seller["user_id"])
                        recorded += 1
                    except Exception as e:
                        logger.warning(f"Failed to record analytics for seller {seller['user_id']}: {e}")
                
                logger.info(f"Recorded daily analytics for {recorded} sellers")
                
            except Exception as e:
                logger.error(f"Error recording daily analytics: {e}")

            await asyncio.sleep(86400)  # יום

    async def _publish_scheduled_coupons(self):
        """
        פרסום קופונים מתוזמנים - כל 5 דקות
        
        מחפש קופונים שהגיע זמן הפרסום שלהם ומפרסם אותם
        """
        while self.running:
            try:
                logger.debug("Checking for scheduled coupons to publish...")
                
                now = datetime.utcnow()
                
                # מציאת קופונים מתוזמנים שהגיע זמנם
                scheduled = await db.scheduled_coupons.find({
                    "status": "pending",
                    "scheduled_at": {"$lte": now}
                }).to_list(length=None)
                
                published = 0
                for item in scheduled:
                    try:
                        coupon_data = item.get("coupon_data", {})
                        
                        # יצירת הקופון
                        coupon = await CouponService.create_coupon(
                            seller_id=item["seller_id"],
                            title=coupon_data.get("title", "קופון"),
                            category=coupon_data.get("category", "אחר"),
                            original_price=coupon_data.get("original_price", 0),
                            sale_price=coupon_data.get("sale_price", 0),
                            description=coupon_data.get("description"),
                            digital_code=coupon_data.get("digital_code"),
                            expires_at=coupon_data.get("expires_at")
                        )
                        
                        if coupon:
                            # עדכון הסטטוס
                            await db.scheduled_coupons.update_one(
                                {"_id": item["_id"]},
                                {
                                    "$set": {
                                        "status": "published",
                                        "published_coupon_id": coupon._id,
                                        "published_at": now
                                    }
                                }
                            )
                            
                            # שליחת התראה למוכר
                            await NotificationService.send_notification(
                                user_id=item["seller_id"],
                                title="✅ קופון מתוזמן פורסם",
                                message=f"הקופון '{coupon.title}' פורסם בהצלחה כמתוכנן!",
                                notification_type="scheduled_published"
                            )
                            
                            published += 1
                        else:
                            # סימון ככושל
                            await db.scheduled_coupons.update_one(
                                {"_id": item["_id"]},
                                {"$set": {"status": "failed", "error": "Failed to create coupon"}}
                            )
                            
                    except Exception as e:
                        logger.error(f"Failed to publish scheduled coupon {item['_id']}: {e}")
                        await db.scheduled_coupons.update_one(
                            {"_id": item["_id"]},
                            {"$set": {"status": "failed", "error": str(e)}}
                        )
                
                if published > 0:
                    logger.info(f"Published {published} scheduled coupons")
                    
            except Exception as e:
                logger.error(f"Error publishing scheduled coupons: {e}")

            await asyncio.sleep(300)  # 5 דקות

    async def _send_seller_daily_summaries(self):
        """
        שליחת סיכומים יומיים למוכרים שהפעילו - כל יום בשעה 8 בבוקר
        """
        while self.running:
            try:
                logger.debug("Checking for daily summary notifications...")
                
                # בדיקה אם השעה היא 8 בבוקר (בערך)
                current_hour = datetime.utcnow().hour
                
                if current_hour == 8:  # 8 UTC
                    logger.info("Sending daily summaries to sellers...")
                    
                    # מציאת מוכרים שהפעילו סיכום יומי
                    settings = await db.seller_alert_settings.find({
                        "daily_summary": True
                    }).to_list(length=None)
                    
                    sent = 0
                    for setting in settings:
                        try:
                            seller_id = setting["seller_id"]
                            
                            # קבלת סטטיסטיקות אתמול
                            yesterday_stats = await AnalyticsService.get_sales_by_period(seller_id, "day")
                            
                            if yesterday_stats.get("total_sales", 0) > 0 or True:  # שלח גם אם אין מכירות
                                # יצירת סיכום
                                summary = f"""
📊 *סיכום יומי*

📅 תאריך: {datetime.utcnow().strftime('%d/%m/%Y')}

💰 מכירות אתמול:
• סה"כ: {yesterday_stats.get('total_sales', 0)}
• הכנסות נטו: {yesterday_stats.get('total_revenue', 0):.2f}₪

בהצלחה היום! 🚀
"""
                                
                                await NotificationService.send_notification(
                                    user_id=seller_id,
                                    title="📊 סיכום יומי",
                                    message=summary,
                                    notification_type="daily_summary"
                                )
                                sent += 1
                                
                        except Exception as e:
                            logger.warning(f"Failed to send daily summary to seller {setting.get('seller_id')}: {e}")
                    
                    if sent > 0:
                        logger.info(f"Sent daily summaries to {sent} sellers")
                    
                    # המתנה 23 שעות כדי לא לשלוח שוב
                    await asyncio.sleep(82800)  # 23 שעות
                else:
                    # בדיקה כל שעה
                    await asyncio.sleep(3600)  # שעה
                    
            except Exception as e:
                logger.error(f"Error sending daily summaries: {e}")
                await asyncio.sleep(3600)  # שעה

    # ==================== Classifieds Model (P2P) Tasks ====================

    async def _check_p2p_timeouts(self):
        """
        בדיקת הזמנות P2P שעברו timeout (מוכר לא אישר בזמן) - כל 10 דקות
        
        מעביר הזמנות לסטטוס מחלוקת אוטומטית ומתריע לאדמינים
        """
        # Wait a bit for bot to initialize
        await asyncio.sleep(60)
        
        while self.running:
            try:
                logger.debug("Checking P2P seller confirmation timeouts...")
                
                # Need bot instance to send notifications
                # We'll import the function and get bot from application
                from telegram.ext import Application
                from handlers.p2p_handlers import process_p2p_timeouts
                
                # The process_p2p_timeouts function requires a bot instance
                # We can't call it directly here without the bot
                # Instead, we'll handle timeouts directly in this task
                
                from datetime import datetime
                from models import P2POrderStatus
                import database
                
                p2p_orders = await database.get_p2p_orders_collection()
                now = datetime.utcnow()
                
                # Find orders that exceeded confirmation deadline
                cursor = p2p_orders.find({
                    "status": P2POrderStatus.PENDING_SELLER_CONFIRMATION.value,
                    "seller_confirmation_deadline": {"$lte": now}
                })
                
                timed_out_orders = await cursor.to_list(length=None)
                processed = 0
                
                for order_data in timed_out_orders:
                    order_id = order_data["_id"]
                    seller_id = order_data["seller_id"]
                    buyer_id = order_data["buyer_id"]
                    
                    # Update to auto-dispute status
                    await p2p_orders.update_one(
                        {"_id": order_id},
                        {
                            "$set": {
                                "status": P2POrderStatus.AUTO_DISPUTE.value,
                                "dispute_opened_at": now,
                                "dispute_reason": "timeout - המוכר לא אישר בזמן"
                            }
                        }
                    )
                    
                    # Send notifications (without bot, just log for now)
                    # In production, admin notifications would be sent when bot is available
                    logger.warning(
                        f"P2P Order {order_id} auto-disputed: "
                        f"seller {seller_id} did not confirm within deadline. "
                        f"Buyer: {buyer_id}, Amount: {order_data.get('price', 0):.2f}₪"
                    )
                    
                    processed += 1
                
                if processed > 0:
                    logger.info(f"Processed {processed} P2P order timeouts")
                    
            except Exception as e:
                logger.error(f"Error checking P2P timeouts: {e}")

            await asyncio.sleep(600)  # 10 דקות


# יצירת instance גלובלי
scheduler = BackgroundScheduler()
