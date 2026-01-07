"""
Main Bot Application for Marketplace Bot
"""
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from config import Config
from database import db

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    from keyboards import get_main_menu_keyboard
    
    user = update.effective_user
    user_data = await db.get_user(user.id)
    
    if not user_data:
        user_data = await db.create_user(user.id, user.username, user.first_name)
        await update.message.reply_text(
            f"ברוך הבא {user.first_name}! 🎉\n"
            "זהו בוט Marketplace לקניה ומכירת קופונים."
        )
    
    role = user_data.get("role", "buyer")
    keyboard = get_main_menu_keyboard(role)
    
    await update.message.reply_text(
        "בחר פעולה מהתפריט:",
        reply_markup=keyboard
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio
    
    async def init_db():
        await db.connect()
    
    asyncio.run(init_db())
    main()
