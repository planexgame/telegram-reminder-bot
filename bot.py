# bot.py - полный исправленный код с Telegram Stars
import os
import logging
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    PreCheckoutQueryHandler
)
import threading
import time as time_module
import asyncio

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

# Константы
FREE_LIMIT = 5
PREMIUM_PRICES = {
    '1': {'stars': 299, 'days': 30, 'text': '1 месяц'},
    '3': {'stars': 799, 'days': 90, 'text': '3 месяца'},
    '12': {'stars': 1990, 'days': 365, 'text': '12 месяцев'}
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
                "payments": "telegram_stars"
            })
        
        @web_app.route('/ping')
        def ping():
            return "pong", 200
        
        @web_app.route('/health')
        def health():
            try:
                conn = db.get_connection()
                db_status = "connected" if conn else "disconnected"
                
                return jsonify({
                    "status": "healthy",
                    "database": db_status,
                    "bot": "running",
                    "timestamp": datetime.now().isoformat(),
                    "version": "2.0.0"
                }), 200
            except Exception as e:
                return jsonify({
                    "status": "unhealthy",
                    "error": str(e)[:100],
                    "timestamp": datetime.now().isoformat()
                }), 500
        
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
                elif self.path == '/health' or self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = json.dumps({
                        "status": "healthy",
                        "service": "telegram-bot",
                        "timestamp": datetime.now().isoformat()
                    })
                    self.wfile.write(response.encode())
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
    errors_count = 0
    
    while True:
        try:
            ping_count += 1
            url = "https://telegram-reminder-bot-vc4c.onrender.com/ping"
            
            response = requests.get(url, timeout=15)
            current_time = time_module.strftime('%H:%M:%S')
            
            if response.status_code == 200:
                if response.text.strip() == 'pong':
                    print(f"✅ [{current_time}] Keep-alive #{ping_count}: OK")
                    errors_count = 0
                else:
                    print(f"⚠️ [{current_time}] Keep-alive #{ping_count}: Неверный ответ")
                    errors_count += 1
            else:
                print(f"❌ [{current_time}] Keep-alive #{ping_count}: Код {response.status_code}")
                errors_count += 1
                
            if errors_count > 3:
                time_module.sleep(600)
            else:
                time_module.sleep(480)
                
        except requests.exceptions.Timeout:
            current_time = time_module.strftime('%H:%M:%S')
            print(f"⏱️ [{current_time}] Keep-alive #{ping_count}: Таймаут")
            errors_count += 1
            time_module.sleep(300)
            
        except Exception as e:
            current_time = time_module.strftime('%H:%M:%S')
            print(f"🚨 [{current_time}] Keep-alive #{ping_count}: {str(e)[:80]}")
            errors_count += 1
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
                InlineKeyboardButton("➕ Создать напоминание", callback_data="create"),
                InlineKeyboardButton("📋 Мои напоминания", callback_data="list")
            ],
            [
                InlineKeyboardButton("⭐ Премиум", callback_data="premium_info"),
                InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")
            ]
        ]
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        premium_text = "⭐ АКТИВЕН" if has_premium else "🆓 БЕСПЛАТНЫЙ"
        limit_text = '∞' if has_premium else FREE_LIMIT
        
        message = (
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"<b>Ваша статистика:</b>\n"
            f"📊 Напоминаний: {reminders_count}/{limit_text}\n"
            f"⭐ Статус: {premium_text}\n\n"
            f"<b>Способы оплаты:</b>\n"
            f"• ⭐ Telegram Stars (автоматически)\n"
            f"• 💳 Ручная оплата (карта)\n\n"
            f"Выберите действие:"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text(
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"Бот работает! 🚀\n\n"
            f"Используйте команды:\n"
            f"/new - создать напоминание\n"
            f"/list - список напоминаний\n"
            f"/premium - премиум подписка\n"
            f"/status - статус бота",
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
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
        "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
        "<b>Способы оплаты премиума:</b>\n"
        "1. ⭐ Telegram Stars (встроенная оплата)\n"
        "2. 💳 Ручная оплата (перевод на карту)\n\n"
        "<i>По вопросам обращайтесь к администратору</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# ========== КОМАНДА /NEW ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания"""
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
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if not has_premium:
            reminders_count = db.get_user_reminders_count(user_id)
            if reminders_count >= FREE_LIMIT:
                keyboard = [
                    [InlineKeyboardButton("⭐ Купить премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "⭐ <b>Премиум подписка</b> дает неограниченное количество напоминаний!",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        await update.message.reply_text(
            "📝 <b>Создание напоминания</b>\n\n"
            "Шаг 1 из 3\n"
            "Введите <b>название платежа</b>:\n\n"
            "Например: <i>Коммунальные услуги, Интернет, Кредит</i>",
            parse_mode='HTML'
        )
        
        context.user_data['user_id'] = user_id
        return TITLE
        
    except Exception as e:
        logger.error(f"Ошибка в new_command: {e}")
        await update.message.reply_text("❌ Ошибка при создании напоминания.")
        return ConversationHandler.END

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем название"""
    title = update.message.text.strip()
    
    if len(title) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Введите снова:")
        return TITLE
    
    context.user_data['title'] = title
    
    await update.message.reply_text(
        "Шаг 2 из 3\n"
        "Введите <b>сумму платежи</b> (в рублях):\n\n"
        "Например: <i>4500</i> или <i>1250.50</i>",
        parse_mode='HTML'
    )
    
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем сумму"""
    try:
        amount_text = update.message.text.replace(',', '.').strip()
        amount = float(amount_text)
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0.")
            return AMOUNT
        
        context.user_data['amount'] = amount
        
        await update.message.reply_text(
            "Шаг 3 из 3\n"
            "Введите <b>дату платежа</b> (ДД.ММ.ГГГГ):\n\n"
            "Например: <i>25.01.2024</i>",
            parse_mode='HTML'
        )
        
        return DATE
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат суммы. Введите число:")
        return AMOUNT

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем дату и сохраняем"""
    try:
        date_text = update.message.text.strip()
        day, month, year = map(int, date_text.split('.'))
        payment_date = datetime(year, month, day).date()
        
        if payment_date < datetime.now().date():
            await update.message.reply_text("❌ Дата должна быть в будущем.")
            return DATE
        
        user_id = context.user_data.get('user_id')
        title = context.user_data.get('title')
        amount = context.user_data.get('amount')
        
        if not all([user_id, title, amount]):
            await update.message.reply_text("❌ Ошибка данных. Начните заново.")
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
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                [InlineKeyboardButton("➕ Еще напоминание", callback_data="create")]
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
        logger.error(f"Ошибка в get_date: {e}")
        await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
        return DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания"""
    await update.message.reply_text("❌ Создание напоминания отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# ========== КОМАНДА /LIST ==========

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
        
        reminders = []
        try:
            reminders = db.get_user_reminders(user_id)
        except Exception as e:
            logger.error(f"Ошибка получения напоминаний: {e}")
        
        if not reminders:
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
                [InlineKeyboardButton("⭐ Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="list")]
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
                    try:
                        date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    except:
                        date_obj = datetime.strptime(payment_date, '%d.%m.%Y')
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
            
            recurrence_icon = "🔄 " if rem.get('recurrence') != 'once' else ""
            
            message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
            message += f"   💰 {amount}₽\n"
            message += f"   📅 {formatted_date} {recurrence_icon}\n\n"
        
        message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний ⭐\n"
        
        keyboard = []
        
        delete_buttons = []
        for i in range(min(3, len(reminders))):
            reminder = reminders[i]
            title_short = reminder.get('title', 'Без названия')[:15]
            reminder_id = reminder.get('id')
            if reminder_id:
                delete_buttons.append(
                    InlineKeyboardButton(
                        f"🗑 {i+1}. {title_short}...",
                        callback_data=f"delete_{reminder_id}"
                    )
                )
        
        for i in range(0, len(delete_buttons), 2):
            row = delete_buttons[i:i+2]
            keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
        ])
        
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("⭐ Купить премиум", callback_data="premium_info")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_command: {e}")
        await update.message.reply_text(
            f"❌ <b>Ошибка при получении списка</b>\n\n"
            f"Попробуйте позже или обратитесь к администратору.\n\n"
            f"Ошибка: {str(e)[:100]}",
            parse_mode='HTML'
        )

# ========== ОБРАБОТЧИК КНОПКИ "МОИ НАПОМИНАНИЯ" ==========

async def handle_list_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопки 'Мои напоминания'"""
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
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
                [InlineKeyboardButton("⭐ Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="list")]
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
                    try:
                        date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    except:
                        date_obj = datetime.strptime(payment_date, '%d.%m.%Y')
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
            
            recurrence_icon = "🔄 " if rem.get('recurrence') != 'once' else ""
            
            message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
            message += f"   💰 {amount}₽\n"
            message += f"   📅 {formatted_date} {recurrence_icon}\n\n"
        
        message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на сумма {total_amount:.2f}₽\n"
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний ⭐\n"
        
        keyboard = []
        
        delete_buttons = []
        for i in range(min(3, len(reminders))):
            reminder = reminders[i]
            title_short = reminder.get('title', 'Без названия')[:15]
            reminder_id = reminder.get('id')
            if reminder_id:
                delete_buttons.append(
                    InlineKeyboardButton(
                        f"🗑 {i+1}. {title_short}...",
                        callback_data=f"delete_{reminder_id}"
                    )
                )
        
        for i in range(0, len(delete_buttons), 2):
            row = delete_buttons[i:i+2]
            keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
        ])
        
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("⭐ Купить премиум", callback_data="premium_info")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в handle_list_button: {e}")
        await query.edit_message_text(
            f"❌ <b>Ошибка при получении списка</b>\n\n"
            f"Попробуйте команду /list\n\n"
            f"Ошибка: {str(e)[:100]}",
            parse_mode='HTML'
        )

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        status_text = (
            f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить»</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>⭐ Telegram Stars:</b> ✅ доступен\n"
            f"<b>💳 Ручная оплата:</b> ✅ доступна\n"
            f"<b>🕒 Время уведомлений:</b> 10:00 по Москве\n"
            f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
            f"<b>🕒 Серверное время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Работающие команды:</b>\n"
            f"✅ /start — запуск бота\n"
            f"✅ /new — создание напоминания\n"
            f"✅ /list — список напоминаний\n"
            f"✅ /premium — премиум подписка\n"
            f"✅ /status — этот статус\n"
            f"✅ /help — справка\n\n"
            f"<b>Способы оплаты:</b>\n"
            f"• ⭐ Telegram Stars (встроенная оплата)\n"
            f"• 💳 Ручная оплата (карта)\n\n"
            f"<i>Все системы работают нормально! 🎉</i>"
        )
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

# ========== ПРЕМИУМ КОМАНДЫ ==========

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
            await update.message.reply_text("❌ Ошибка базы данных.")
            return
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            until_date = premium_status.get('premium_until')
            if until_date:
                until_str = until_date.strftime('%d.%m.%Y') if hasattr(until_date, 'strftime') else str(until_date)
                message = f"⭐ <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует до: <b>{until_str}</b>"
            else:
                message = "⭐ <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует бессрочно"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")],
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
            ]
        else:
            message = (
                f"⭐ <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                f"<b>Бесплатный тариф ограничен:</b>\n"
                f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
                f"• ⏰ Уведомления только за 1 день\n"
                f"• 🔄 Нет повторяющихся платежей\n\n"
                f"<b>С премиум вы получаете:</b>\n"
                f"• ♾️ Неограниченные напоминания\n"
                f"• 🔄 Повторяющиеся платежи\n"
                f"• 🔔 Уведомления за 3 и 7 дней\n"
                f"• 📊 Расширенная статистика\n\n"
                f"<b>Выберите способ оплаты:</b>"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("⭐ Telegram Stars", callback_data="stars_payment"),
                    InlineKeyboardButton("💳 Ручная оплата", callback_data="manual_payment")
                ],
                [
                    InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status"),
                    InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в premium_command: {e}")
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Ошибка получения информации о премиуме.")
        else:
            await update.message.reply_text("❌ Ошибка получения информации о премиуме.")

async def stars_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора оплаты через Stars"""
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
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            await query.edit_message_text(
                "✅ У вас уже активна премиум подписка!\n\n"
                "Используйте команду /premium чтобы увидеть детали."
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("⭐ 1 месяц - 299 Stars", callback_data="stars_buy_1"),
                InlineKeyboardButton("⭐ 3 месяца - 799 Stars", callback_data="stars_buy_3")
            ],
            [
                InlineKeyboardButton("⭐ 12 месяцев - 1990 Stars", callback_data="stars_buy_12"),
                InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
            ],
            [
                InlineKeyboardButton("💳 Перейти к ручной оплате", callback_data="manual_payment"),
                InlineKeyboardButton("↩️ Назад", callback_data="premium_info")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⭐ <b>ОПЛАТА ЧЕРЕЗ TELEGRAM STARS</b>\n\n"
            "Telegram Stars — это встроенная система оплаты в Telegram.\n\n"
            "<b>Преимущества:</b>\n"
            "• ⚡ Мгновенная активация\n"
            "• 🔒 Безопасная оплата\n"
            "• 📱 Удобно через приложение\n\n"
            "<b>Выберите подписку:</b>\n\n"
            "• <b>1 месяц</b> — 299 Stars\n"
            "   👉 Для тестирования\n\n"
            "• <b>3 месяца</b> — 799 Stars\n"
            "   👉 Экономия 11%\n\n"
            "• <b>12 месяцев</b> — 1990 Stars\n"
            "   👉 Экономия 45%\n\n"
            "• <b>7 дней теста</b> — бесплатно\n"
            "   👉 Все функции премиума",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в stars_payment_handler: {e}")
        await query.edit_message_text("❌ Ошибка при оформлении подписки.")

async def manual_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора ручной оплаты"""
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
        
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            await query.edit_message_text(
                "✅ У вас уже активна премиум подписка!\n\n"
                "Используйте команду /premium чтобы увидеть детали."
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("1 месяц - 299₽", callback_data="manual_buy_1"),
                InlineKeyboardButton("3 месяца - 799₽", callback_data="manual_buy_3")
            ],
            [
                InlineKeyboardButton("12 месяцев - 1990₽", callback_data="manual_buy_12"),
                InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
            ],
            [
                InlineKeyboardButton("⭐ Перейти к Telegram Stars", callback_data="stars_payment"),
                InlineKeyboardButton("↩️ Назад", callback_data="premium_info")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💳 <b>РУЧНАЯ ОПЛАТА</b>\n\n"
            "После выбора подписки вы получите реквизиты для оплаты.\n"
            "Администратор активирует премиум вручную после получения платежа.\n\n"
            "<b>Доступные способы оплаты:</b>\n"
            "• 💳 Перевод на карту\n\n"
            "<b>Выберите подписку:</b>\n\n"
            "• <b>1 месяц</b> — 299₽\n"
            "   👉 Для тестирования\n\n"
            "• <b>3 месяца</b> — 799₽\n"
            "   👉 Экономия 11%\n\n"
            "• <b>12 месяцев</b> — 1990₽\n"
            "   👉 Экономия 45%\n\n"
            "• <b>7 дней теста</b> — бесплатно\n"
            "   👉 Все функции премиума",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в manual_payment_handler: {e}")
        await query.edit_message_text("❌ Ошибка при оформлении подписки.")

# ========== ОБРАБОТКА TELEGRAM STARS ==========

async def stars_pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение платежа перед списанием Stars"""
    query = update.pre_checkout_query
    
    try:
        payload = query.invoice_payload
        if payload.startswith("premium_"):
            period = payload.split("_")[1]
            
            if period in PREMIUM_PRICES:
                expected_amount = PREMIUM_PRICES[period]['stars'] * 100
                
                if query.total_amount == expected_amount:
                    await query.answer(ok=True)
                    logger.info(f"✅ Pre-checkout подтвержден: {payload}")
                else:
                    await query.answer(
                        ok=False, 
                        error_message=f"Неверная сумма. Ожидается {PREMIUM_PRICES[period]['stars']} Stars"
                    )
            else:
                await query.answer(
                    ok=False, 
                    error_message="Неверный период подписки"
                )
        else:
            await query.answer(
                ok=False, 
                error_message="Неверный payload"
            )
            
    except Exception as e:
        logger.error(f"Ошибка pre-checkout: {e}")
        await query.answer(
            ok=False,
            error_message="Внутренняя ошибка. Попробуйте позже."
        )

async def stars_successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешного платежа через Telegram Stars"""
    try:
        payment = update.message.successful_payment
        payload = payment.invoice_payload
        
        if not payload.startswith("premium_"):
            logger.error(f"Неизвестный payload: {payload}")
            return
        
        period = payload.split("_")[1]
        
        if period not in PREMIUM_PRICES:
            logger.error(f"Неизвестный период: {period}")
            return
        
        user = update.effective_user
        
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await update.message.reply_text(
                "❌ Ошибка активации. Свяжитесь с администратором."
            )
            return
        
        payment_id = db.create_payment(
            user_id=user_id,
            amount=payment.total_amount / 100,
            period_days=PREMIUM_PRICES[period]['days']
        )
        
        if payment_id:
            db.update_payment_status(
                payment_id=payment_id,
                status='succeeded',
                telegram_payment_id=payment.telegram_payment_charge_id
            )
            
            if db.activate_premium(user_id, PREMIUM_PRICES[period]['days']):
                await update.message.reply_text(
                    f"🎉 <b>ОПЛАТА УСПЕШНА!</b>\n\n"
                    f"✅ Премиум подписка на {PREMIUM_PRICES[period]['text']} активирована.\n"
                    f"⭐ Оплачено: {payment.total_amount/100} Stars\n"
                    f"🆔 ID платежа: {payment.telegram_payment_charge_id}\n\n"
                    f"<b>Теперь вам доступны:</b>\n"
                    f"• ♾️ Неограниченные напоминания\n"
                    f"• 🔄 Повторяющиеся платежи\n"
                    f"• 🔔 Уведомления за 3 и 7 дней\n\n"
                    f"Спасибо за покупку! ⭐",
                    parse_mode='HTML'
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"💰 <b>НОВЫЙ ПЛАТЕЖ TELEGRAM STARS</b>\n\n"
                             f"👤 Пользователь: @{user.username or user.id}\n"
                             f"📦 Подписка: {PREMIUM_PRICES[period]['text']}\n"
                             f"⭐ Stars: {payment.total_amount/100}\n"
                             f"🆔 Payment ID: {payment.telegram_payment_charge_id}\n"
                             f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                             f"Премиум активирован автоматически.",
                        parse_mode='HTML'
                    )
                except Exception as admin_error:
                    logger.error(f"Не удалось уведомить админа: {admin_error}")
                
                logger.info(f"✅ Премиум активирован через Stars: user={user.id}, period={period}")
            else:
                await update.message.reply_text(
                    "❌ Ошибка активации премиума. Свяжитесь с администратором."
                )
        else:
            await update.message.reply_text(
                "❌ Ошибка записи платежа. Свяжитесь с администратором."
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки Stars платежа: {e}", exc_info=True)
        
        try:
            await update.message.reply_text(
                "❌ Ошибка обработки платежа. Свяжитесь с администратором."
            )
        except:
            pass

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "create":
            await query.edit_message_text(
                "📝 <b>СОЗДАНИЕ НАПОМИНАНИЯ</b>\n\n"
                "Для создания напоминания используйте команду:\n"
                "<code>/new</code>\n\n"
                "Или нажмите на одну из кнопок ниже:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                    [InlineKeyboardButton("⭐ Премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data == "list":
            await handle_list_button(update, context)
            
        elif query.data == "premium_info":
            await premium_command(update, context)
            
        elif query.data == "stars_payment":
            await stars_payment_handler(update, context)
            
        elif query.data == "manual_payment":
            await manual_payment_handler(update, context)
            
        elif query.data.startswith("stars_buy_"):
            period = query.data.split("_")[2]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                user = query.from_user
                
                try:
                    await query.edit_message_text(
                        f"⭐ <b>СОЗДАНИЕ СЧЕТА...</b>\n\n"
                        f"Подписка: {price_info['text']}\n"
                        f"Стоимость: {price_info['stars']} Stars\n\n"
                        f"<i>Сейчас откроется окно оплаты...</i>",
                        parse_mode='HTML'
                    )
                    
                    await context.bot.send_invoice(
                        chat_id=user.id,
                        title=f"Премиум подписка на {price_info['text']}",
                        description="Доступ к неограниченным напоминаниям и расширенным функциям",
                        payload=f"premium_{period}",
                        provider_token=None,  # ⭐ Важно: None для Telegram Stars!
                        currency="XTR",
                        prices=[
                            LabeledPrice(label="Премиум подписка", amount=price_info['stars'] * 100)
                        ],
                        max_tip_amount=50000,
                        suggested_tip_amounts=[5000, 10000, 25000],
                        start_parameter=f"premium_{user.id}",
                        need_name=False,
                        need_phone_number=False,
                        need_email=False,
                        need_shipping_address=False,
                        is_flexible=False
                    )
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки инвойса: {e}")
                    
                    await query.edit_message_text(
                        f"❌ <b>Ошибка создания платежа</b>\n\n"
                        f"Причина: {str(e)[:200]}\n\n"
                        f"<b>Возможные решения:</b>\n"
                        f"1. Обновите приложение Telegram\n"
                        f"2. Попробуйте ручную оплату\n"
                        f"3. Свяжитесь с администратором",
                        parse_mode='HTML'
                    )
            else:
                await query.edit_message_text("❌ Неверный период подписки.")
                
        elif query.data.startswith("manual_buy_"):
            period = query.data.split("_")[2]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                user = query.from_user
                
                instructions = (
                    f"💳 <b>ИНСТРУКЦИИ ДЛЯ РУЧНОЙ ОПЛАТЫ</b>\n\n"
                    f"<b>Сумма к оплате:</b> {price_info['stars']}₽\n"
                    f"<b>Период подписки:</b> {price_info['text']}\n"
                    f"<b>Ваш username:</b> @{user.username or user.id}\n\n"
                    f"<b>Перевод на карту:</b>\n"
                    f"Номер карты: <code>2204 1801 8490 6030</code>\n"
                    f"Банк: Тинькофф\n\n"
                    f"<b>Обязательно укажите в комментарии:</b>\n"
                    f"<code>@{user.username or user.id} премиум {price_info['text']}</code>\n\n"
                    f"<b>После перевода:</b>\n"
                    f"1. Нажмите кнопку '✅ Я оплатил'\n"
                    f"2. Администратор проверит платеж\n"
                    f"3. Вы получите уведомление об активации\n\n"
                    f"Обычно активация занимает до 24 часов."
                )
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{period}")],
                    [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"stars_buy_{period}")],
                    [InlineKeyboardButton("↩️ Назад", callback_data="manual_payment")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    instructions,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Неверный период подписки.")
                
        elif query.data == "premium_status":
            user = query.from_user
            user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
            
            if user_id:
                premium_status = db.get_user_premium_status(user_id)
                has_premium = premium_status.get('has_active_premium', False) if premium_status else False
                
                if has_premium:
                    until_date = premium_status.get('premium_until')
                    if until_date:
                        until_str = until_date.strftime('%d.%m.%Y') if hasattr(until_date, 'strftime') else str(until_date)
                        message = f"⭐ <b>ПРЕМИУМ СТАТУС</b>\n\nВаш премиум действует до: <b>{until_str}</b>"
                    else:
                        message = "⭐ <b>ПРЕМИУМ СТАТУС</b>\n\nУ вас активна бессрочная премиум подписка!"
                    
                    keyboard = [
                        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                        [InlineKeyboardButton("🔄 Обновить статус", callback_data="premium_status")]
                    ]
                else:
                    message = "🆓 <b>ПРЕМИУМ СТАТУС</b>\n\nУ вас нет активной премиум подписки."
                    keyboard = [
                        [InlineKeyboardButton("⭐ Купить премиум", callback_data="premium_info")],
                        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
                    ]
                
                await query.edit_message_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Ошибка получения статуса.")
                
        elif query.data.startswith("delete_"):
            try:
                reminder_id = int(query.data.split("_")[1])
                user = query.from_user
                
                user_id = db.get_or_create_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                
                if db.delete_reminder(user_id, reminder_id):
                    await handle_list_button(update, context)
                else:
                    await query.edit_message_text("❌ Не удалось удалить напоминание.")
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
                await query.edit_message_text("❌ Ошибка при удалении.")
                
        elif query.data == "help_btn":
            await query.edit_message_text(
                "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
                "<b>Основные команды:</b>\n"
                "• /start — начать работу\n"
                "• /new — создать напоминание\n"
                "• /list — список напоминаний\n"
                "• /premium — премиум подписка\n"
                "• /status — статус бота\n"
                "• /help — эта справка\n\n"
                f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
                "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
                "<b>Способы оплаты премиума:</b>\n"
                "1. ⭐ Telegram Stars (встроенная оплата)\n"
                "2. 💳 Ручная оплата (карта)\n\n"
                "<i>По вопросам обращайтесь к администратору</i>",
                parse_mode='HTML'
            )
        
        # Админ кнопки (упрощенные)
        elif query.data == "admin_panel":
            user = query.from_user
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
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
                        
                        cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                        successful_payments = cursor.fetchone()[0]
                    else:
                        total_users = premium_users = total_reminders = successful_payments = 0
            except:
                total_users = premium_users = total_reminders = successful_payments = 0
            
            keyboard = [
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
                [
                    InlineKeyboardButton("⭐ Активировать", callback_data="admin_activate"),
                    InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
                ],
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
                f"<b>Статистика:</b>\n"
                f"• 👥 Пользователей: {total_users}\n"
                f"• ⭐ Премиум: {premium_users}\n"
                f"• 📝 Напоминаний: {total_reminders}\n"
                f"• 💰 Успешных платежей: {successful_payments}\n\n"
                f"Выберите действие:",
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
                    "• 🔄 Повторяющиеся платежи\n"
                    "• 🔔 Уведомления за 3 и 7 дней\n\n"
                    "Наслаждайтесь! Если понравится - сможете оформить полную подписку. ⭐",
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Ошибка активации тестового периода.")
                
        # ========== ОБРАБОТЧИК КНОПКИ "Я ОПЛАТИЛ" ==========
        elif query.data.startswith("manual_paid_"):
            try:
                period = query.data.split("_")[2] if len(query.data.split("_")) > 2 else "1"
                
                if period in PREMIUM_PRICES:
                    price_info = PREMIUM_PRICES[period]
                    user = query.from_user
                    
                    logger.info(f"💰 Кнопка 'Я оплатил' нажата: user_id={user.id}, period={period}")
                    
                    await query.edit_message_text(
                        f"✅ <b>Заявка принята!</b>\n\n"
                        f"<b>Детали оплаты:</b>\n"
                        f"• Подписка: {price_info['text']}\n"
                        f"• Сумма: {price_info['stars']}₽\n"
                        f"• Срок: {price_info['days']} дней\n\n"
                        f"<b>Что дальше:</b>\n"
                        f"1. Администратор получил уведомление\n"
                        f"2. Он активирует ваш премиум вручную\n"
                        f"3. Вы получите сообщение о активации\n\n"
                        f"Обычно это занимает до 24 часов.\n\n"
                        f"Спасибо за покупку! 💰",
                        parse_mode='HTML'
                    )
                    
                    if not ADMIN_ID or ADMIN_ID == 0:
                        logger.error("❌ ADMIN_ID не настроен!")
                        return
                    
                    try:
                        username_display = f"@{user.username}" if user.username else f"ID_{user.id}"
                        
                        admin_message = (
                            f"💰 <b>НОВАЯ ЗАЯВКА НА РУЧНУЮ ОПЛАТУ!</b>\n\n"
                            f"<b>👤 Пользователь:</b>\n"
                            f"├ Имя: {user.first_name or 'Не указано'}\n"
                            f"├ Фамилия: {user.last_name or 'Не указана'}\n"
                            f"├ Username: {username_display}\n"
                            f"└ ID: <code>{user.id}</code>\n\n"
                            f"<b>📦 Подписка:</b>\n"
                            f"├ Период: {price_info['text']}\n"
                            f"├ Сумма: {price_info['stars']}₽\n"
                            f"└ Дней: {price_info['days']}\n\n"
                            f"<b>⚡ Быстрая активация:</b>\n"
                            f"<code>/admin_activate {username_display.replace('@', '')} {price_info['days']}</code>\n\n"
                            f"<b>⏰ Время заявки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                        )
                        
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=admin_message,
                            parse_mode='HTML'
                        )
                        
                        logger.info(f"✅ Уведомление отправлено администратору {ADMIN_ID}")
                        
                    except Exception as admin_error:
                        logger.error(f"❌ Ошибка отправки уведомления админу: {admin_error}")
                        
                else:
                    await query.edit_message_text(
                        "❌ <b>Ошибка обработки оплаты</b>\n\n"
                        "Неверный период подписки. Пожалуйста, попробуйте снова.",
                        parse_mode='HTML'
                    )
                    
            except Exception as e:
                logger.error(f"❌ Общая ошибка в обработчике manual_paid_: {e}")
                
                try:
                    await query.edit_message_text(
                        "❌ <b>Произошла критическая ошибка</b>\n\n"
                        "Пожалуйста, повторите попытку или свяжитесь с администратором напрямую.",
                        parse_mode='HTML'
                    )
                except:
                    pass
                
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")

# ========== АДМИН КОМАНДЫ (упрощенные) ==========

async def admin_activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда активации премиума админом"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "⭐ <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
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
                         f"• 🔄 Повторяющиеся платежи\n"
                         f"• 🔔 Уведомления за 3 и 7 дней\n\n"
                         f"Спасибо за использование бота! ⭐",
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
                "⚠️ Произошла ошибка. Попробуйте команду /start"
            )
    except:
        pass

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота"""
    print("=" * 60)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
    print("💰 Платежи: Telegram Stars + Ручная оплата")
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
    
    print("⭐ Telegram Stars: ✅ готов к использованию")
    
    app = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для создания напоминаний
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('new', new_command)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    app.add_handler(conv_handler)
    
    # Обработчики Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(stars_pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_successful_payment_handler))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    
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
    print("⭐ Telegram Stars готов к работе!")
    print("=" * 60)
    
    # Запускаем веб-сервер
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    time_module.sleep(3)
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
