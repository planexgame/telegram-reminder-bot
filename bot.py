import os
import logging
import threading
import time
import requests
from datetime import datetime
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

# ==================== АВТОПИНГ ====================
def keep_alive():
    """Функция для поддержания бота онлайн"""
    
    def ping_server():
        """Пинг сервера каждые 10 минут"""
        # URL вашего сервиса на Render
        render_url = os.getenv('RENDER_URL')
        
        if not render_url:
            # Если RENDER_URL не указан, пробуем определить автоматически
            service_name = os.getenv('RENDER_SERVICE_NAME', 'telegram-reminder-bot')
            render_url = f"https://{service_name}.onrender.com"
        
        logger.info(f"🔄 Автопинг запущен. URL: {render_url}")
        
        while True:
            try:
                response = requests.get(render_url, timeout=10)
                logger.info(f"✅ Пинг успешен: {response.status_code}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка пинга: {e}")
            
            # Ждем 8 минут (480 секунд) - меньше 15 минут!
            time.sleep(480)
    
    # Запускаем в отдельном потоке
    ping_thread = threading.Thread(target=ping_server, daemon=True)
    ping_thread.start()

# ==================== КОМАНДЫ БОТА ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
        [InlineKeyboardButton("💎 Премиум", callback_data="premium"),
         InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔔 <b>НеЗабудьОплатить</b>\n\n"
        f"Привет, {user.first_name}! Я помогу не забывать о важных платежах.\n\n"
        "<b>🎯 Бесплатные функции:</b>\n"
        "• До 5 напоминаний\n"
        "• Уведомления за день\n"
        "• Простой интерфейс\n\n"
        "<b>💎 Премиум (299₽/мес):</b>\n"
        "• Неограниченные напоминания\n"
        "• Повторяющиеся платежи\n"
        "• Уведомления за 3 и 7 дней\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = (
        "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• /start — начать работу\n"
        "• /help — эта справка\n"
        "• /new — создать напоминание (скоро)\n"
        "• /list — список напоминаний (скоро)\n"
        "• /premium — премиум подписка (скоро)\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Создаете напоминание\n"
        "2. Указываете сумму и дату\n"
        "3. Получаете уведомление\n"
        "4. Не забываете оплатить!\n\n"
        "<i>Бот теперь работает 24/7!</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "create":
            await query.edit_message_text(
                "🔄 <b>Создание напоминания</b>\n\n"
                "Используйте команду /new для создания напоминаний.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='HTML'
            )
        elif query.data == "list":
            await query.edit_message_text(
                "📋 <b>Ваши напоминания</b>\n\n"
                "Используйте команду /list для просмотра напоминаний.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='HTML'
            )
        elif query.data == "premium":
            await query.edit_message_text(
                "💎 <b>Премиум подписка</b>\n\n"
                "• Неограниченные напоминания\n"
                "• Повторяющиеся платежи\n"
                "• Уведомления за несколько дней\n"
                "• Всего 299₽/мес\n\n"
                "Используйте команду /premium для подробной информации.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='HTML'
            )
        elif query.data == "help_btn":
            await query.edit_message_text(
                "<b>📚 Помощь по боту:</b>\n\n"
                "<b>Основные команды:</b>\n"
                "• /start — начать работу\n"
                "• /help — эта справка\n\n"
                "<b>В разработке:</b>\n"
                "• Создание напоминаний (/new)\n"
                "• Просмотр напоминаний (/list)\n"
                "• Премиум подписка (/premium)\n\n"
                "<i>Следите за обновлениями!</i>",
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте /start")

# ==================== ЗАПУСК БОТА ====================
def main():
    """Основная функция запуска"""
    # Проверяем токен
    if not TOKEN:
        logger.error("❌ Токен бота не найден! Установите переменную TELEGRAM_TOKEN")
        return
    
    logger.info("🚀 Запуск бота...")
    
    # Запускаем автопинг (чтобы бот не засыпал на Render)
    keep_alive()
    logger.info("✅ Автопинг активирован")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    logger.info("✅ Бот запущен и готов к работе!")
    logger.info("🤖 Бот будет оставаться онлайн 24/7 благодаря автопингу")
    application.run_polling()

if __name__ == '__main__':
    main()
