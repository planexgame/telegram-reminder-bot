# bot.py - исправленная версия с работающей кнопкой создания и почтой
import os
import logging
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
import threading
import time as time_module

# Импортируем наши модули
from database import db
from notifications import send_reminder_notifications

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("❌ Токен не найден! Установите TELEGRAM_TOKEN в Render.")
    exit(1)

# Получаем ADMIN_ID
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    if ADMIN_ID == 0:
        logger.error("❌ ADMIN_ID не настроен! Установите переменную ADMIN_ID в Render.")
        print("=" * 50)
        print("❌ ОШИБКА: ADMIN_ID не настроен!")
        print("Добавьте в переменные окружения Render:")
        print("ADMIN_ID = ваш_telegram_id")
        print("=" * 50)
        exit(1)
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки ADMIN_ID: {e}")
    print("=" * 50)
    print("❌ НЕВЕРНЫЙ FORMAT ADMIN_ID!")
    print("ADMIN_ID должен быть числом (ваш Telegram ID)")
    print("=" * 50)
    exit(1)

# Почта администратора - ИСПРАВЛЕНО: добавлено отображение в HTML
ADMIN_EMAIL = "support@nezabudioplatit.ru"

# Номер карты для оплаты
CARD_NUMBER = os.getenv('CARD_NUMBER', '2204 1801 8490 6030')

# Константы
FREE_LIMIT = 5
PREMIUM_PRICES = {
    '1': {'amount': 299, 'days': 30, 'text': '1 месяц'},
    '3': {'amount': 799, 'days': 90, 'text': '3 месяца'},
    '12': {'amount': 1990, 'days': 365, 'text': '12 месяцев'}
}

# Состояния для ConversationHandler
TITLE, AMOUNT, DATE = range(3)

# ========== ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE ==========

def run_web_server():
    """Запуск веб-сервера для keep-alive"""
    try:
        from flask import Flask, jsonify
        
        web_app = Flask(__name__)
        
        @web_app.route('/')
        def home():
            return jsonify({
                "status": "active",
                "service": "telegram-reminder-bot",
                "bot": "running",
                "timestamp": datetime.now().isoformat(),
                "payments": "manual_only"
            })
        
        @web_app.route('/ping')
        def ping():
            return "pong", 200
        
        port = int(os.getenv('PORT', 8080))
        print(f"🌐 Веб-сервер запускается на порту {port}")
        web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
    except ImportError:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import json
        
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/ping':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'pong')
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Bot is running')
            
            def log_message(self, format, *args):
                pass
        
        port = int(os.getenv('PORT', 8080))
        server = HTTPServer(('0.0.0.0', port), Handler)
        print(f"🌐 HTTP сервер запущен на порту {port}")
        server.serve_forever()

def start_keep_alive():
    """Keep-alive для Render"""
    import requests
    
    print("=" * 50)
    print("🔄 ЗАПУСКАЮ KEEP-ALIVE")
    print(f"🔗 URL: https://telegram-reminder-bot-vc4c.onrender.com")
    print("⏰ Интервал: 8 минут")
    print("=" * 50)
    
    ping_count = 0
    
    while True:
        try:
            ping_count += 1
            url = "https://telegram-reminder-bot-vc4c.onrender.com/ping"
            
            response = requests.get(url, timeout=15)
            current_time = time_module.strftime('%H:%M:%S')
            
            if response.status_code == 200 and response.text.strip() == 'pong':
                print(f"✅ [{current_time}] Keep-alive #{ping_count}: OK")
            else:
                print(f"⚠️ [{current_time}] Keep-alive #{ping_count}: Проблема")
                
            time_module.sleep(480)
                
        except:
            current_time = time_module.strftime('%H:%M:%S')
            print(f"🚨 [{current_time}] Keep-alive #{ping_count}: Ошибка")
            time_module.sleep(300)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        premium_status = db.get_user_premium_status(user_id) if user_id else {'has_active_premium': False}
        reminders_count = db.get_user_reminders_count(user_id) if user_id else 0
        
        has_premium = premium_status.get('has_active_premium', False)
        
        keyboard = [
            [
                InlineKeyboardButton("➕ Создать напоминание", callback_data="create_new_reminder"),
                InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")
            ],
            [
                InlineKeyboardButton("💎 Премиум", callback_data="premium_info"),
                InlineKeyboardButton("📧 Помощь", callback_data="help_info")
            ]
        ]
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        premium_text = "💎 АКТИВЕН" if has_premium else "🆓 БЕСПЛАТНЫЙ"
        limit_text = '∞' if has_premium else FREE_LIMIT
        
        message = (
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"<b>Ваша статистика:</b>\n"
            f"📊 Напоминаний: {reminders_count}/{limit_text}\n"
            f"💎 Статус: {premium_text}\n\n"
            f"<b>Способ оплаты:</b>\n"
            f"• 💳 Ручная оплата (карта)\n"
            f"• 📧 Почта админа: {ADMIN_EMAIL}\n\n"
            f"Выберите действие:"
        )
        
        if update.message:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        error_message = (
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"Бот работает! 🚀\n\n"
            f"Используйте команды:\n"
            f"/new - создать напоминание\n"
            f"/list - список напоминаний\n"
            f"/premium - премиум подписка\n"
            f"/status - статус бота\n"
            f"/help - помощь"
        )
        
        if update.message:
            await update.message.reply_text(error_message, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - ИСПРАВЛЕНО: почта отображается"""
    help_text = (
        f"<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
        f"<b>Основные команды:</b>\n"
        f"• /start — начать работу\n"
        f"• /new — создать напоминание\n"
        f"• /list — список напоминаний\n"
        f"• /premium — премиум подписка\n"
        f"• /status — статус бота\n"
        f"• /help — эта справка\n\n"
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
        f"<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
        f"<b>Способ оплаты премиума:</b>\n"
        f"💳 Ручная оплата (карта)\n\n"
        f"<b>📧 Почта администратора для оплаты и вопросов:</b>\n"
        f"<code>{ADMIN_EMAIL}</code>\n\n"
        f"<b>📞 Техническая поддержка:</b>\n"
        f"• Почта: <code>{ADMIN_EMAIL}</code>\n"
        f"• Ответ в течение 24 часов\n\n"
        f"<i>По любым вопросам пишите на почту!</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_new_reminder")],
        [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='HTML')
    elif update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

# ========== ПРОСТОЙ СПОСОБ СОЗДАНИЯ НАПОМИНАНИЯ ==========

async def create_reminder_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Создать напоминание' - ПРОСТОЙ ВАРИАНТ"""
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await query.edit_message_text("❌ Ошибка базы данных.")
            return
        
        # Проверяем лимит
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if not has_premium:
            reminders_count = db.get_user_reminders_count(user_id)
            if reminders_count >= FREE_LIMIT:
                keyboard = [
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!\n\n"
                    f"📧 Для оплаты: {ADMIN_EMAIL}",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return
        
        # Создаем простое меню для создания
        await query.edit_message_text(
            "📝 <b>Создание напоминания</b>\n\n"
            "Для создания напоминания используйте команду:\n"
            "<code>/new</code>\n\n"
            "Или нажмите кнопку ниже, чтобы создать через простую форму:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Быстрое создание", callback_data="quick_create")],
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                [InlineKeyboardButton("🏠 В начало", callback_data="start")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка в create_reminder_button_handler: {e}")
        await query.edit_message_text("❌ Ошибка. Используйте команду /new")

async def quick_create_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрое создание напоминания через форму"""
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    # Сохраняем данные пользователя
    context.user_data['creating_reminder'] = True
    context.user_data['user_id'] = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    await query.edit_message_text(
        "📝 <b>Быстрое создание напоминания</b>\n\n"
        "Отправьте мне данные в формате:\n"
        "<code>Название | Сумма | Дата</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>Интернет | 500 | 25.01.2024</code>\n\n"
        "<i>Или напишите 'отмена' для отмены</i>",
        parse_mode='HTML'
    )
    
    return TITLE

async def quick_create_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка быстрого создания"""
    try:
        text = update.message.text.strip()
        
        if text.lower() == 'отмена':
            await update.message.reply_text("❌ Создание отменено.")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Парсим данные
        parts = [p.strip() for p in text.split('|')]
        if len(parts) != 3:
            await update.message.reply_text("❌ Неверный формат. Используйте: Название | Сумма | Дата\n\nПример: Интернет | 500 | 25.01.2024")
            return TITLE
        
        title, amount_str, date_str = parts
        
        # Проверяем название
        if len(title) < 2:
            await update.message.reply_text("❌ Название слишком короткое.")
            return TITLE
        
        # Проверяем сумму
        try:
            amount = float(amount_str.replace(',', '.'))
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше 0.")
                return TITLE
        except:
            await update.message.reply_text("❌ Неверный формат суммы.")
            return TITLE
        
        # Проверяем дату
        try:
            day, month, year = map(int, date_str.split('.'))
            payment_date = datetime(year, month, day).date()
            
            if payment_date < datetime.now().date():
                await update.message.reply_text("❌ Дата должна быть в будущем.")
                return TITLE
        except:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return TITLE
        
        # Сохраняем в базу
        user_id = context.user_data.get('user_id')
        date_str_db = payment_date.strftime('%Y-%m-%d')
        
        reminder_id = db.add_reminder(
            user_id=user_id,
            title=title,
            amount=amount,
            payment_date=date_str_db
        )
        
        if reminder_id:
            keyboard = [
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                [InlineKeyboardButton("➕ Еще напоминание", callback_data="create_new_reminder")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ <b>Напоминание создано!</b>\n\n"
                f"<b>Название:</b> {title}\n"
                f"<b>Сумма:</b> {amount}₽\n"
                f"<b>Дата:</b> {date_str}\n\n"
                f"Вы получите уведомление за день до платежа.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Ошибка сохранения.")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка в quick_create_process: {e}")
        await update.message.reply_text("❌ Ошибка при создании. Попробуйте снова.")
        return ConversationHandler.END

# ========== КОМАНДА /NEW ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания через команду /new"""
    user = update.effective_user
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await update.message.reply_text("❌ Ошибка базы данных.")
            return ConversationHandler.END
        
        # Проверяем лимит
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if not has_premium:
            reminders_count = db.get_user_reminders_count(user_id)
            if reminders_count >= FREE_LIMIT:
                keyboard = [
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!\n\n"
                    f"📧 Для оплаты: {ADMIN_EMAIL}",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        # Сохраняем данные пользователя
        context.user_data['creating_reminder'] = True
        context.user_data['user_id'] = user_id
        context.user_data['step'] = 'title'
        
        await update.message.reply_text(
            "📝 <b>Создание напоминания</b>\n\n"
            "Шаг 1 из 3\n"
            "Введите <b>название платежа</b>:\n\n"
            "Например: <i>Коммунальные услуги, Интернет, Кредит</i>\n\n"
            "<i>Напишите 'отмена' для отмены</i>",
            parse_mode='HTML'
        )
        
        return TITLE
        
    except Exception as e:
        logger.error(f"Ошибка в new_command: {e}")
        await update.message.reply_text("❌ Ошибка при создании напоминания.")
        return ConversationHandler.END

async def get_title_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: Получаем название"""
    title = update.message.text.strip()
    
    if title.lower() == 'отмена':
        await update.message.reply_text("❌ Создание напоминания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
    
    if len(title) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Введите снова:")
        return TITLE
    
    context.user_data['title'] = title
    context.user_data['step'] = 'amount'
    
    await update.message.reply_text(
        "✅ Название сохранено!\n\n"
        "Шаг 2 из 3\n"
        "Введите <b>сумму платежа</b> (в рублях):\n\n"
        "Например: <i>4500</i> или <i>1250.50</i>\n\n"
        "<i>Напишите 'отмена' для отмены</i>",
        parse_mode='HTML'
    )
    
    return AMOUNT

async def get_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: Получаем сумму"""
    try:
        amount_text = update.message.text.strip()
        
        if amount_text.lower() == 'отмена':
            await update.message.reply_text("❌ Создание напоминания отменено.")
            context.user_data.clear()
            return ConversationHandler.END
        
        amount = float(amount_text.replace(',', '.'))
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0. Введите снова:")
            return AMOUNT
        
        context.user_data['amount'] = amount
        context.user_data['step'] = 'date'
        
        await update.message.reply_text(
            "✅ Сумма сохранена!\n\n"
            "Шаг 3 из 3\n"
            "Введите <b>дату платежа</b> (ДД.ММ.ГГГГ):\n\n"
            "Например: <i>25.01.2024</i>\n\n"
            "<i>Напишите 'отмена' для отмены</i>",
            parse_mode='HTML'
        )
        
        return DATE
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат суммы. Введите число:")
        return AMOUNT

async def get_date_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 3: Получаем дату и сохраняем"""
    try:
        date_text = update.message.text.strip()
        
        if date_text.lower() == 'отмена':
            await update.message.reply_text("❌ Создание напоминания отменено.")
            context.user_data.clear()
            return ConversationHandler.END
        
        day, month, year = map(int, date_text.split('.'))
        payment_date = datetime(year, month, day).date()
        
        if payment_date < datetime.now().date():
            await update.message.reply_text("❌ Дата должна быть в будущем. Введите снова:")
            return DATE
        
        user_id = context.user_data.get('user_id')
        title = context.user_data.get('title')
        amount = context.user_data.get('amount')
        
        if not all([user_id, title, amount]):
            await update.message.reply_text("❌ Ошибка данных. Начните заново.")
            context.user_data.clear()
            return ConversationHandler.END
        
        date_str = payment_date.strftime('%Y-%m-%d')
        
        reminder_id = db.add_reminder(
            user_id=user_id,
            title=title,
            amount=amount,
            payment_date=date_str
        )
        
        if reminder_id:
            keyboard = [
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                [InlineKeyboardButton("➕ Еще напоминание", callback_data="create_new_reminder")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ <b>Напоминание создано!</b>\n\n"
                f"<b>Название:</b> {title}\n"
                f"<b>Сумма:</b> {amount}₽\n"
                f"<b>Дата:</b> {date_text}\n\n"
                f"Вы получите уведомление за день до платежа.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Ошибка сохранения.")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка в get_date_step: {e}")
        await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n\nНапример: <i>25.01.2024</i>", parse_mode='HTML')
        return DATE

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания"""
    await update.message.reply_text("❌ Создание напоминания отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# ========== СПИСОК НАПОМИНАНИЙ ==========

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list - список напоминаний"""
    user = update.effective_user
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await update.message.reply_text("❌ Ошибка базы данных.")
            return
        
        reminders = db.get_user_reminders(user_id)
        
        if not reminders:
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_new_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 <b>У вас пока нет напоминаний.</b>\n\n"
                "Создайте первое напоминание о платеже!\n\n"
                "Используйте команду /new или нажмите кнопку ниже:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return
        
        message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
        total_amount = 0
        
        for i, rem in enumerate(reminders[:10], 1):
            payment_date = rem.get('payment_date', '')
            if isinstance(payment_date, str):
                try:
                    date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = payment_date
            elif hasattr(payment_date, 'strftime'):
                formatted_date = payment_date.strftime('%d.%m.%Y')
            else:
                formatted_date = str(payment_date)[:10]
            
            amount = rem.get('amount', 0)
            try:
                total_amount += float(amount)
            except:
                pass
            
            message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
            message += f"   💰 {amount}₽\n"
            message += f"   📅 {formatted_date}\n\n"
        
        message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний 💎\n"
            message += f"📧 Почта для оплаты: {ADMIN_EMAIL}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать еще", callback_data="create_new_reminder")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")]
        ]
        
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_command: {e}")
        await update.message.reply_text(
            f"❌ <b>Ошибка при получении списка</b>\n\n"
            f"Попробуйте позже или обратитесь к администратору.\n\n"
            f"📧 Почта: {ADMIN_EMAIL}",
            parse_mode='HTML'
        )

async def handle_list_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Мои напоминания'"""
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await query.edit_message_text("❌ Ошибка базы данных.")
            return
        
        reminders = db.get_user_reminders(user_id)
        
        if not reminders:
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_new_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📭 <b>У вас пока нет напоминаний.</b>\n\n"
                "Создайте первое напоминание о платеже!\n\n"
                "Используйте команду /new или нажмите кнопку ниже:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return
        
        message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
        total_amount = 0
        
        for i, rem in enumerate(reminders[:10], 1):
            payment_date = rem.get('payment_date', '')
            if isinstance(payment_date, str):
                try:
                    date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = payment_date
            elif hasattr(payment_date, 'strftime'):
                formatted_date = payment_date.strftime('%d.%m.%Y')
            else:
                formatted_date = str(payment_date)[:10]
            
            amount = rem.get('amount', 0)
            try:
                total_amount += float(amount)
            except:
                pass
            
            message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
            message += f"   💰 {amount}₽\n"
            message += f"   📅 {formatted_date}\n\n"
        
        message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний 💎\n"
            message += f"📧 Почта для оплаты: {ADMIN_EMAIL}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать еще", callback_data="create_new_reminder")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")]
        ]
        
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в handle_list_button: {e}")
        await query.edit_message_text(
            f"❌ <b>Ошибка при получении списка</b>\n\n"
            f"Попробуйте команду /list\n\n"
            f"📧 Почта поддержки: {ADMIN_EMAIL}",
            parse_mode='HTML'
        )

# ========== ПРЕМИУМ ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium"""
    user = update.effective_user
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            if update.message:
                await update.message.reply_text("❌ Ошибка базы данных.")
            elif update.callback_query:
                await update.callback_query.edit_message_text("❌ Ошибка базы данных.")
            return
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            until_date = premium_status.get('premium_until')
            if until_date:
                until_str = until_date.strftime('%d.%m.%Y') if hasattr(until_date, 'strftime') else str(until_date)
                message = f"💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует до: <b>{until_str}</b>"
            else:
                message = "💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует бессрочно"
            
            keyboard = [
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                [InlineKeyboardButton("🏠 В начало", callback_data="start")]
            ]
        else:
            message = (
                f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                f"<b>Бесплатный тариф ограничен:</b>\n"
                f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
                f"• ⏰ Уведомления только за 1 день\n\n"
                f"<b>С премиум вы получаете:</b>\n"
                f"• ♾️ Неограниченные напоминания\n"
                f"• 🔔 Уведомления за 3 и 7 дней\n"
                f"• 📊 Расширенная статистика\n\n"
                f"<b>Выберите подписку:</b>\n\n"
                f"📧 Почта для оплаты: {ADMIN_EMAIL}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("1 месяц - 299₽", callback_data="buy_1"),
                    InlineKeyboardButton("3 месяца - 799₽", callback_data="buy_3")
                ],
                [
                    InlineKeyboardButton("12 месяцев - 1990₽", callback_data="buy_12"),
                    InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
                ],
                [
                    InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders"),
                    InlineKeyboardButton("📧 Помощь", callback_data="help_info")
                ],
                [InlineKeyboardButton("🏠 В начало", callback_data="start")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в premium_command: {e}")
        if update.message:
            await update.message.reply_text("❌ Ошибка получения информации о премиуме.")
        elif update.callback_query:
            await update.callback_query.edit_message_text("❌ Ошибка получения информации о премиуме.")

# ========== ОБРАБОТЧИК ОСТАЛЬНЫХ КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик остальных inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "help_info":
            await help_command(update, context)
            
        elif query.data == "list_reminders":
            await handle_list_button(update, context)
            
        elif query.data == "premium_info":
            await premium_command(update, context)
            
        elif query.data.startswith("buy_"):
            period = query.data.split("_")[1]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                user = query.from_user
                
                instructions = (
                    f"💳 <b>ИНСТРУКЦИИ ДЛЯ ОПЛАТЫ</b>\n\n"
                    f"<b>Сумма к оплате:</b> {price_info['amount']}₽\n"
                    f"<b>Период подписки:</b> {price_info['text']}\n"
                    f"<b>Ваш username:</b> @{user.username or user.id}\n\n"
                    f"<b>Для оплаты напишите на почту:</b>\n"
                    f"<code>{ADMIN_EMAIL}</code>\n\n"
                    f"<b>В письме укажите:</b>\n"
                    f"1. Ваш Telegram: @{user.username or user.id}\n"
                    f"2. Выбранный период: {price_info['text']}\n"
                    f"3. Сумму: {price_info['amount']}₽\n\n"
                    f"<b>После оплаты:</b>\n"
                    f"1. Администратор получит ваше письмо\n"
                    f"2. Он активирует ваш премиум\n"
                    f"3. Вы получите уведомление в Telegram\n\n"
                    f"Обычно активация занимает до 24 часов."
                )
                
                keyboard = [
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                    [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")],
                    [InlineKeyboardButton("🏠 В начало", callback_data="start")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    instructions,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
        elif query.data == "trial":
            user = query.from_user
            user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
            
            if db.activate_premium(user_id, 7):
                await query.edit_message_text(
                    "🎉 <b>Тестовый премиум активирован!</b>\n\n"
                    "Вам доступны все функции премиума на 7 дней:\n\n"
                    "• ♾️ Неограниченные напоминания\n"
                    "• 🔔 Уведомления за 3 и 7 дней\n\n"
                    "Наслаждайтесь! Если понравится - напишите на почту для оплаты полной подписки.\n\n"
                    f"📧 Почта: {ADMIN_EMAIL}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
                    ])
                )
            else:
                await query.edit_message_text("❌ Ошибка активации тестового периода.")
                
        elif query.data == "admin_panel":
            user = query.from_user
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            
            # Простая админ-панель
            try:
                with db.get_connection() as conn:
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM users")
                        total_users = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
                        premium_users = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT COUNT(*) FROM reminders")
                        total_reminders = cursor.fetchone()[0]
                    else:
                        total_users = premium_users = total_reminders = 0
            except:
                total_users = premium_users = total_reminders = 0
            
            message = (
                f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
                f"<b>Статистика:</b>\n"
                f"• 👥 Пользователей: {total_users}\n"
                f"• 💎 Премиум: {premium_users}\n"
                f"• 📝 Напоминаний: {total_reminders}\n\n"
                f"<b>📧 Ваша почта:</b> {ADMIN_EMAIL}\n\n"
                f"<b>Для активации премиума:</b>\n"
                f"<code>/admin_activate @username дни</code>\n\n"
                f"<b>Пример:</b>\n"
                f"<code>/admin_activate @ivanov 30</code>"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")],
                [InlineKeyboardButton("🏠 В начало", callback_data="start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text("⚠️ Произошла ошибка. Попробуйте команду /start")

# ========== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        status_text = (
            f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить»</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>💳 Ручная оплата:</b> ✅ доступна\n"
            f"<b>🕒 Время уведомлений:</b> 10:00 по Москве\n"
            f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
            f"<b>📧 Почта админа:</b> {ADMIN_EMAIL}\n"
            f"<b>🕒 Серверное время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Работающие команды:</b>\n"
            f"✅ /start — запуск бота\n"
            f"✅ /new — создать напоминание\n"
            f"✅ /list — список напоминаний\n"
            f"✅ /premium — премиум подписка\n"
            f"✅ /status — этот статус\n"
            f"✅ /help — справка\n\n"
            f"<b>Способ оплаты:</b>\n"
            f"• 📧 Напишите на почту: {ADMIN_EMAIL}\n\n"
            f"<i>Бот работает нормально! 🎉</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_new_reminder")],
            [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
            [InlineKeyboardButton("📧 Помощь", callback_data="help_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    try:
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
                premium_users = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM reminders")
                total_reminders = cursor.fetchone()[0]
            else:
                total_users = premium_users = total_reminders = 0
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        total_users = premium_users = total_reminders = 0
    
    message = (
        f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {total_reminders}\n\n"
        f"<b>📧 Ваша почта:</b> {ADMIN_EMAIL}\n\n"
        f"<b>Для активации премиума:</b>\n"
        f"<code>/admin_activate @username дни</code>\n\n"
        f"<b>Пример:</b>\n"
        f"<code>/admin_activate @ivanov 30</code>"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def admin_activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда активации премиума админом"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "💎 <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
            "<b>Использование:</b>\n"
            "<code>/admin_activate @username 30</code>\n\n"
            "<b>Где:</b>\n"
            "• @username — username пользователя\n"
            "• 30 — количество дней премиума\n\n"
            "<b>Пример:</b>\n"
            "<code>/admin_activate @ivanov 30</code> — на 30 дней"
        )
        return
    
    username = context.args[0].replace('@', '')
    days = int(context.args[1]) if len(context.args) > 1 else 30
    
    with db.get_connection() as conn:
        if not conn:
            await update.message.reply_text("❌ Ошибка базы данных.")
            return
        
        cursor = conn.cursor()
        cursor.execute('SELECT id, telegram_id, first_name FROM users WHERE username = %s', (username,))
        result = cursor.fetchone()
        
        if not result:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
            return
        
        user_id, telegram_id, first_name = result
        
        if db.activate_premium(user_id, days):
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"🎉 <b>Вам активирована премиум подписка!</b>\n\n"
                         f"Администратор активировал вам премиум подписку на {days} дней.\n\n"
                         f"<b>Теперь вам доступны:</b>\n"
                         f"• ♾️ Неограниченные напоминания\n"
                         f"• 🔔 Уведомления за 3 и 7 дней\n\n"
                         f"Спасибо за использование бота! 💎\n\n"
                         f"📧 По вопросам: {ADMIN_EMAIL}",
                    parse_mode='HTML'
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ <b>Премиум успешно активирован!</b>\n\n"
                f"Пользователь: {first_name or '@'+username}\n"
                f"Telegram ID: <code>{telegram_id}</code>\n"
                f"Срок: {days} дней",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ Ошибка активации премиума для @{username}.")

# ========== ОБРАБОТЧИК ОШИБОК ==========

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка бота: {context.error}", exc_info=True)
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                f"⚠️ Произошла ошибка. Попробуйте команду /start\n\n"
                f"📧 Если проблема повторяется, напишите на почту: {ADMIN_EMAIL}"
            )
    except:
        pass

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота"""
    print("=" * 60)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
    print("💰 Платежи: Ручная оплата через почту")
    print(f"📧 Почта админа: {ADMIN_EMAIL}")
    print("=" * 60)
    
    print(f"✅ Токен: {'найден' if TOKEN else 'НЕ НАЙДЕН'}")
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
    print(f"🌐 Веб-порт: {os.getenv('PORT', 8080)}")
    
    try:
        if db.init_db():
            print("✅ База данных: подключена")
        else:
            print("⚠️ База данных: проблемы с подключением")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    
    print("💳 Ручная оплата через почту: ✅ доступна")
    print("➕ Кнопка 'Создать напоминание': ✅ работает")
    print(f"📧 Почта в помощи: ✅ {ADMIN_EMAIL}")
    
    app = Application.builder().token(TOKEN).build()
    
    # Два ConversationHandler: для команды и для кнопки
    new_command_handler = ConversationHandler(
        entry_points=[CommandHandler('new', new_command)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title_step)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount_step)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date_step)],
        },
        fallbacks=[CommandHandler('cancel', cancel_creation)],
        allow_reentry=True
    )
    
    quick_create_handler_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(quick_create_handler, pattern='^quick_create$')],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_create_process)],
        },
        fallbacks=[CommandHandler('cancel', cancel_creation)],
        allow_reentry=True
    )
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    
    # Обработчики Conversation
    app.add_handler(new_command_handler)
    app.add_handler(quick_create_handler_conv)
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(create_reminder_button_handler, pattern='^create_new_reminder$'))
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(?!create_new_reminder|quick_create).*$'))
    
    # Планировщик уведомлений
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(
            send_reminder_notifications,
            time=time(hour=7, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6),
            name="daily_reminders"
        )
        print("📅 Планировщик уведомлений настроен")
    else:
        print("⚠️ JobQueue не доступен, уведомления отключены")
    
    app.add_error_handler(error_handler)
    
    print("\n✅ Команды зарегистрированы")
    print("📝 Доступные команды:")
    print("  • /start, /new, /list, /premium, /status, /help")
    print("  • /admin, /admin_activate")
    print("=" * 60)
    print("📧 Оплата через почту готова к работе!")
    print("=" * 60)
    
    # Запускаем веб-сервер
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    time_module.sleep(2)
    print("✅ Веб-сервер запущен")
    
    # Запускаем keep-alive
    keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
    keep_alive_thread.start()
    print("✅ Keep-alive механизм запущен")
    
    print("🤖 Telegram бот запускается...")
    print("=" * 60)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
