import os
import logging
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from telegram.error import TelegramError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
TOKEN = os.getenv('TELEGRAM_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

class Database:
    def __init__(self):
        self.conn = None
        
    def connect(self):
        """Подключение к PostgreSQL"""
        try:
            self.conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            logger.info("✅ Подключение к БД успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            return False
    
    def init_db(self):
        """Инициализация таблиц"""
        if not DATABASE_URL:
            logger.warning("⚠️ DATABASE_URL не найден. База данных отключена.")
            return False
            
        if not self.connect():
            return False
            
        try:
            cursor = self.conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    is_premium BOOLEAN DEFAULT FALSE,
                    premium_until DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица напоминаний
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    title VARCHAR(255) NOT NULL,
                    amount DECIMAL(10, 2),
                    payment_date DATE NOT NULL,
                    recurrence VARCHAR(20) DEFAULT 'once',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.conn.commit()
            logger.info("✅ Таблицы созданы/проверены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()

# Создаем экземпляр БД
db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Простое сообщение для начала
    keyboard = [
        [
            InlineKeyboardButton("➕ Создать напоминание", callback_data="create"),
            InlineKeyboardButton("📋 Мои напоминания", callback_data="list")
        ],
        [
            InlineKeyboardButton("💎 Премиум", callback_data="premium"),
            InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — бот для напоминаний о платежах.\n\n"
        "🎯 *Бесплатно:* до 5 напоминаний\n"
        "💎 *Премиум:* неограниченно\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - исправленная версия"""
    try:
        await update.message.reply_text(
            "📚 *Помощь по боту:*\n\n"
            "Основные команды:\n"
            "• /start - начать работу\n"
            "• /new - создать напоминание (скоро)\n"
            "• /list - список напоминаний (скоро)\n"
            "• /premium - информация о подписке (скоро)\n\n"
            "По вопросам пишите: @your_support",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в help_command: {e}")
        await update.message.reply_text("📚 Используйте команду /start для начала работы.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "create":
            await query.edit_message_text(
                "🔄 *Создание напоминания*\n\n"
                "Используйте команду /new для создания напоминаний.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='Markdown'
            )
        elif query.data == "list":
            await query.edit_message_text(
                "📋 *Ваши напоминания*\n\n"
                "Используйте команду /list для просмотра напоминаний.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='Markdown'
            )
        elif query.data == "premium":
            await query.edit_message_text(
                "💎 *Премиум подписка*\n\n"
                "• Неограниченные напоминания\n"
                "• Повторяющиеся платежи\n"
                "• Уведомления за несколько дней\n"
                "• Всего 299₽/мес\n\n"
                "Используйте команду /premium для подробной информации.\n"
                "Эта функция скоро будет доступна!",
                parse_mode='Markdown'
            )
        elif query.data == "help_btn":
            # Отправляем новое сообщение вместо редактирования
            await query.message.reply_text(
                "📚 *Помощь по боту:*\n\n"
                "Основные команды:\n"
                "• /start - начать работу\n"
                "• /help - эта справка\n\n"
                "Функции в разработке:\n"
                "• Создание напоминаний (/new)\n"
                "• Просмотр напоминаний (/list)\n"
                "• Премиум подписка (/premium)\n\n"
                "Следите за обновлениями!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте снова.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    try:
        # Отправляем сообщение об ошибке пользователю
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Попробуйте команду /start"
            )
    except:
        pass

def main():
    """Основная функция запуска"""
    # Проверяем токен
    if not TOKEN:
        logger.error("❌ Токен бота не найден! Установите переменную TELEGRAM_TOKEN")
        return
    
    logger.info("🚀 Запуск бота...")
    
    # Инициализация БД
    if DATABASE_URL:
        db.init_db()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("✅ Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == '__main__':
    main()
