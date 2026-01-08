"""
שירות ניהול צ'אט אנונימי בין קונים למוכרים
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class ChatService:
    """שירות לניהול שיחות צ'אט"""

    # -------------------- Admin Forum (Topics) mirroring --------------------

    @staticmethod
    def _admin_forum_enabled() -> bool:
        return bool(getattr(Config, "ADMIN_FORUM_ENABLED", False)) and int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0) != 0

    @staticmethod
    def _user_display_name_from_doc(user_doc: Optional[dict], fallback: str) -> str:
        if not user_doc:
            return fallback
        return (
            user_doc.get("commercial_name")
            or user_doc.get("business_name")
            or user_doc.get("first_name")
            or user_doc.get("username")
            or fallback
        )

    @staticmethod
    def _build_admin_forum_topic_title(buyer_doc: Optional[dict], seller_doc: Optional[dict], buyer_id: int, seller_id: int) -> str:
        buyer_name = ChatService._user_display_name_from_doc(buyer_doc, f"Buyer {buyer_id}")
        seller_name = ChatService._user_display_name_from_doc(seller_doc, f"Seller {seller_id}")
        title = f"{buyer_name} ↔ {seller_name}"
        # Telegram topic names have practical length limits; keep it short & stable.
        return title[:120]

    @staticmethod
    async def _ensure_admin_forum_topic(bot: "Bot", chat_doc: dict) -> Optional[int]:
        """
        Ensure a dedicated forum topic exists for this chat, and persist its topic id on the chat document.
        Returns message_thread_id (topic id) or None if unavailable.
        """
        if not ChatService._admin_forum_enabled():
            return None

        admin_forum_chat_id = int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0)
        existing_topic = chat_doc.get("admin_forum_topic_id")
        existing_forum = chat_doc.get("admin_forum_chat_id")
        if existing_topic and existing_forum == admin_forum_chat_id:
            try:
                return int(existing_topic)
            except Exception:
                pass

        # Create a new topic (best-effort)
        try:
            # Lazy import to keep module import side-effects minimal
            from telegram import Bot  # noqa: F401
        except Exception:
            return None

        if not hasattr(bot, "create_forum_topic"):
            logger.warning("Admin forum mirroring enabled but Bot.create_forum_topic is not available in this PTB version")
            return None

        buyer_id = int(chat_doc.get("buyer_id") or 0)
        seller_id = int(chat_doc.get("seller_id") or 0)
        buyer_doc = await db.users.find_one({"user_id": buyer_id})
        seller_doc = await db.users.find_one({"user_id": seller_id})
        topic_title = ChatService._build_admin_forum_topic_title(buyer_doc, seller_doc, buyer_id, seller_id)

        try:
            topic = await bot.create_forum_topic(chat_id=admin_forum_chat_id, name=topic_title)
            topic_id = int(getattr(topic, "message_thread_id"))
        except Exception as e:
            logger.warning(f"Failed to create admin forum topic (chat_id={admin_forum_chat_id}): {e}")
            return None

        try:
            await db.chats.update_one(
                {"_id": chat_doc["_id"]},
                {
                    "$set": {
                        "admin_forum_chat_id": admin_forum_chat_id,
                        "admin_forum_topic_id": topic_id,
                        "admin_forum_topic_title": topic_title,
                        "admin_forum_created_at": datetime.utcnow(),
                    }
                },
            )
        except Exception as e:
            logger.warning(f"Failed to persist admin forum topic mapping on chat {chat_doc.get('_id')}: {e}")

        return topic_id

    @staticmethod
    async def _mirror_message_to_admin_forum(bot: "Bot", chat_doc: dict, sender_id: int, message_text: str) -> None:
        if not ChatService._admin_forum_enabled():
            return

        admin_forum_chat_id = int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0)
        topic_id = await ChatService._ensure_admin_forum_topic(bot, chat_doc)
        if not topic_id:
            return

        buyer_id = int(chat_doc.get("buyer_id") or 0)
        seller_id = int(chat_doc.get("seller_id") or 0)
        sender_role = "קונה" if sender_id == buyer_id else "מוכר" if sender_id == seller_id else "משתמש"

        sender_doc = await db.users.find_one({"user_id": sender_id})
        buyer_doc = await db.users.find_one({"user_id": buyer_id})
        seller_doc = await db.users.find_one({"user_id": seller_id})
        buyer_name = ChatService._user_display_name_from_doc(buyer_doc, f"{buyer_id}")
        seller_name = ChatService._user_display_name_from_doc(seller_doc, f"{seller_id}")
        sender_name = ChatService._user_display_name_from_doc(sender_doc, str(sender_id))

        # Use Markdown safely
        try:
            from telegram.helpers import escape_markdown
            md = lambda s: escape_markdown("" if s is None else str(s), version=1)
        except Exception:
            md = lambda s: "" if s is None else str(s)

        text = (
            f"💬 *שיחה:* {md(buyer_name)} ↔ {md(seller_name)}\n"
            f"👤 *שולח:* {md(sender_name)} ({md(sender_role)})\n"
            f"🆔 *Chat:* `{md(str(chat_doc.get('_id'))[:24])}`\n\n"
            f"{md(message_text)}"
        )

        try:
            await bot.send_message(
                chat_id=admin_forum_chat_id,
                message_thread_id=topic_id,
                text=text,
                parse_mode="Markdown",
            )
        except TypeError:
            # Backward compatibility: if message_thread_id is unsupported, fall back to the main forum chat
            await bot.send_message(chat_id=admin_forum_chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to mirror chat message to admin forum: {e}")

    @staticmethod
    async def get_chat_by_admin_forum_topic(admin_forum_chat_id: int, topic_id: int) -> Optional[dict]:
        """Lookup chat doc by admin forum topic mapping."""
        try:
            return await db.chats.find_one(
                {
                    "admin_forum_chat_id": int(admin_forum_chat_id),
                    "admin_forum_topic_id": int(topic_id),
                }
            )
        except Exception as e:
            logger.error(f"Error finding chat by admin forum topic: {e}")
            return None

    @staticmethod
    async def create_chat(buyer_id: int, seller_id: int, order_id: Optional[str] = None) -> Optional[str]:
        """
        יצירת שיחת צ'אט חדשה או קבלת קיימת

        Returns:
            chat_id או None במקרה של שגיאה
        """
        try:
            # בדיקה אם כבר קיימת שיחה
            existing = await db.chats.find_one({
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "status": "active"
            })

            if existing:
                return str(existing["_id"])

            # יצירת שיחה חדשה
            chat_data = {
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "order_id": ObjectId(order_id) if order_id else None,
                "status": "active",
                "created_at": datetime.utcnow(),
                "last_message_at": datetime.utcnow(),
                "buyer_unread": 0,
                "seller_unread": 0
            }

            result = await db.chats.insert_one(chat_data)
            logger.info(f"Chat created: {result.inserted_id} between {buyer_id} and {seller_id}")

            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error creating chat: {e}")
            return None

    @staticmethod
    async def send_message(
        chat_id: str,
        sender_id: int,
        message_text: str
    ) -> Optional[str]:
        """
        שליחת הודעה בצ'אט

        Returns:
            message_id או הודעת שגיאה
        """
        try:
            chat = await db.chats.find_one({"_id": ObjectId(chat_id)})

            if not chat:
                return "❌ שיחה לא נמצאה"

            if chat["status"] != "active":
                return "❌ השיחה סגורה"

            # בדיקה שהשולח שייך לשיחה
            if sender_id not in [chat["buyer_id"], chat["seller_id"]]:
                return "❌ אין לך הרשאה לשיחה זו"

            # קביעת הנמען
            is_buyer = sender_id == chat["buyer_id"]
            recipient_id = chat["seller_id"] if is_buyer else chat["buyer_id"]

            # שמירת ההודעה
            message_data = {
                "chat_id": ObjectId(chat_id),
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "message": message_text[:1000],  # הגבלת אורך
                "read": False,
                "created_at": datetime.utcnow()
            }

            result = await db.messages.insert_one(message_data)

            # עדכון שיחה
            update_data = {
                "last_message_at": datetime.utcnow(),
                "last_message": message_text[:100]
            }

            # הגדלת מונה הודעות שלא נקראו
            if is_buyer:
                update_data["seller_unread"] = chat.get("seller_unread", 0) + 1
            else:
                update_data["buyer_unread"] = chat.get("buyer_unread", 0) + 1

            await db.chats.update_one(
                {"_id": ObjectId(chat_id)},
                {"$set": update_data}
            )

            # Use a bot instance for notifications / mirroring (best-effort)
            bot = None
            try:
                from telegram import Bot
                bot = Bot(Config.BOT_TOKEN)
            except Exception as e:
                logger.warning(f"Failed to initialize Bot for chat notifications: {e}")

            if bot:
                # שליחת התראה לנמען
                try:
                    sender = await db.users.find_one({"user_id": sender_id})
                    sender_name = sender.get("first_name", "משתמש") if sender else "משתמש"

                    await bot.send_message(
                        recipient_id,
                        f"💬 *הודעה חדשה מ-{sender_name}*\n\n"
                        f"{message_text[:200]}\n\n"
                        f"השב על ידי שליחת /chats",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send message notification: {e}")

                # Mirror to admin forum (Topics) - best-effort (should never block user flow)
                try:
                    await ChatService._mirror_message_to_admin_forum(bot, chat, sender_id, message_text)
                except Exception as e:
                    logger.warning(f"Failed to mirror message to admin forum: {e}")

            logger.info(f"Message sent in chat {chat_id} by {sender_id}")
            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return f"❌ שגיאה בשליחת הודעה: {str(e)}"

    @staticmethod
    async def get_chat_messages(chat_id: str, user_id: int, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
        """
        קבלת הודעות שיחה

        Returns:
            רשימת הודעות או None במקרה של שגיאה
        """
        try:
            chat = await db.chats.find_one({"_id": ObjectId(chat_id)})

            if not chat:
                return None

            # בדיקה שהמשתמש שייך לשיחה
            if user_id not in [chat["buyer_id"], chat["seller_id"]]:
                return None

            # סימון הודעות כנקראו
            is_buyer = user_id == chat["buyer_id"]

            await db.messages.update_many(
                {
                    "chat_id": ObjectId(chat_id),
                    "recipient_id": user_id,
                    "read": False
                },
                {"$set": {"read": True, "read_at": datetime.utcnow()}}
            )

            # איפוס מונה הודעות שלא נקראו
            if is_buyer:
                await db.chats.update_one(
                    {"_id": ObjectId(chat_id)},
                    {"$set": {"buyer_unread": 0}}
                )
            else:
                await db.chats.update_one(
                    {"_id": ObjectId(chat_id)},
                    {"$set": {"seller_unread": 0}}
                )

            # קבלת הודעות
            cursor = db.messages.find({
                "chat_id": ObjectId(chat_id)
            }).sort("created_at", -1).limit(limit)

            messages = await cursor.to_list(length=None)
            messages.reverse()  # מהישנה לחדשה

            return messages

        except Exception as e:
            logger.error(f"Error getting chat messages: {e}")
            return None

    @staticmethod
    async def get_user_chats(user_id: int) -> List[Dict[str, Any]]:
        """קבלת כל השיחות של משתמש"""
        try:
            cursor = db.chats.find({
                "$or": [
                    {"buyer_id": user_id},
                    {"seller_id": user_id}
                ],
                "status": "active"
            }).sort("last_message_at", -1)

            chats = await cursor.to_list(length=None)

            # הוספת מידע על המשתתפים
            for chat in chats:
                is_buyer = user_id == chat["buyer_id"]
                other_user_id = chat["seller_id"] if is_buyer else chat["buyer_id"]

                other_user = await db.users.find_one({"user_id": other_user_id})

                if other_user:
                    chat["other_user_name"] = other_user.get("first_name") or other_user.get("business_name", "משתמש")
                    chat["other_user_role"] = "מוכר" if is_buyer else "קונה"
                else:
                    chat["other_user_name"] = "משתמש"
                    chat["other_user_role"] = "לא ידוע"

                # מספר הודעות שלא נקראו
                chat["unread_count"] = chat.get("buyer_unread" if is_buyer else "seller_unread", 0)

            return chats

        except Exception as e:
            logger.error(f"Error getting user chats: {e}")
            return []

    @staticmethod
    async def close_chat(chat_id: str, user_id: int, is_admin: bool = False) -> Optional[str]:
        """
        סגירת שיחה

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            chat = await db.chats.find_one({"_id": ObjectId(chat_id)})

            if not chat:
                return "❌ שיחה לא נמצאה"

            # בדיקת הרשאות
            if not is_admin and user_id not in [chat["buyer_id"], chat["seller_id"]]:
                return "❌ אין לך הרשאה לסגור שיחה זו"

            await db.chats.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$set": {
                        "status": "closed",
                        "closed_at": datetime.utcnow(),
                        "closed_by": user_id
                    }
                }
            )

            logger.info(f"Chat {chat_id} closed by {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error closing chat: {e}")
            return f"❌ שגיאה בסגירת שיחה: {str(e)}"

    @staticmethod
    async def get_chat_by_id(chat_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """קבלת מידע על שיחה"""
        try:
            chat = await db.chats.find_one({"_id": ObjectId(chat_id)})

            if not chat:
                return None

            # בדיקה שהמשתמש שייך לשיחה
            if user_id not in [chat["buyer_id"], chat["seller_id"]]:
                return None

            return chat

        except Exception as e:
            logger.error(f"Error getting chat: {e}")
            return None

    @staticmethod
    async def delete_message(message_id: str, user_id: int, is_admin: bool = False) -> Optional[str]:
        """
        מחיקת הודעה

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            message = await db.messages.find_one({"_id": ObjectId(message_id)})

            if not message:
                return "❌ הודעה לא נמצאה"

            # בדיקת הרשאות
            if not is_admin and message["sender_id"] != user_id:
                return "❌ אין לך הרשאה למחוק הודעה זו"

            await db.messages.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": {"deleted": True, "deleted_at": datetime.utcnow()}}
            )

            logger.info(f"Message {message_id} deleted by {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return f"❌ שגיאה במחיקת הודעה: {str(e)}"

    @staticmethod
    async def get_unread_count(user_id: int) -> int:
        """קבלת מספר הודעות שלא נקראו"""
        try:
            # סיכום כל ההודעות שלא נקראו מכל השיחות
            chats = await db.chats.find({
                "$or": [
                    {"buyer_id": user_id},
                    {"seller_id": user_id}
                ]
            }).to_list(length=None)

            total_unread = 0
            for chat in chats:
                is_buyer = user_id == chat["buyer_id"]
                unread = chat.get("buyer_unread" if is_buyer else "seller_unread", 0)
                total_unread += unread

            return total_unread

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    @staticmethod
    async def search_chats(user_id: int, query: str) -> List[Dict[str, Any]]:
        """חיפוש בשיחות"""
        try:
            # חיפוש בהודעות
            cursor = db.messages.find({
                "$or": [
                    {"sender_id": user_id},
                    {"recipient_id": user_id}
                ],
                "message": {"$regex": query, "$options": "i"}
            }).sort("created_at", -1).limit(20)

            messages = await cursor.to_list(length=None)

            # קבלת השיחות המתאימות
            chat_ids = list(set([msg["chat_id"] for msg in messages]))

            chats = []
            for chat_id in chat_ids:
                chat = await db.chats.find_one({"_id": chat_id})
                if chat:
                    is_buyer = user_id == chat["buyer_id"]
                    other_user_id = chat["seller_id"] if is_buyer else chat["buyer_id"]

                    other_user = await db.users.find_one({"user_id": other_user_id})
                    if other_user:
                        chat["other_user_name"] = other_user.get("first_name") or other_user.get("business_name", "משתמש")

                    chats.append(chat)

            return chats

        except Exception as e:
            logger.error(f"Error searching chats: {e}")
            return []

    @staticmethod
    async def block_user_in_chat(chat_id: str, blocker_id: int) -> Optional[str]:
        """
        חסימת משתמש בשיחה

        Returns:
            None אם הצליח, או הודעת שגיאה
        """
        try:
            chat = await db.chats.find_one({"_id": ObjectId(chat_id)})

            if not chat:
                return "❌ שיחה לא נמצאה"

            if blocker_id not in [chat["buyer_id"], chat["seller_id"]]:
                return "❌ אין לך הרשאה לשיחה זו"

            is_buyer = blocker_id == chat["buyer_id"]
            blocked_id = chat["seller_id"] if is_buyer else chat["buyer_id"]

            await db.chats.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$set": {
                        "blocked": True,
                        "blocked_by": blocker_id,
                        "blocked_user": blocked_id,
                        "blocked_at": datetime.utcnow(),
                        "status": "blocked"
                    }
                }
            )

            logger.info(f"User {blocked_id} blocked in chat {chat_id} by {blocker_id}")
            return None

        except Exception as e:
            logger.error(f"Error blocking user in chat: {e}")
            return f"❌ שגיאה בחסימה: {str(e)}"

    @staticmethod
    async def get_admin_all_chats(page: int = 0) -> List[Dict[str, Any]]:
        """קבלת כל השיחות (לאדמין)"""
        try:
            skip = page * Config.ITEMS_PER_PAGE

            cursor = db.chats.find({}).sort("last_message_at", -1).skip(skip).limit(Config.ITEMS_PER_PAGE)

            chats = await cursor.to_list(length=None)

            # הוספת מידע על המשתתפים
            for chat in chats:
                buyer = await db.users.find_one({"user_id": chat["buyer_id"]})
                seller = await db.users.find_one({"user_id": chat["seller_id"]})

                chat["buyer_name"] = buyer.get("first_name", "קונה") if buyer else "קונה"
                chat["seller_name"] = seller.get("business_name", "מוכר") if seller else "מוכר"

            return chats

        except Exception as e:
            logger.error(f"Error getting admin all chats: {e}")
            return []
