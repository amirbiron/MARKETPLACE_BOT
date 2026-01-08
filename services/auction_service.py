"""
שירות ניהול מכרזים (Auctions)
"""
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
from database import db
from models import Auction, AuctionStatus, User
from config import Config
import logging

logger = logging.getLogger(__name__)


class AuctionService:
    """שירות לניהול מכרזים"""

    @staticmethod
    async def create_auction(
        seller_id: int,
        coupon_id: str,
        starting_price: float,
        duration_hours: int = 24
    ) -> Optional[Tuple[str, str]]:
        """
        יצירת מכרז חדש

        Returns:
            Tuple[auction_id, error_message] או None אם הצליח
        """
        try:
            # בדיקה שהקופון קיים ושייך למוכר
            coupon = await db.coupons.find_one({
                "_id": ObjectId(coupon_id),
                "seller_id": seller_id,
                "status": "active"
            })

            if not coupon:
                return None, "❌ קופון לא נמצא או לא פעיל"

            # בדיקה שאין מכרז פעיל לקופון זה
            existing_auction = await db.auctions.find_one({
                "coupon_id": ObjectId(coupon_id),
                "status": "active"
            })

            if existing_auction:
                return None, "❌ כבר קיים מכרז פעיל לקופון זה"

            # יצירת המכרז
            auction = Auction(
                seller_id=seller_id,
                coupon_id=ObjectId(coupon_id),
                starting_price=starting_price,
                end_time=datetime.utcnow() + timedelta(hours=duration_hours)
            )

            result = await db.auctions.insert_one(auction.to_dict())

            # עדכון סטטוס הקופון למכרז
            await db.coupons.update_one(
                {"_id": ObjectId(coupon_id)},
                {"$set": {"status": "auction", "auction_id": result.inserted_id}}
            )

            logger.info(f"Auction created: {result.inserted_id} for coupon {coupon_id}")
            return str(result.inserted_id), None

        except Exception as e:
            logger.error(f"Error creating auction: {e}")
            return None, f"❌ שגיאה ביצירת מכרז: {str(e)}"

    @staticmethod
    async def place_bid(
        auction_id: str,
        bidder_id: int,
        bid_amount: float
    ) -> Optional[str]:
        """
        הצבת הצעת מחיר במכרז

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            auction = await db.auctions.find_one({"_id": ObjectId(auction_id)})

            if not auction:
                return "❌ מכרז לא נמצא"

            if auction["status"] != "active":
                return "❌ המכרז אינו פעיל"

            if auction["end_time"] < datetime.utcnow():
                # המכרז הסתיים
                await AuctionService.end_auction(auction_id)
                return "❌ המכרז הסתיים"

            # בדיקה שהמוכר לא מנסה להציע על המכרז שלו
            if auction["seller_id"] == bidder_id:
                return "❌ אינך יכול להציע על המכרז שלך"

            # בדיקה שההצעה גבוהה מהנוכחית
            min_bid = auction["current_price"] + Config.MIN_BID_INCREMENT
            if bid_amount < min_bid:
                return f"❌ ההצעה חייבת להיות לפחות {min_bid:.2f}₪"

            # בדיקת יתרה
            user = await db.users.find_one({"user_id": bidder_id})
            if not user:
                return "❌ משתמש לא נמצא"

            total_needed = bid_amount + Config.BUYER_COMMISSION_RATE * bid_amount

            if user["balance"] < total_needed:
                return f"❌ אין מספיק יתרה. נדרש: {total_needed:.2f}₪"

            # שחרור יתרה קפואה של המציע הקודם
            if auction.get("current_bidder_id"):
                prev_bidder = auction["current_bidder_id"]
                prev_frozen = auction["current_price"] * (1 + Config.BUYER_COMMISSION_RATE)

                await db.users.update_one(
                    {"user_id": prev_bidder},
                    {
                        "$inc": {
                            "frozen_balance": -prev_frozen,
                            "balance": prev_frozen
                        }
                    }
                )

                # התראה למציע הקודם שהוא עקף
                try:
                    from telegram import Bot
                    bot = Bot(Config.BOT_TOKEN)
                    await bot.send_message(
                        prev_bidder,
                        f"⚠️ ההצעה שלך במכרז עוקפה!\n"
                        f"המחיר החדש: {bid_amount:.2f}₪\n"
                        f"היתרה הקפואה שוחררה."
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify previous bidder: {e}")

            # הקפאת יתרה למציע החדש
            await db.users.update_one(
                {"user_id": bidder_id},
                {
                    "$inc": {
                        "balance": -total_needed,
                        "frozen_balance": total_needed
                    }
                }
            )

            # עדכון המכרז
            await db.auctions.update_one(
                {"_id": ObjectId(auction_id)},
                {
                    "$set": {
                        "current_price": bid_amount,
                        "current_bidder_id": bidder_id,
                        "last_bid_time": datetime.utcnow()
                    },
                    "$inc": {"bid_count": 1}
                }
            )

            # שמירת היסטוריית הצעות
            await db.auction_bids.insert_one({
                "auction_id": ObjectId(auction_id),
                "bidder_id": bidder_id,
                "amount": bid_amount,
                "created_at": datetime.utcnow()
            })

            logger.info(f"Bid placed: {bid_amount} by {bidder_id} on auction {auction_id}")
            return None

        except Exception as e:
            logger.error(f"Error placing bid: {e}")
            return f"❌ שגיאה בהצבת הצעה: {str(e)}"

    @staticmethod
    async def end_auction(auction_id: str) -> Optional[Tuple[bool, str]]:
        """
        סיום מכרז וקביעת זוכה

        Returns:
            Tuple[has_winner, message]
        """
        try:
            auction = await db.auctions.find_one({"_id": ObjectId(auction_id)})

            if not auction:
                return False, "❌ מכרז לא נמצא"

            if auction["status"] != "active":
                return False, "❌ המכרז כבר הסתיים"

            # סימון המכרז כהסתיים
            await db.auctions.update_one(
                {"_id": ObjectId(auction_id)},
                {
                    "$set": {
                        "status": "ended",
                        "ended_at": datetime.utcnow()
                    }
                }
            )

            # אם יש זוכה
            if auction.get("current_bidder_id"):
                winner_id = auction["current_bidder_id"]
                winning_price = auction["current_price"]

                # יצירת הזמנה
                coupon = await db.coupons.find_one({"_id": auction["coupon_id"]})

                buyer_commission = winning_price * Config.BUYER_COMMISSION_RATE
                seller_commission = winning_price * Config.SELLER_COMMISSION_RATE

                order_id = await db.create_order(
                    buyer_id=winner_id,
                    seller_id=auction["seller_id"],
                    coupon_id=str(auction["coupon_id"]),
                    original_price=coupon.get("original_price", winning_price),
                    sale_price=winning_price,
                    buyer_commission=buyer_commission,
                    seller_commission=seller_commission,
                    coupon_code=coupon.get("digital_code", "")
                )

                # שחרור יתרה קפואה והעברת כסף
                frozen_amount = winning_price + buyer_commission

                # ניכוי מיתרה קפואה של הקונה
                await db.users.update_one(
                    {"user_id": winner_id},
                    {"$inc": {"frozen_balance": -frozen_amount}}
                )

                # הוספת כסף למוכר (בניכוי עמלה)
                seller_receives = winning_price - seller_commission
                await db.users.update_one(
                    {"user_id": auction["seller_id"]},
                    {"$inc": {"balance": seller_receives}}
                )

                # עדכון סטטוס הקופון
                await db.coupons.update_one(
                    {"_id": auction["coupon_id"]},
                    {"$set": {"status": "sold"}}
                )

                # שמירת הזוכה במכרז
                await db.auctions.update_one(
                    {"_id": ObjectId(auction_id)},
                    {"$set": {"winner_id": winner_id, "order_id": ObjectId(order_id)}}
                )

                # התראות
                try:
                    from telegram import Bot
                    bot = Bot(Config.BOT_TOKEN)

                    # לזוכה
                    await bot.send_message(
                        winner_id,
                        f"🎉 *ניצחת במכרז!*\n\n"
                        f"💰 מחיר הזכייה: {winning_price:.2f}₪\n"
                        f"📦 קוד הקופון: `{coupon.get('digital_code', '')}`\n"
                        f"⏰ יש לך 12 שעות לדווח על בעיה",
                        parse_mode="Markdown"
                    )

                    # למוכר
                    await bot.send_message(
                        auction["seller_id"],
                        f"✅ *המכרז הסתיים!*\n\n"
                        f"💰 מחיר הזכייה: {winning_price:.2f}₪\n"
                        f"💵 תקבל: {seller_receives:.2f}₪ (לאחר עמלה {Config.SELLER_COMMISSION_RATE*100:.0f}%)\n"
                        f"הכסף הועבר ליתרתך.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send auction end notifications: {e}")

                logger.info(f"Auction {auction_id} ended with winner {winner_id}")
                return True, f"✅ המכרז הסתיים! הזוכה: משתמש {winner_id}"

            else:
                # אין הצעות - ביטול המכרז
                await db.coupons.update_one(
                    {"_id": auction["coupon_id"]},
                    {"$set": {"status": "active"}, "$unset": {"auction_id": ""}}
                )

                logger.info(f"Auction {auction_id} ended with no bids")
                return False, "ℹ️ המכרז הסתיים ללא הצעות"

        except Exception as e:
            logger.error(f"Error ending auction: {e}")
            return False, f"❌ שגיאה בסיום מכרז: {str(e)}"

    @staticmethod
    async def cancel_auction(auction_id: str, seller_id: int) -> Optional[str]:
        """
        ביטול מכרז על ידי המוכר

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            auction = await db.auctions.find_one({"_id": ObjectId(auction_id)})

            if not auction:
                return "❌ מכרז לא נמצא"

            if auction["seller_id"] != seller_id:
                return "❌ אינך בעלים של מכרז זה"

            if auction["status"] != "active":
                return "❌ לא ניתן לבטל מכרז שכבר הסתיים"

            # אם יש מציעים - לא ניתן לבטל
            if auction.get("current_bidder_id"):
                return "❌ לא ניתן לבטל מכרז שיש בו הצעות"

            # ביטול המכרז
            await db.auctions.update_one(
                {"_id": ObjectId(auction_id)},
                {
                    "$set": {
                        "status": "cancelled",
                        "cancelled_at": datetime.utcnow()
                    }
                }
            )

            # החזרת הקופון למצב פעיל
            await db.coupons.update_one(
                {"_id": auction["coupon_id"]},
                {"$set": {"status": "active"}, "$unset": {"auction_id": ""}}
            )

            logger.info(f"Auction {auction_id} cancelled by seller {seller_id}")
            return None

        except Exception as e:
            logger.error(f"Error cancelling auction: {e}")
            return f"❌ שגיאה בביטול מכרז: {str(e)}"

    @staticmethod
    async def get_active_auctions(page: int = 0, category: Optional[str] = None) -> List[dict]:
        """קבלת מכרזים פעילים עם פגינציה"""
        try:
            query = {"status": "active", "end_time": {"$gt": datetime.utcnow()}}

            skip = page * Config.ITEMS_PER_PAGE
            cursor = db.auctions.find(query).sort("end_time", 1).skip(skip).limit(Config.ITEMS_PER_PAGE)

            auctions = await cursor.to_list(length=None)

            # הוספת מידע על הקופונים
            for auction in auctions:
                coupon = await db.coupons.find_one({"_id": auction["coupon_id"]})
                if coupon:
                    auction["coupon"] = coupon

                    # סינון לפי קטגוריה אם נדרש
                    if category and coupon.get("category") != category:
                        auctions.remove(auction)

            return auctions

        except Exception as e:
            logger.error(f"Error getting active auctions: {e}")
            return []

    @staticmethod
    async def get_auction_by_id(auction_id: str) -> Optional[dict]:
        """קבלת מכרז לפי ID"""
        try:
            auction = await db.auctions.find_one({"_id": ObjectId(auction_id)})

            if auction:
                # הוספת מידע על הקופון
                coupon = await db.coupons.find_one({"_id": auction["coupon_id"]})
                if coupon:
                    auction["coupon"] = coupon

                # הוספת מידע על המוכר
                seller = await db.users.find_one({"user_id": auction["seller_id"]})
                if seller:
                    auction["seller"] = {
                        "business_name": seller.get("business_name", "לא ידוע"),
                        "verified": seller.get("verified", False)
                    }

                # ספירת הצעות
                bid_count = await db.auction_bids.count_documents({"auction_id": ObjectId(auction_id)})
                auction["bid_count"] = bid_count

            return auction

        except Exception as e:
            logger.error(f"Error getting auction: {e}")
            return None

    @staticmethod
    async def get_auction_bids(auction_id: str, limit: int = 10) -> List[dict]:
        """קבלת היסטוריית הצעות למכרז"""
        try:
            cursor = db.auction_bids.find(
                {"auction_id": ObjectId(auction_id)}
            ).sort("created_at", -1).limit(limit)

            return await cursor.to_list(length=None)

        except Exception as e:
            logger.error(f"Error getting auction bids: {e}")
            return []

    @staticmethod
    async def get_seller_auctions(seller_id: int) -> List[dict]:
        """קבלת כל המכרזים של מוכר"""
        try:
            cursor = db.auctions.find(
                {"seller_id": seller_id}
            ).sort("created_at", -1)

            auctions = await cursor.to_list(length=None)

            # הוספת מידע על הקופונים
            for auction in auctions:
                coupon = await db.coupons.find_one({"_id": auction["coupon_id"]})
                if coupon:
                    auction["coupon"] = coupon

            return auctions

        except Exception as e:
            logger.error(f"Error getting seller auctions: {e}")
            return []

    @staticmethod
    async def get_user_bids(user_id: int) -> List[dict]:
        """קבלת כל ההצעות של משתמש"""
        try:
            # מציאת כל ההצעות
            cursor = db.auction_bids.find(
                {"bidder_id": user_id}
            ).sort("created_at", -1)

            bids = await cursor.to_list(length=None)

            # הוספת מידע על המכרזים והקופונים
            for bid in bids:
                auction = await db.auctions.find_one({"_id": bid["auction_id"]})
                if auction:
                    bid["auction"] = auction

                    coupon = await db.coupons.find_one({"_id": auction["coupon_id"]})
                    if coupon:
                        bid["coupon"] = coupon

            return bids

        except Exception as e:
            logger.error(f"Error getting user bids: {e}")
            return []

    @staticmethod
    async def check_and_end_expired_auctions():
        """בדיקה וסיום מכרזים שהסתיימו - לרוץ ב-background"""
        try:
            expired_auctions = await db.auctions.find({
                "status": "active",
                "end_time": {"$lt": datetime.utcnow()}
            }).to_list(length=None)

            ended_count = 0
            for auction in expired_auctions:
                success, msg = await AuctionService.end_auction(str(auction["_id"]))
                if success is not None:
                    ended_count += 1

            if ended_count > 0:
                logger.info(f"Ended {ended_count} expired auctions")

            return ended_count

        except Exception as e:
            logger.error(f"Error checking expired auctions: {e}")
            return 0
