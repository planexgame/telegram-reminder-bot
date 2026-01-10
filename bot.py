import os
import logging
import threading
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
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
PORT = int(os.environ.get('PORT', 10000))  # Для Flask

# ==================== FLASK СЕРВЕР ДЛЯ HEALTH CHECK ====================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'bot': 'НеЗабудьОплатить',
        'timestamp': datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@flask_app.route('/ping')
def ping():
    return 'pong', 200

def run_flask():
    """Запуск Flask сервера в отдельном потоке"""
    try:
        logger.info(f"🌐 Flask сервер запускается на порту {PORT}")
        flask_app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Ошибка Flask: {e}")

# ==================== АВТОПИНГ ====================
def keep_alive():
    """Функция для поддержания бота онлайн"""
    
    def ping_self():
        """Пинг самого себя каждые 5 минут"""
        # Ждем 10 секунд чтобы Flask успел запуститься
        time.sleep(10)
        
        # URL нашего же сервиса
        render_url = os.getenv('RENDER_URL', 'https://telegram-reminder-bot-vc4c.onrender.com')
        
        # Добавляем /ping эндпоинт
        ping_url = f"{render_url}/ping"
        
        logger.info(f"🔄 Автопинг запущен. Будем пинговать: {ping_url}")
        
        while True:
            try:
                response = requests.get(ping_url, timeout=5)
                if response.status_code == 200 and response.text.strip() == 'pong':
                    logger.info(f"✅ Пинг успешен: {response.status_code}")
                else:
                    logger.warning(f"⚠️ Странный ответ: {response.status_code} - {response.text}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка пинга: {e}")
            
            # Ждем 4 минуты (240 секунд) - меньше 15 минут!
            time.sleep(240)
    
    # Запускаем в отдельном потоке
    ping_thread = threading.Thread(target=ping_self, daemon=True)
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
    
    # Запускаем Flask сервер в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask сервер запущен")
    
    # Запускаем автопинг
    keep_alive()
    logger.info("✅ Автопинг активирован")
    
    # Создаем приложение Telegram бота
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    logger.info("✅ Бот запущен и готов к работе!")
    logger.info("🌐 Доступны эндпоинты: /ping, /health, /")
    application.run_polling()

if __name__ == '__main__':
    main()
