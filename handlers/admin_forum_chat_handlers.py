"""
Admin forum (Topics) chat mirroring handlers.

When enabled (Config.ADMIN_FORUM_CHAT_ID / ADMIN_FORUM_ENABLED), user-to-user chat messages
are mirrored into a forum topic. Admins can reply inside the topic and choose whether the
reply is sent to the buyer, seller, or both.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.helpers import escape_markdown

from config import Config
from services.chat_service import ChatService

logger = logging.getLogger(__name__)


class AdminForumChatHandlers:
    """Handlers for admin forum (Topics) support chat."""

    @staticmethod
    def _md(text: object) -> str:
        return escape_markdown("" if text is None else str(text), version=1)

    @staticmethod
    def _is_allowed_admin(user_id: int) -> bool:
        return int(user_id) in set(getattr(Config, "ADMIN_IDS", []) or [])

    @staticmethod
    async def on_admin_forum_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """When an admin posts in a linked topic, prompt for routing (buyer/seller/both)."""
        if not getattr(Config, "ADMIN_FORUM_ENABLED", False):
            return
        admin_forum_chat_id = int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0)
        if admin_forum_chat_id == 0:
            return

        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not chat or not user:
            return
        if chat.id != admin_forum_chat_id:
            return
        if user.is_bot:
            return
        if not AdminForumChatHandlers._is_allowed_admin(user.id):
            return

        # Only act inside Topics (message_thread_id exists)
        topic_id = getattr(msg, "message_thread_id", None)
        if not topic_id:
            return

        # Ignore service messages about topics
        if getattr(msg, "forum_topic_created", None) or getattr(msg, "forum_topic_edited", None):
            return
        if getattr(msg, "forum_topic_closed", None) or getattr(msg, "forum_topic_reopened", None):
            return

        chat_doc = await ChatService.get_chat_by_admin_forum_topic(admin_forum_chat_id, int(topic_id))
        if not chat_doc:
            return

        buyer_id = int(chat_doc.get("buyer_id") or 0)
        seller_id = int(chat_doc.get("seller_id") or 0)
        chat_short = str(chat_doc.get("_id") or "")[:8]

        buttons = [
            [
                InlineKeyboardButton("📨 לקונה", callback_data=f"af_send:buyer:{msg.message_id}"),
                InlineKeyboardButton("📨 למוכר", callback_data=f"af_send:seller:{msg.message_id}"),
            ],
            [InlineKeyboardButton("📨 לשניהם", callback_data=f"af_send:both:{msg.message_id}")],
        ]

        prompt = (
            "📤 *הודעת מנהל*\n\n"
            f"לאן לשלוח את ההודעה הזו?\n"
            f"🆔 *Chat:* `{AdminForumChatHandlers._md(chat_short)}`\n"
            f"👥 *Buyer:* `{buyer_id}` | *Seller:* `{seller_id}`"
        )

        try:
            await context.bot.send_message(
                chat_id=admin_forum_chat_id,
                message_thread_id=int(topic_id),
                text=prompt,
                reply_to_message_id=msg.message_id,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown",
            )
        except TypeError:
            # Backward compatible fallback
            await context.bot.send_message(
                chat_id=admin_forum_chat_id,
                text=prompt,
                reply_to_message_id=msg.message_id,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Failed to send admin routing prompt: {e}")

    @staticmethod
    async def on_admin_forum_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle routing selection buttons (buyer/seller/both)."""
        query = update.callback_query
        if not query or not query.data:
            return

        user = update.effective_user
        if not user or user.is_bot:
            return
        if not AdminForumChatHandlers._is_allowed_admin(user.id):
            await query.answer("אין הרשאה", show_alert=True)
            return

        if not getattr(Config, "ADMIN_FORUM_ENABLED", False):
            await query.answer("האפשרות כבויה", show_alert=True)
            return

        admin_forum_chat_id = int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0)
        if admin_forum_chat_id == 0:
            await query.answer("לא הוגדרה קבוצת פורום", show_alert=True)
            return

        parts = query.data.split(":")
        # af_send:<target>:<message_id>
        if len(parts) != 3:
            await query.answer("בקשה לא תקינה", show_alert=True)
            return

        _, target, msg_id_str = parts
        try:
            admin_msg_id = int(msg_id_str)
        except Exception:
            await query.answer("בקשה לא תקינה", show_alert=True)
            return

        topic_id = getattr(query.message, "message_thread_id", None)
        if not topic_id:
            await query.answer("לא נמצא topic", show_alert=True)
            return

        chat_doc = await ChatService.get_chat_by_admin_forum_topic(admin_forum_chat_id, int(topic_id))
        if not chat_doc:
            await query.answer("לא נמצאה שיחה לטופיק הזה", show_alert=True)
            return

        buyer_id = int(chat_doc.get("buyer_id") or 0)
        seller_id = int(chat_doc.get("seller_id") or 0)

        recipients: List[int]
        if target == "buyer":
            recipients = [buyer_id]
            label = "לקונה"
        elif target == "seller":
            recipients = [seller_id]
            label = "למוכר"
        elif target == "both":
            recipients = [buyer_id, seller_id]
            label = "לשניהם"
        else:
            await query.answer("יעד לא מוכר", show_alert=True)
            return

        admin_name = user.full_name or user.first_name or str(user.id)
        prefix = f"👮‍♂️ *הודעה ממנהל:* {AdminForumChatHandlers._md(admin_name)}"

        await query.answer(f"שולח {label}…")

        failed: List[int] = []
        for rid in recipients:
            if not rid:
                continue
            try:
                await context.bot.send_message(chat_id=rid, text=prefix, parse_mode="Markdown")
                await context.bot.copy_message(
                    chat_id=rid,
                    from_chat_id=admin_forum_chat_id,
                    message_id=admin_msg_id,
                )
            except Exception:
                failed.append(rid)

        # Mark done (remove buttons to prevent accidental double-send)
        try:
            done_text = (query.message.text or "") + f"\n\n✅ נשלח {label}."
            if failed:
                done_text += f"\n⚠️ נכשל עבור: {', '.join(str(x) for x in failed)}"
            await query.edit_message_text(done_text, parse_mode="Markdown", reply_markup=None)
        except Exception:
            # Editing can fail if message already edited/too old; ignore
            pass


def get_admin_forum_chat_handlers():
    """Register handlers for admin forum mirroring."""
    if not getattr(Config, "ADMIN_FORUM_ENABLED", False):
        return []
    admin_forum_chat_id = int(getattr(Config, "ADMIN_FORUM_CHAT_ID", 0) or 0)
    if admin_forum_chat_id == 0:
        return []

    return [
        MessageHandler(filters.Chat(admin_forum_chat_id), AdminForumChatHandlers.on_admin_forum_message),
        CallbackQueryHandler(AdminForumChatHandlers.on_admin_forum_send_callback, pattern=r"^af_send:"),
    ]

