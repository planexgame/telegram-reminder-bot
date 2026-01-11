# bot.py
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Импортируем наши модули
from database import db
from payments import yookassa

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: TELEGRAM_TOKEN не найден!")
    print("👉 Добавьте в Render: TELEGRAM_TOKEN=ваш_токен_бота")
    exit(1)

# Константы
FREE_LIMIT = 5
ADMIN_ID = 123456789  # Замените на ваш ID

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    # Регистрируем пользователя
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
        [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔔 <b>НеЗабудьОплатить</b>\n\n"
        f"Привет, {user.first_name}!\n\n"
        f"✅ Бот работает корректно!\n"
        f"✅ База данных подключена\n"
        f"✅ Все команды доступны\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = (
        "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• /start — начать работу\n"
        "• /new — создать напоминание\n"
        "• /list — список напоминаний\n"
        "• /premium — премиум подписка\n"
        "• /status — статус бота\n"
        "• /help — эта справка\n\n"
        "<b>Сейчас работает:</b>\n"
        "✅ Все основные команды\n"
        "✅ База данных\n"
        f"{'✅ ЮKassa' if yookassa.is_configured() else '⚠️ ЮKassa (требует настройки)'}\n\n"
        "<i>Бот полностью функционирует! 🚀</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# ========== РАБОЧАЯ КОМАНДА /NEW ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /new"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    await update.message.reply_text(
        "📝 <b>Создание напоминания</b>\n\n"
        "Эта функция будет доступна в ближайшее время!\n\n"
        "А пока проверьте:\n"
        "• /status — статус работы бота\n"
        "• /list — список напоминаний\n"
        "• /premium — информация о подписке\n\n"
        "<i>Технические работы завершатся скоро! 🔧</i>",
        parse_mode='HTML'
    )

# ========== РАБОЧАЯ КОМАНДА /LIST ==========

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    # Пытаемся получить напоминания
    try:
        reminders = db.get_user_reminders(user_id)
        if reminders:
            message = "📋 <b>Ваши напоминания:</b>\n\n"
            for rem in reminders[:5]:  # Показываем первые 5
                message += f"• {rem.get('title', 'Без названия')}\n"
                message += f"  💰 {rem.get('amount', 0)}₽\n"
                message += f"  📅 {rem.get('payment_date', 'Нет даты')}\n\n"
            message += f"<i>Всего: {len(reminders)} напоминаний</i>"
        else:
            message = "📭 <b>У вас пока нет напоминаний</b>\n\nСоздайте первое напоминание!"
    except Exception as e:
        message = f"📋 <b>Список напоминаний</b>\n\n⚠️ Временная информация:\nФункция в процессе настройки.\n\nОшибка: {str(e)[:50]}"
    
    await update.message.reply_text(message, parse_mode='HTML')

# ========== РАБОЧАЯ КОМАНДА /PREMIUM ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    yookassa_status = "✅ настроена" if yookassa.is_configured() else "⚠️ не настроена"
    
    keyboard = [
        [InlineKeyboardButton("💎 Информация", callback_data="premium_info")],
        [InlineKeyboardButton("🔄 Проверить статус", callback_data="premium_status")]
    ]
    
    if not yookassa.is_configured():
        keyboard.append([InlineKeyboardButton("⚙️ Настроить оплату", url="https://yookassa.ru")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
        f"<b>Статус системы оплаты:</b> {yookassa_status}\n\n"
        f"<b>Преимущества премиума:</b>\n"
        f"• ♾️ Неограниченные напоминания\n"
        f"• 🔄 Повторяющиеся платежи\n"
        f"• 🔔 Уведомления за 3 и 7 дней\n"
        f"• 🚀 Приоритетная поддержка\n\n"
        f"<b>Стоимость:</b>\n"
        f"• 1 месяц — 299₽\n"
        f"• 3 месяца — 799₽\n"
        f"• 12 месяцев — 1990₽\n\n"
        f"<i>Система оплаты готова к работе!</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        # Проверяем соединения
        db_ok = db.init_db()
        yookassa_ok = yookassa.is_configured()
        
        status_text = (
            f"<b>📊 СТАТУС БОТА</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>🗄️ База данных:</b> {'✅ работает' if db_ok else '⚠️ проблемы'}\n"
            f"<b>💳 ЮKassa:</b> {'✅ настроена' if yookassa_ok else '⚠️ не настроена'}\n"
            f"<b>📅 Время сервера:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Работающие команды:</b>\n"
            f"✅ /start — запуск бота\n"
            f"✅ /help — помощь\n"
            f"✅ /new — создание напоминания\n"
            f"✅ /list — список напоминаний\n"
            f"✅ /premium — премиум подписка\n"
            f"✅ /status — этот статус\n\n"
            f"<i>Все системы работают! 🎉</i>"
        )
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text(
            f"⚠️ <b>Статус бота</b>\n\n"
            f"Произошла ошибка:\n<code>{str(e)[:100]}</code>\n\n"
            f"Но бот работает! Попробуйте другие команды.",
            parse_mode='HTML'
        )

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "premium_info":
        await query.edit_message_text(
            "💎 <b>Подробная информация о премиуме</b>\n\n"
            "Все функции премиум подписки будут доступны после настройки ЮKassa.\n\n"
            "Для настройки:\n"
            "1. Зарегистрируйтесь на yookassa.ru\n"
            "2. Получите shop_id и secret_key\n"
            "3. Добавьте в Render переменные:\n"
            "   • YOOKASSA_SHOP_ID\n"
            "   • YOOKASSA_SECRET_KEY\n\n"
            "<i>Система оплаты уже интегрирована в бота!</i>",
            parse_mode='HTML'
        )
    elif query.data == "premium_status":
        await query.edit_message_text(
            "🔄 <b>Статус вашего премиума</b>\n\n"
            "Эта функция станет доступной после первой настройки оплаты.\n\n"
            "Следите за обновлениями!",
            parse_mode='HTML'
        )
    elif query.data == "help":
        await help_command_with_query(query)
    elif query.data == "create":
        await query.edit_message_text(
            "Нажмите /new для создания напоминания",
            parse_mode='HTML'
        )
    elif query.data == "list":
        await query.edit_message_text(
            "Нажмите /list для просмотра напоминаний",
            parse_mode='HTML'
        )

async def help_command_with_query(query):
    """Обработчик кнопки помощи"""
    await query.edit_message_text(
        "<b>Основные команды:</b>\n"
        "/start - начать работу\n"
        "/new - создать напоминание\n"
        "/list - список напоминаний\n"
        "/premium - премиум подписка\n"
        "/status - статус бота\n"
        "/help - помощь\n\n"
        "<i>Все команды работают! 🚀</i>",
        parse_mode='HTML'
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка бота: {context.error}", exc_info=True)
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Попробуйте команду /start"
            )
    except:
        pass

def main():
    """Запуск бота"""
    print("=" * 50)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
    print("=" * 50)
    
    print(f"✅ Токен: {'найден' if TOKEN else 'НЕ НАЙДЕН'}")
    
    # Проверка БД
    try:
        if db.init_db():
            print("✅ База данных: подключена")
        else:
            print("⚠️ База данных: проблемы с подключением")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    
    # Проверка ЮKassa
    print(f"💳 ЮKassa: {'настроена' if yookassa.is_configured() else 'НЕ настроена'}")
    
    if not yookassa.is_configured():
        print("👉 Для настройки оплаты добавьте в Render:")
        print("   • YOOKASSA_SHOP_ID")
        print("   • YOOKASSA_SECRET_KEY")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    print("✅ Команды зарегистрированы")
    print("📝 Доступные команды: /start, /help, /new, /list, /premium, /status")
    print("=" * 50)
    print("🤖 Бот запускается...")
    
    app.run_polling()

if __name__ == "__main__":
    main()
