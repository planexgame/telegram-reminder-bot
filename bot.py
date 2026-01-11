# bot.py - полный обновленный код с Telegram Stars
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
from telegram_payments import telegram_stars
from manual_payments import manual_payments

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
    print(f"✅ Тип ADMIN_ID: {type(ADMIN_ID)}")
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
# Состояния для рассылки с фото
AWAITING_PHOTO, AWAITING_TEXT = range(2)

# ========== ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE ==========

def run_web_server():
    """Запуск веб-сервера для keep-alive"""
    try:
        from flask import Flask, jsonify
        import os
        
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
            """Эндпоинт для мониторинга"""
            return "pong", 200
        
        @web_app.route('/health')
        def health():
            """Полная проверка здоровья"""
            try:
                # Проверяем подключение к БД
                conn = db.get_connection()
                db_status = "connected" if conn else "disconnected"
                
                return jsonify({
                    "status": "healthy",
                    "database": db_status,
                    "bot": "running",
                    "payments": telegram_stars.get_payment_stats(),
                    "timestamp": datetime.now().isoformat(),
                    "version": "2.0.0"
                }), 200
            except Exception as e:
                return jsonify({
                    "status": "unhealthy",
                    "error": str(e)[:100],
                    "timestamp": datetime.now().isoformat()
                }), 500
        
        @web_app.route('/status')
        def status():
            """Статус бота с подробностями"""
            try:
                # Базовая статистика
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM users")
                    total_users = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM reminders WHERE is_active = TRUE")
                    total_reminders = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                    total_payments = cursor.fetchone()[0]
                    cursor.close()
            except:
                total_users = total_reminders = total_payments = 0
            
            return jsonify({
                "bot": "НеЗабудьОплатить",
                "status": "running",
                "version": "2.0.0",
                "users": total_users,
                "active_reminders": total_reminders,
                "successful_payments": total_payments,
                "payment_method": "telegram_stars",
                "uptime": "always",
                "server_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "admin_id": ADMIN_ID
            })
        
        # Запускаем веб-сервер
        port = int(os.getenv('PORT', 8080))
        print(f"🌐 Веб-сервер запускается на порту {port}")
        web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
    except ImportError:
        # Если Flask не установлен, используем простой HTTP сервер
        print("⚠️ Flask не установлен, использую простой HTTP сервер")
        run_simple_http_server()

def run_simple_http_server():
    """Простой HTTP сервер без зависимостей"""
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
                    "payments": "telegram_stars",
                    "timestamp": datetime.now().isoformat()
                })
                self.wfile.write(response.encode())
            else:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Bot is running')
        
        def log_message(self, format, *args):
            pass  # Отключаем логирование
    
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"🌐 HTTP сервер запущен на порту {port}")
    server.serve_forever()

def start_keep_alive():
    """Исправленный keep-alive для Render"""
    import requests
    
    print("=" * 50)
    print("🔄 ЗАПУСКАЮ ИСПРАВЛЕННЫЙ KEEP-ALIVE")
    print(f"🔗 URL: https://telegram-reminder-bot-vc4c.onrender.com")
    print("⏰ Интервал: 8 минут")
    print("=" * 50)
    
    ping_count = 0
    errors_count = 0
    
    while True:
        try:
            ping_count += 1
            url = "https://telegram-reminder-bot-vc4c.onrender.com/ping"
            
            # Делаем запрос с таймаутом
            response = requests.get(url, timeout=15)
            
            current_time = time_module.strftime('%H:%M:%S')
            
            if response.status_code == 200:
                if response.text.strip() == 'pong':
                    print(f"✅ [{current_time}] Keep-alive #{ping_count}: Render получил запрос!")
                    errors_count = 0  # Сбрасываем счетчик ошибок
                else:
                    print(f"⚠️ [{current_time}] Keep-alive #{ping_count}: Неверный ответ: '{response.text}'")
                    errors_count += 1
            else:
                print(f"❌ [{current_time}] Keep-alive #{ping_count}: Код {response.status_code}")
                errors_count += 1
                
            # Если много ошибок подряд - увеличиваем интервал
            if errors_count > 3:
                print(f"⚠️ Много ошибок ({errors_count}), увеличиваю интервал...")
                time_module.sleep(600)  # 10 минут
            else:
                time_module.sleep(480)  # 8 минут
                
        except requests.exceptions.Timeout:
            current_time = time_module.strftime('%H:%M:%S')
            print(f"⏱️ [{current_time}] Keep-alive #{ping_count}: Таймаут (15 сек)")
            errors_count += 1
            time_module.sleep(300)  # 5 минут при таймауте
            
        except Exception as e:
            current_time = time_module.strftime('%H:%M:%S')
            error_msg = str(e)
            print(f"🚨 [{current_time}] Keep-alive #{ping_count}: {error_msg[:80]}")
            errors_count += 1
            time_module.sleep(300)  # 5 минут при ошибке

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    try:
        # Регистрируем пользователя
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Получаем данные пользователя
        premium_status = db.get_user_premium_status(user_id) if user_id else {'has_active_premium': False}
        reminders_count = db.get_user_reminders_count(user_id) if user_id else 0
        
        has_premium = premium_status.get('has_active_premium', False)
        
        # Создаем клавиатуру
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
        
        # Формируем сообщение
        premium_text = "⭐ АКТИВЕН" if has_premium else "🆓 БЕСПЛАТНЫЙ"
        limit_text = '∞' if has_premium else FREE_LIMIT
        
        message = (
            f"🔔 <b>НеЗабудьОплатить v2.0</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"<b>Ваша статистика:</b>\n"
            f"📊 Напоминаний: {reminders_count}/{limit_text}\n"
            f"⭐ Статус: {premium_text}\n\n"
            f"<b>Ваши возможности:</b>\n"
            f"• {'♾️ Неограниченные' if has_premium else f'До {FREE_LIMIT}'} напоминаний\n"
            f"• 🔔 Уведомления за {'3 и 7 дней' if has_premium else '1 день'}\n"
            f"• {'🔄 Повторяющиеся платежи' if has_premium else '📅 Разовые напоминания'}\n\n"
            f"<b>Способы оплаты:</b>\n"
            f"• ⭐ Telegram Stars (автоматически)\n"
            f"• 💳 Ручная оплата (карта/СБП)\n\n"
            f"Выберите действие:"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text(
            f"🔔 <b>НеЗабудьОплатить v2.0</b>\n\n"
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
        "<b>🔔 НеЗабудьОплатить v2.0 — помощь</b>\n\n"
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
        "1. ⭐ Telegram Stars (автоматически)\n"
        "2. 💳 Ручная оплата (карта/СБП)\n\n"
        "<i>По вопросам оплаты обращайтесь к администратору</i>"
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
        
        # Проверяем лимиты
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
        
        # Проверяем что дата в будущем
        if payment_date < datetime.now().date():
            await update.message.reply_text("❌ Дата должна быть в будущем.")
            return DATE
        
        # Сохраняем напоминание
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
        
        # Получаем напоминания
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
        
        # Формируем сообщение
        message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
        total_amount = 0
        
        for i, rem in enumerate(reminders[:10], 1):
            # Форматируем дату
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
        
        # Получаем статус премиума
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний ⭐\n"
        
        # Клавиатура с кнопками удаления
        keyboard = []
        
        # Кнопки удаления (первые 3 напоминания)
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
        
        # Добавляем кнопки удаления по 2 в ряд
        for i in range(0, len(delete_buttons), 2):
            row = delete_buttons[i:i+2]
            keyboard.append(row)
        
        # Основные кнопки
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
        ])
        
        # Если нет премиума и достигнут/почти достигнут лимит
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
        # Регистрируем/получаем пользователя
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await query.edit_message_text("❌ Ошибка базы данных.")
            return
        
        # Получаем напоминания
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
        
        # Формируем сообщение
        message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
        total_amount = 0
        
        for i, rem in enumerate(reminders[:10], 1):
            # Форматируем дату
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
        
        # Получаем статус премиума
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний ⭐\n"
        
        # Клавиатура с кнопками удаления
        keyboard = []
        
        # Кнопки удаления (первые 3 напоминания)
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
        
        # Добавляем кнопки удаления по 2 в ряд
        for i in range(0, len(delete_buttons), 2):
            row = delete_buttons[i:i+2]
            keyboard.append(row)
        
        # Основные кнопки
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
        ])
        
        # Если нет премиума и достигнут/почти достигнут лимит
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
        stars_status = telegram_stars.get_payment_stats()
        
        status_text = (
            f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить v2.0»</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>⭐ Telegram Stars:</b> {'✅ настроен' if stars_status['configured'] else '⚠️ не настроен'}\n"
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
            f"• ⭐ Telegram Stars (автоматическая оплата)\n"
            f"• 💳 Ручная оплата (карта, СБП, крипто)\n\n"
            f"<i>Все системы работают нормально! 🎉</i>"
        )
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

# ========== ПРЕМИУМ КОМАНДЫ ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium - с возможностью покупки через Stars"""
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
        
        # Получаем статус
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            # Если уже есть премиум - показываем информацию
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
            # Если нет премиума - предлагаем купить
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
            
            # Кнопки покупки
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
        
        # Проверяем, не активна ли уже подписка
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            await query.edit_message_text(
                "✅ У вас уже активна премиум подписка!\n\n"
                "Используйте команду /premium чтобы увидеть детали."
            )
            return
        
        # Предлагаем варианты подписок через Stars
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
            "Telegram Stars — это внутренняя валюта Telegram для оплаты услуг.\n\n"
            "<b>Преимущества:</b>\n"
            "• ⚡ Мгновенная активация\n"
            "• 🔒 Безопасная оплата\n"
            "• 📱 Удобно через приложение\n\n"
            "<b>Выберите подписку:</b>\n\n"
            "• <b>1 месяц</b> — 299 Stars\n"
            "   👉 Для тестирования\n\n"
            "• <b>3 месяца</b> — 799 Stars (267 Stars/мес)\n"
            "   👉 Экономия 11%\n\n"
            "• <b>12 месяцев</b> — 1990 Stars (166 Stars/мес)\n"
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
        
        # Проверяем, не активна ли уже подписка
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            await query.edit_message_text(
                "✅ У вас уже активна премиум подписка!\n\n"
                "Используйте команду /premium чтобы увидеть детали."
            )
            return
        
        # Предлагаем варианты ручной оплаты
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
            "• 💳 Перевод на карту\n"
            "• 📱 СБП (Система быстрых платежей)\n"
            "• ₿ Криптовалюта (USDT, TRC20)\n\n"
            "<b>Выберите подписку:</b>\n\n"
            "• <b>1 месяц</b> — 299₽\n"
            "   👉 Для тестирования\n\n"
            "• <b>3 месяца</b> — 799₽ (267₽/мес)\n"
            "   👉 Экономия 11%\n\n"
            "• <b>12 месяцев</b> — 1990₽ (166₽/мес)\n"
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
        # Проверяем payload
        payload = query.invoice_payload
        if payload.startswith("premium_"):
            period = payload.split("_")[1]
            
            if period in PREMIUM_PRICES:
                # Проверяем сумму
                expected_amount = PREMIUM_PRICES[period]['stars'] * 100  # В минимальных единицах
                
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
        
        # Извлекаем данные из payload
        payload = payment.invoice_payload
        if not payload.startswith("premium_"):
            logger.error(f"Неизвестный payload: {payload}")
            return
        
        period = payload.split("_")[1]
        
        if period not in PREMIUM_PRICES:
            logger.error(f"Неизвестный период: {period}")
            return
        
        user = update.effective_user
        
        # Регистрируем пользователя
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
        
        # Создаем запись о платеже в базе
        payment_id = db.create_payment(
            user_id=user_id,
            amount=payment.total_amount / 100,
            period_days=PREMIUM_PRICES[period]['days']
        )
        
        if payment_id:
            # Обновляем статус платежа
            db.update_payment_status(
                payment_id=payment_id,
                status='succeeded',
                telegram_payment_id=payment.telegram_payment_charge_id
            )
            
            # Активируем премиум
            if db.activate_premium(user_id, PREMIUM_PRICES[period]['days']):
                # Отправляем подтверждение пользователю
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
                
                # Уведомляем администратора
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

# ========== АДМИН КОМАНДЫ ==========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin - панель администратора"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text(
            f"❌ <b>ДОСТУП ЗАПРЕЩЕН</b>\n\n"
            f"Ваш ID: <code>{user.id}</code>\n"
            f"Требуется ID: <code>{ADMIN_ID}</code>\n\n"
            f"<i>Эта команда только для администратора</i>",
            parse_mode='HTML'
        )
        return
    
    # Получаем статистику
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
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        total_users = premium_users = total_reminders = successful_payments = 0
    
    # Клавиатура
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="broadcast_text")],
        [
            InlineKeyboardButton("⭐ Активировать", callback_data="admin_activate"),
            InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
        ],
        [InlineKeyboardButton("💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    stars_stats = telegram_stars.get_payment_stats()
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"⚙️ <b>АДМИН ПАНЕЛЬ v2.0</b>\n\n"
            f"<b>Статистика:</b>\n"
            f"• 👥 Пользователей: {total_users}\n"
            f"• ⭐ Премиум: {premium_users}\n"
            f"• 📝 Напоминаний: {total_reminders}\n"
            f"• 💰 Успешных платежей: {successful_payments}\n"
            f"• ⚡ Telegram Stars: {'✅' if stars_stats['configured'] else '❌'}\n\n"
            f"<b>Доступные функции:</b>\n"
            f"• 📨 Рассылка сообщений\n"
            f"• ⭐ Управление премиумом\n"
            f"• 📊 Просмотр статистики\n"
            f"• 💰 Управление платежами\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⚙️ <b>АДМИН ПАНЕЛЬ v2.0</b>\n\n"
            f"<b>Статистика:</b>\n"
            f"• 👥 Пользователей: {total_users}\n"
            f"• ⭐ Премиум: {premium_users}\n"
            f"• 📝 Напоминаний: {total_reminders}\n"
            f"• 💰 Успешных платежей: {successful_payments}\n"
            f"• ⚡ Telegram Stars: {'✅' if stars_stats['configured'] else '❌'}\n\n"
            f"<b>Доступные функции:</b>\n"
            f"• 📨 Рассылка сообщений\n"
            f"• ⭐ Управление премиумом\n"
            f"• 📊 Просмотр статистики\n"
            f"• 💰 Управление платежами\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def admin_payments_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик просмотра платежей"""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Доступ запрещен", show_alert=True)
        return
    
    await query.answer()
    
    try:
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                # Получаем последние платежи
                cursor.execute('''
                    SELECT p.id, u.username, u.telegram_id, p.amount, p.period_days, p.status, p.created_at
                    FROM payments p
                    JOIN users u ON p.user_id = u.id
                    ORDER BY p.created_at DESC
                    LIMIT 10
                ''')
                payments = cursor.fetchall()
                
                message = "💰 <b>ПОСЛЕДНИЕ ПЛАТЕЖИ</b>\n\n"
                
                if payments:
                    for i, (pid, username, tg_id, amount, days, status, created_at) in enumerate(payments, 1):
                        status_icon = "✅" if status == 'succeeded' else "⏳" if status == 'pending' else "❌"
                        date_str = created_at.strftime('%d.%m %H:%M') if hasattr(created_at, 'strftime') else str(created_at)[:16]
                        
                        message += f"{i}. {status_icon} @{username or tg_id}\n"
                        message += f"   💰 {amount} Stars | {days} дней\n"
                        message += f"   📅 {date_str} | ID: {pid}\n\n"
                else:
                    message += "📭 Платежей пока нет\n\n"
                
                # Статистика по методам оплаты
                cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                total_success = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
                total_pending = cursor.fetchone()[0]
                
                message += f"<b>Статистика:</b>\n"
                message += f"• ✅ Успешных: {total_success}\n"
                message += f"• ⏳ Ожидают: {total_pending}\n"
                message += f"• ⚡ Telegram Stars: {'✅ Настроен' if telegram_stars.is_configured else '❌ Не настроен'}\n\n"
                
                cursor.close()
            else:
                message = "❌ Ошибка подключения к БД"
        
        keyboard = [
            [InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
            [InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка admin_payments_handler: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Основные кнопки
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
                
                # Создаем инвойс для Telegram Stars
                try:
                    await query.edit_message_text(
                        f"⭐ <b>СОЗДАНИЕ СЧЕТА...</b>\n\n"
                        f"Подписка: {price_info['text']}\n"
                        f"Стоимость: {price_info['stars']} Stars\n\n"
                        f"<i>Сейчас откроется окно оплаты...</i>",
                        parse_mode='HTML'
                    )
                    
                    # Отправляем инвойс
                    await context.bot.send_invoice(
                        chat_id=user.id,
                        title=f"Премиум подписка на {price_info['text']}",
                        description="Доступ к неограниченным напоминаниям и расширенным функциям",
                        payload=f"premium_{period}",
                        provider_token=telegram_stars.provider_token if telegram_stars.is_configured else None,
                        currency="XTR",  # Код валюты Telegram Stars
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
                    
                    if "provider_token" in str(e).lower():
                        await query.edit_message_text(
                            f"❌ <b>TELEGRAM STARS НЕ НАСТРОЕН</b>\n\n"
                            f"Администратор еще не настроил платежи через Stars.\n\n"
                            f"<b>Используйте ручную оплату:</b>",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("💳 Ручная оплата", callback_data=f"manual_buy_{period}")],
                                [InlineKeyboardButton("↩️ Назад", callback_data="stars_payment")]
                            ]),
                            parse_mode='HTML'
                        )
                    else:
                        await query.edit_message_text(
                            f"❌ Ошибка создания счета: {str(e)[:100]}"
                        )
            else:
                await query.edit_message_text("❌ Неверный период подписки.")
                
        elif query.data.startswith("manual_buy_"):
            # Ручная оплата (старая логика сохранена)
            period = query.data.split("_")[2]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                user = query.from_user
                
                # Формируем инструкции для ручной оплаты
                instructions = manual_payments.format_payment_instructions(
                    amount=price_info['stars'],  # Используем stars как сумму в рублях
                    period=price_info['text'],
                    username=user.username or str(user.id)
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
                "<b>🔔 НеЗабудьОплатить v2.0 — помощь</b>\n\n"
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
                "1. ⭐ Telegram Stars (автоматическая оплата)\n"
                "2. 💳 Ручная оплата (карта/СБП/крипто)\n\n"
                "<i>По вопросам обращайтесь к администратору</i>",
                parse_mode='HTML'
            )
        
        # Админ кнопки
        elif query.data == "admin_panel":
            await admin_command(update, context)
            
        elif query.data == "admin_stats":
            await admin_stats_handler(query, context)
            
        elif query.data == "admin_users":
            await admin_users_handler(query, context)
            
        elif query.data == "admin_payments":
            await admin_payments_handler(update, context)
            
        elif query.data == "admin_activate":
            await query.edit_message_text(
                "⭐ <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
                "Используйте команду:\n"
                "<code>/admin_activate @username 30</code>\n\n"
                "Где 30 - количество дней премиума.\n\n"
                "<b>Примеры:</b>\n"
                "<code>/admin_activate @ivanov 30</code>\n"
                "<code>/admin_activate @petrov 365</code>\n\n"
                "<i>Или используйте /admin_users для просмотра списка пользователей</i>",
                parse_mode='HTML'
            )
            
        elif query.data == "admin_deactivate_menu":
            await query.edit_message_text(
                "🚫 <b>ДЕАКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
                "Используйте команду:\n"
                "<code>/admin_deactivate @username</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/admin_deactivate @ivanov</code>\n\n"
                "Сначала найдите username пользователя через кнопку '👥 Пользователи'",
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
                
        # ========== ОБРАБОТЧИК КНОПКИ "Я ОПЛАТИЛ" (ручная оплата) ==========
        elif query.data.startswith("manual_paid_"):
            """Обработчик кнопки 'Я оплатил' с уведомлением админу"""
            try:
                period = query.data.split("_")[2] if len(query.data.split("_")) > 2 else "1"
                
                if period in PREMIUM_PRICES:
                    price_info = PREMIUM_PRICES[period]
                    user = query.from_user
                    
                    logger.info(f"💰 Кнопка 'Я оплатил' нажата: user_id={user.id}, username=@{user.username}, period={period}")
                    
                    # Сообщение пользователю
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
                    
                    # Проверяем ADMIN_ID
                    if not ADMIN_ID or ADMIN_ID == 0:
                        logger.error("❌ ADMIN_ID не настроен!")
                        await query.message.reply_text(
                            "⚠️ <b>Техническая ошибка</b>\n\n"
                            "ADMIN_ID не настроен. Сообщите об этом администратору."
                        )
                        return
                    
                    # Формируем уведомление для администратора
                    try:
                        username_display = f"@{user.username}" if user.username else f"ID_{user.id}"
                        first_name_display = user.first_name or "Не указано"
                        last_name_display = user.last_name or "Не указана"
                        
                        admin_message = (
                            f"💰 <b>НОВАЯ ЗАЯВКА НА РУЧНУЮ ОПЛАТУ!</b>\n\n"
                            f"<b>👤 Пользователь:</b>\n"
                            f"├ Имя: {first_name_display}\n"
                            f"├ Фамилия: {last_name_display}\n"
                            f"├ Username: {username_display}\n"
                            f"└ ID: <code>{user.id}</code>\n\n"
                            f"<b>📦 Подписка:</b>\n"
                            f"├ Период: {price_info['text']}\n"
                            f"├ Сумма: {price_info['stars']}₽\n"
                            f"└ Дней: {price_info['days']}\n\n"
                            f"<b>⚡ Быстрая активация:</b>\n"
                            f"<code>/admin_activate {username_display.replace('@', '')} {price_info['days']}</code>\n"
                            f"или\n"
                            f"<code>/admin_activate {user.id} {price_info['days']}</code>\n\n"
                            f"<b>⏰ Время заявки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                            f"<i>Для просмотра всех заявок: /admin_requests</i>"
                        )
                        
                        # Отправляем уведомление администратору
                        sent_message = await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=admin_message,
                            parse_mode='HTML'
                        )
                        
                        logger.info(f"✅ Уведомление отправлено администратору {ADMIN_ID}. Message ID: {sent_message.message_id}")
                        
                    except Exception as admin_error:
                        error_msg = str(admin_error)
                        logger.error(f"❌ Ошибка отправки уведомления админу: {error_msg}")
                        
                        await query.message.reply_text(
                            f"⚠️ <b>Внимание!</b>\n\n"
                            f"Не удалось автоматически уведомить администратора.\n\n"
                            f"<b>Ваши данные для ручной активации:</b>\n"
                            f"• Ваш ID: <code>{user.id}</code>\n"
                            f"• Подписка: {price_info['text']}\n"
                            f"• Сумма: {price_info['stars']}₽\n\n"
                            f"<b>Сообщите администратору:</b>\n"
                            f"Используйте команду:\n"
                            f"<code>/admin_activate {user.id} {price_info['days']}</code>",
                            parse_mode='HTML'
                        )
                        
                else:
                    await query.edit_message_text(
                        "❌ <b>Ошибка обработки оплаты</b>\n\n"
                        "Неверный период подписки. Пожалуйста, попробуйте снова.",
                        parse_mode='HTML'
                    )
                    
            except Exception as e:
                logger.error(f"❌ Общая ошибка в обработчике manual_paid_: {e}", exc_info=True)
                
                try:
                    await query.edit_message_text(
                        "❌ <b>Произошла критическая ошибка</b>\n\n"
                        "Пожалуйста, повторите попытку или свяжитесь с администратором напрямую.",
                        parse_mode='HTML'
                    )
                except:
                    pass
                
        # Админ рассылка (оставлена без изменений)
        elif query.data == "broadcast_text":
            await query.edit_message_text(
                "📝 <b>ТЕКСТОВАЯ РАССЫЛКА</b>\n\n"
                "Используйте команду:\n"
                "<code>/broadcast Ваш текст</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/broadcast Новое обновление! Добавлены крутые функции</code>\n\n"
                "<b>Или выберите аудиторию:</b>",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("👥 Всем", callback_data="broadcast_all_menu"),
                        InlineKeyboardButton("⭐ Премиум", callback_data="broadcast_premium_menu")
                    ],
                    [
                        InlineKeyboardButton("🆓 Бесплатные", callback_data="broadcast_free_menu"),
                        InlineKeyboardButton("↩️ Назад", callback_data="admin_panel")
                    ]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data.startswith("confirm_broadcast_all_"):
            await handle_confirm_broadcast(query, context, 'all', 'text')
            
        elif query.data.startswith("confirm_broadcast_premium_"):
            await handle_confirm_broadcast(query, context, 'premium', 'text')
            
        elif query.data.startswith("confirm_broadcast_free_"):
            await handle_confirm_broadcast(query, context, 'free', 'text')
            
        elif query.data.startswith("confirm_photo_all_"):
            await handle_confirm_broadcast(query, context, 'all', 'photo')
            
        elif query.data.startswith("confirm_photo_premium_"):
            await handle_confirm_broadcast(query, context, 'premium', 'photo')
            
        elif query.data.startswith("confirm_photo_free_"):
            await handle_confirm_broadcast(query, context, 'free', 'photo')
            
        elif query.data == "cancel_broadcast":
            await query.edit_message_text("❌ Рассылка отменена.")
            context.user_data.pop('broadcast_message', None)
            context.user_data.pop('photo_file_id', None)
            context.user_data.pop('photo_caption', None)
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")

# ========== АДМИН ОБРАБОТЧИКИ ==========

async def admin_stats_handler(query, context):
    """Обработчик статистики админа"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    try:
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                total = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
                premium = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM reminders")
                reminders = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                payments = cursor.fetchone()[0]
            else:
                total = premium = reminders = payments = 0
        
        stars_stats = telegram_stars.get_payment_stats()
        
        await query.edit_message_text(
            f"📊 <b>СТАТИСТИКА БОТА v2.0</b>\n\n"
            f"• 👥 Всего пользователей: {total}\n"
            f"• ⭐ Премиум пользователей: {premium}\n"
            f"• 📝 Всего напоминаний: {reminders}\n"
            f"• 💰 Успешных платежей: {payments}\n\n"
            f"<b>Telegram Stars:</b>\n"
            f"• ⚡ Настроен: {'✅ Да' if stars_stats['configured'] else '❌ Нет'}\n"
            f"• 🔐 Токен провайдера: {'✅ Есть' if stars_stats['has_provider_token'] else '❌ Нет'}\n"
            f"• 🛡️ Секретный токен: {'✅ Есть' if stars_stats['has_secret_token'] else '❌ Нет'}\n\n"
            f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>",
            parse_mode='HTML'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

async def admin_users_handler(query, context):
    """Обработчик списка пользователей"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    try:
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, first_name, is_premium, created_at 
                    FROM users 
                    ORDER BY created_at DESC 
                    LIMIT 15
                """)
                users = cursor.fetchall()
            else:
                users = []
        
        if not users:
            await query.edit_message_text("📭 Пользователей пока нет.")
            return
        
        message = "👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛЫ:</b>\n\n"
        
        for i, (username, first_name, is_premium, created_at) in enumerate(users, 1):
            username_display = f"@{username}" if username else "нет username"
            premium = "⭐" if is_premium else "🆓"
            date_str = created_at.strftime('%d.%m') if hasattr(created_at, 'strftime') else str(created_at)[:10]
            
            message += f"{i}. {premium} {first_name or 'Без имени'} ({username_display}) - {date_str}\n"
            
            if i % 5 == 0:
                message += "\n"
        
        message += f"\n<i>Всего пользователей: {len(users)}</i>\n\n"
        message += "<b>Для управления премиумом:</b>\n"
        message += "• Активация: <code>/admin_activate @username 30</code>\n"
        message += "• Деактивация: <code>/admin_deactivate @username</code>"
        
        keyboard = [
            [
                InlineKeyboardButton("⭐ Активировать", callback_data="admin_activate"),
                InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
            ],
            [InlineKeyboardButton("🔄 Обновить", callback_data="admin_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

async def handle_confirm_broadcast(query, context, target_type, broadcast_type):
    """Обработка подтверждения рассылки"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    await query.edit_message_text(
        f"⏳ <b>НАЧИНАЮ РАССЫЛКУ...</b>\n\n"
        f"Тип: {target_type}\n"
        f"Формат: {'Фото' if broadcast_type == 'photo' else 'Текст'}\n\n"
        f"<i>Это может занять несколько минут. Вы получите отчет по завершении.</i>",
        parse_mode='HTML'
    )
    
    # Импортируем здесь, чтобы избежать циклического импорта
    from broadcast import send_text_broadcast, send_photo_broadcast
    
    if broadcast_type == 'photo':
        photo_file_id = context.user_data.get('photo_file_id')
        caption = context.user_data.get('photo_caption', '')
        message_text = context.user_data.get('broadcast_message', '')
        
        if not photo_file_id:
            await query.edit_message_text("❌ Ошибка: фото не найдено.")
            return
        
        asyncio.create_task(
            send_photo_broadcast(context, photo_file_id, caption, message_text, target_type, ADMIN_ID)
        )
    else:
        message_text = context.user_data.get('broadcast_message')
        if not message_text:
            await query.edit_message_text("❌ Ошибка: текст сообщения не найден.")
            return
        
        asyncio.create_task(
            send_text_broadcast(context, message_text, target_type, ADMIN_ID)
        )
    
    # Очищаем данные
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('photo_file_id', None)
    context.user_data.pop('photo_caption', None)

# ========== ТЕСТОВЫЕ КОМАНДЫ ==========

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда /test"""
    stars_stats = telegram_stars.get_payment_stats()
    
    await update.message.reply_text(
        f"✅ <b>Бот работает! v2.0</b>\n\n"
        f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"ADMIN_ID: {ADMIN_ID}\n"
        f"Ваш ID: {update.effective_user.id}\n"
        f"Вы админ: {'✅ Да' if update.effective_user.id == ADMIN_ID else '❌ Нет'}\n\n"
        f"<b>Telegram Stars:</b>\n"
        f"• Настроен: {'✅ Да' if stars_stats['configured'] else '❌ Нет'}\n"
        f"• Провайдер токен: {'✅ Есть' if stars_stats['has_provider_token'] else '❌ Нет'}\n"
        f"• Секретный токен: {'✅ Есть' if stars_stats['has_secret_token'] else '❌ Нет'}",
        parse_mode='HTML'
    )

async def test_stars_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки Telegram Stars"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    stars_stats = telegram_stars.get_payment_stats()
    
    test_message = (
        f"🧪 <b>ТЕСТ TELEGRAM STARS v2.0</b>\n\n"
        f"<b>Статус настройки:</b>\n"
        f"• Настроен: {'✅ Да' if stars_stats['configured'] else '❌ Нет'}\n"
        f"• Провайдер токен: {'✅ Есть' if stars_stats['has_provider_token'] else '❌ Нет'}\n"
        f"• Секретный токен: {'✅ Есть' if stars_stats['has_secret_token'] else '❌ Нет'}\n\n"
    )
    
    if stars_stats['configured']:
        test_message += (
            f"✅ <b>Telegram Stars настроен правильно!</b>\n\n"
            f"<b>Для теста:</b>\n"
            f"1. Используйте команду /premium\n"
            f"2. Выберите '⭐ Telegram Stars'\n"
            f"3. Выберите подписку\n"
            f"4. Оплатите тестовыми Stars\n\n"
            f"<b>Переменные окружения:</b>\n"
            f"TELEGRAM_PROVIDER_TOKEN: {'✅ Установлен' if stars_stats['has_provider_token'] else '❌ Отсутствует'}\n"
            f"TELEGRAM_PAYMENT_TOKEN: {'✅ Установлен' if stars_stats['has_secret_token'] else '❌ Отсутствует'}"
        )
    else:
        test_message += (
            f"❌ <b>Telegram Stars не настроен!</b>\n\n"
            f"<b>Необходимо установить в Render:</b>\n"
            f"1. TELEGRAM_PROVIDER_TOKEN (от @BotFather)\n"
            f"2. TELEGRAM_PAYMENT_TOKEN (секретный токен)\n\n"
            f"<b>Инструкция:</b>\n"
            f"1. Напишите @BotFather\n"
            f"2. Выберите вашего бота\n"
            f"3. Bot Settings → Payments\n"
            f"4. Настройте платежи и получите токены"
        )
    
    await update.message.reply_text(test_message, parse_mode='HTML')

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
    """Запуск бота с поддержкой Telegram Stars"""
    print("=" * 60)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить v2.0»")
    print("💰 Платежи: Telegram Stars + Ручная оплата")
    print("=" * 60)
    
    print(f"✅ Токен: {'найден' if TOKEN else 'НЕ НАЙДЕН'}")
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
    print(f"🌐 Веб-порт: {os.getenv('PORT', 8080)}")
    
    # Проверка БД
    try:
        if db.init_db():
            print("✅ База данных: подключена")
        else:
            print("⚠️ База данных: проблемы с подключением")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    
    # Проверка Telegram Stars
    stars_stats = telegram_stars.get_payment_stats()
    print(f"⭐ Telegram Stars: {'✅ настроен' if stars_stats['configured'] else '❌ НЕ настроен'}")
    if stars_stats['configured']:
        print(f"   • Провайдер токен: {'✅ есть' if stars_stats['has_provider_token'] else '❌ нет'}")
        print(f"   • Секретный токен: {'✅ есть' if stars_stats['has_secret_token'] else '❌ нет'}")
    
    # Создаем приложение бота
    app = Application.builder().token(TOKEN).build()
    
    # ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====
    
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
    
    # ConversationHandler для рассылки с фото (оставлен без изменений)
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast_photo', admin_broadcast_photo_command)],
        states={
            AWAITING_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_broadcast_photo)],
            AWAITING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_text)],
        },
        fallbacks=[CommandHandler('cancel', broadcast_cancel)]
    )
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    app.add_handler(CommandHandler("admin_deactivate", admin_deactivate_command))
    app.add_handler(CommandHandler("broadcast", admin_broadcast_command))
    app.add_handler(CommandHandler("broadcast_premium", admin_broadcast_premium_command))
    app.add_handler(CommandHandler("broadcast_test", admin_broadcast_test_command))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CommandHandler("test_stars", test_stars_command))
    app.add_handler(CommandHandler("admin_requests", admin_requests_command))
    app.add_handler(conv_handler)
    app.add_handler(broadcast_conv_handler)
    
    # Обработчики Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(stars_pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_successful_payment_handler))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Настраиваем планировщик уведомлений
    job_queue = app.job_queue
    if job_queue:
        # Уведомления каждый день в 10:00 по Москве (7:00 UTC)
        job_queue.run_daily(
            send_reminder_notifications,
            time=time(hour=7, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6),
            name="daily_reminders"
        )
        print("📅 Планировщик уведомлений настроен")
    else:
        print("⚠️ JobQueue не доступен, уведомления отключены")
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    print("\n✅ Команды зарегистрированы")
    print("📝 Доступные команды:")
    print("  • /start, /new, /list, /premium, /status, /help")
    print("  • /admin, /admin_activate, /admin_deactivate")
    print("  • /broadcast, /broadcast_premium, /broadcast_photo, /broadcast_test")
    print("  • /test, /test_stars")
    print("=" * 60)
    print("⭐ Telegram Stars готов к работе!" if stars_stats['configured'] else "⚠️ Настройте Telegram Stars для автоматических платежей")
    print("=" * 60)
    
    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Даем веб-серверу время запуститься
    time_module.sleep(3)
    print("✅ Веб-сервер запущен")
    
    # Запускаем keep-alive в отдельном потоке
    keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
    keep_alive_thread.start()
    print("✅ Keep-alive механизм запущен")
    
    print("🤖 Telegram бот запускается...")
    print("=" * 60)
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ========== ТОЧКА ВХОДА ==========

if __name__ == "__main__":
    main()
