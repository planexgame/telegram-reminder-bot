import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен
TOKEN = os.getenv('TELEGRAM_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔔 Привет, {user.first_name}!\n\n"
        "Я бот 'НеЗабудьОплатить' — напоминаю о платежах.\n\n"
        "Команды:\n"
        "/start - начало\n"
        "/help - помощь\n"
        "/test - тест",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "🔔 НеЗабудьОплатить — помощь\n\n"
        "Основные команды:\n"
        "/start - начать работу\n"
        "/help - эта справка\n"
        "/test - тестовая команда\n\n"
        "Бот успешно работает!"
    )

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда /test"""
    await update.message.reply_text("✅ Бот работает! Тест пройден.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await query.message.reply_text("Нажмите /help в меню команд")
    elif query.data == "about":
        await query.message.reply_text("Бот 'НеЗабудьОплатить' — напоминания о платежах")

def main():
    """Запуск бота"""
    if not TOKEN:
        logger.error("❌ Токен не найден!")
        return
    
    logger.info("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
