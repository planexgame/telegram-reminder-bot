# bot.py - исправленный код с правильными кнопками
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
    '1': {'amount': 299, 'days': 30, 'text': '1 месяц'},
    '3': {'amount': 799, 'days': 90, 'text': '3 месяца'},
    '12': {'amount': 1990, 'days': 365, 'text': '12 месяцев'}
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
                "timestamp": datetime.now().isoformat()
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
                    "timestamp": datetime.now().isoformat(),
                    "version": "1.0.0"
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
                    cursor.close()
            except:
                total_users = total_reminders = 0
            
            return jsonify({
                "bot": "НеЗабудьОплатить",
                "status": "running",
                "users": total_users,
                "active_reminders": total_reminders,
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
                InlineKeyboardButton("➕ Создать напоминание", callback_data="new_reminder"),
                InlineKeyboardButton("📋 Мои напоминания", callback_data="list")
            ],
            [
                InlineKeyboardButton("💎 Премиум", callback_data="premium_info"),
                InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")
            ]
        ]
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формируем сообщение
        premium_text = "💎 АКТИВЕН" if has_premium else "🆓 БЕСПЛАТНЫЙ"
        limit_text = '∞' if has_premium else FREE_LIMIT
        
        message = (
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"<b>Ваша статистика:</b>\n"
            f"📊 Напоминаний: {reminders_count}/{limit_text}\n"
            f"💎 Статус: {premium_text}\n\n"
            f"<b>Ваши возможности:</b>\n"
            f"• {'♾️ Неограниченные' if has_premium else f'До {FREE_LIMIT}'} напоминаний\n"
            f"• 🔔 Уведомления за {'3 и 7 дней' if has_premium else '1 день'}\n"
            f"• {'🔄 Повторяющиеся платежи' if has_premium else '📅 Разовые напоминания'}\n\n"
            f"Выберите действие:"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        # Упрощенная версия
        await update.message.reply_text(
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"Бот работает! 🚀\n\n"
            f"Используйте команды:\n"
            f"/new - создать напоминание\n"
            f"/list - список напоминаний\n"
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
        "• /buy — купить премиум\n"
        "• /status — статус бота\n"
        "• /help — эта справка\n\n"
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
        "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
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
        
        # Проверяем лимиты
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if not has_premium:
            reminders_count = db.get_user_reminders_count(user_id)
            if reminders_count >= FREE_LIMIT:
                keyboard = [
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")],
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        await update.message.reply_text(
            "📝 <b>Создание напоминания</b>\n\n"
            "Шаг 1 из 3\n"
            "Введите <b>название платежа</b>:\n\n"
            "Например: <i>Коммунальные услуги, Интернет, Кредит</i>\n\n"
            "Для отмены используйте команду /cancel",
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
        "Например: <i>4500</i> или <i>1250.50</i>\n\n"
        "Для отмены используйте команду /cancel",
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
            "Например: <i>25.01.2024</i>\n\n"
            "Для отмены используйте команду /cancel",
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
                [InlineKeyboardButton("➕ Еще напоминание", callback_data="new_reminder")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="start_menu")]
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
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="start_menu")],
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="new_reminder")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❌ Создание напоминания отменено.",
        reply_markup=reply_markup
    )
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
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="new_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
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
            message += f"Купите премиум для неограниченных напоминаний 💎\n"
        
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
            InlineKeyboardButton("➕ Создать еще", callback_data="new_reminder"),
            InlineKeyboardButton("🔙 Назад", callback_data="start_menu")
        ])
        
        # Если нет премиума и достигнут/почти достигнут лимит
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")])
        
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
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="new_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
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
            message += f"Купите премиум для неограниченных напоминаний 💎\n"
        
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
            InlineKeyboardButton("➕ Создать еще", callback_data="new_reminder"),
            InlineKeyboardButton("🔙 Назад", callback_data="start_menu")
        ])
        
        # Если нет премиума и достигнут/почти достигнут лимит
        if not has_premium and len(reminders) >= FREE_LIMIT - 2:
            keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")])
        
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
            f"<b>🕒 Время уведомлений:</b> 10:00 по Москве\n"
            f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
            f"<b>🕒 Серверное время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Работающие команды:</b>\n"
            f"✅ /start — запуск бота\n"
            f"✅ /new — создание напоминания\n"
            f"✅ /list — список напоминаний\n"
            f"✅ /premium — премиум подписка\n"
            f"✅ /buy — покупка премиума\n"
            f"✅ /status — этот статус\n"
            f"✅ /help — справка\n\n"
            f"<i>Все системы работают нормально! 🎉</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="start_menu")],
            [InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

# ========== ПРЕМИУМ КОМАНДЫ ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium - с возможностью покупки"""
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
                message = f"💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует до: <b>{until_str}</b>"
            else:
                message = "💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует бессрочно"
            
            keyboard = [
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
            ]
        else:
            # Если нет премиума - предлагаем купить
            message = (
                f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                f"<b>Бесплатный тариф ограничен:</b>\n"
                f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
                f"• ⏰ Уведомления только за 1 день\n"
                f"• 🔄 Нет повторяющихся платежей\n\n"
                f"<b>С премиум вы получаете:</b>\n"
                f"• ♾️ Неограниченные напоминания\n"
                f"• 🔄 Повторяющиеся платежи\n"
                f"• 🔔 Уведомления за 3 и 7 дней\n"
                f"• 📊 Расширенная статистика\n\n"
                f"<b>Выберите подписку:</b>"
            )
            
            # Кнопки покупки
            keyboard = [
                [
                    InlineKeyboardButton("1 месяц - 299₽", callback_data="buy_1"),
                    InlineKeyboardButton("3 месяца - 799₽", callback_data="buy_3")
                ],
                [
                    InlineKeyboardButton("12 месяцев - 1990₽", callback_data="buy_12"),
                    InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
                ],
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
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

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /buy - покупка премиума"""
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
        
        # Проверяем, не активна ли уже подписка
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            await update.message.reply_text(
                "✅ У вас уже активна премиум подписка!\n\n"
                "Используйте команду /premium чтобы увидеть детали."
            )
            return
        
        # Предлагаем варианты
        keyboard = [
            [
                InlineKeyboardButton("1 месяц - 299₽", callback_data="buy_1"),
                InlineKeyboardButton("3 месяца - 799₽", callback_data="buy_3")
            ],
            [
                InlineKeyboardButton("12 месяцев - 1990₽", callback_data="buy_12"),
                InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💳 <b>ВЫБЕРИТЕ ПОДПИСКУ</b>\n\n"
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
        logger.error(f"Ошибка в buy_command: {e}")
        await update.message.reply_text("❌ Ошибка при оформлении подписки.")

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Основные кнопки
        if query.data == "new_reminder":
            # Используем команду /new через создание временного сообщения
            from telegram import Message
            from telegram._utils.types import ReplyMarkup
            
            # Создаем fake message для вызова new_command
            fake_message = Message(
                message_id=query.message.message_id + 1,
                date=datetime.now(),
                chat=query.message.chat,
                text="/new"
            )
            fake_message.from_user = query.from_user
            
            # Создаем fake update
            fake_update = Update(
                update_id=query.id,
                message=fake_message
            )
            
            # Запускаем команду /new
            await new_command(fake_update, context)
            
        elif query.data == "start_menu":
            # Возврат в главное меню через создание fake команды /start
            fake_message = Message(
                message_id=query.message.message_id + 1,
                date=datetime.now(),
                chat=query.message.chat,
                text="/start"
            )
            fake_message.from_user = query.from_user
            
            fake_update = Update(
                update_id=query.id,
                message=fake_message
            )
            
            await start(fake_update, context)
            
        elif query.data == "create":
            # Альтернативная кнопка создания (для обратной совместимости)
            await query.edit_message_text(
                "📝 <b>СОЗДАНИЕ НАПОМИНАНИЯ</b>\n\n"
                "Для создания напоминания нажмите кнопку:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Создать напоминание", callback_data="new_reminder")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data == "list":
            # Вызываем функцию обработки списка напоминаний
            await handle_list_button(update, context)
            
        elif query.data == "premium_info":
            # Создаем временный update для premium_command
            class FakeMessage:
                def __init__(self, user, chat):
                    self.from_user = user
                    self.text = "/premium"
                    self.chat = chat
                
                async def reply_text(self, text, **kwargs):
                    return await query.edit_message_text(text, **kwargs)
            
            fake_msg = FakeMessage(query.from_user, query.message.chat)
            fake_update = Update(update_id=query.id, message=fake_msg, callback_query=query)
            
            await premium_command(fake_update, context)
            
        elif query.data == "buy_premium":
            await query.edit_message_text(
                "💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                "Для покупки премиум подписки используйте команду /buy\n\n"
                "Или выберите вариант подписки:",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("1 месяц - 299₽", callback_data="buy_1"),
                        InlineKeyboardButton("3 месяца - 799₽", callback_data="buy_3")
                    ],
                    [
                        InlineKeyboardButton("12 месяцев - 1990₽", callback_data="buy_12"),
                        InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")
                    ],
                    [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data.startswith("buy_"):
            period = query.data.split("_")[1]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{period}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"💳 <b>ОПЛАТА {price_info['text'].upper()} ПОДПИСКИ</b>\n\n"
                    f"Сумма: {price_info['amount']}₽\n\n"
                    "<b>Для оплаты:</b>\n"
                    "1. Переведите на карту:\n"
                    "<code>2204 1801 8490 6030</code>\n"
                    "2. В комментарии укажите ваш username\n"
                    "3. Нажмите '✅ Я оплатил'\n\n"
                    "<b>Или отправьте на USDT (TRC20):</b>\n"
                    "<code>TQzCJToybGtn8NnXQ6DTb2qZCBWcpuzX6s</code>\n\n"
                    "Администратор активирует премиум вручную.",
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
                        message = f"💎 <b>ПРЕМИУМ СТАТУС</b>\n\nВаш премиум действует до: <b>{until_str}</b>"
                    else:
                        message = "💎 <b>ПРЕМИУМ СТАТУС</b>\n\nУ вас активна бессрочная премиум подписка!"
                    
                    keyboard = [
                        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
                    ]
                else:
                    message = "🆓 <b>ПРЕМИУМ СТАТУС</b>\n\nУ вас нет активной премиум подписки."
                    keyboard = [
                        [InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
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
                    # После удаления показываем обновленный список
                    await handle_list_button(update, context)
                else:
                    await query.edit_message_text("❌ Не удалось удалить напоминание.")
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
                await query.edit_message_text("❌ Ошибка при удалении.")
                
        elif query.data == "help_btn":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")],
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
                "<b>Основные команды:</b>\n"
                "• /start - начать работу\n"
                "• /new - создать напоминание\n"
                "• /list - список напоминаний\n"
                "• /premium - премиум подписка\n"
                "• /buy - купить премиум\n"
                "• /status - статус бота\n"
                "• /help - эта справка\n\n"
                f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
                "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
                "<i>По вопросам обращайтесь к администратору</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        # Админ кнопки
        elif query.data == "admin_panel":
            await admin_command(update, context)
            
        elif query.data == "admin_stats":
            await admin_stats_handler(query, context)
            
        elif query.data == "admin_users":
            await admin_users_handler(query, context)
            
        elif query.data == "admin_activate":
            await query.edit_message_text(
                "💎 <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
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
            
        elif query.data == "test_admin_notify":
            """Тест уведомлений админу через кнопку"""
            if query.from_user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text="🔔 <b>ТЕСТ ЧЕРЕЗ КНОПКУ</b>\n\n"
                         "✅ Кнопочные уведомления работают!\n\n"
                         "Теперь попробуйте реальную оплату.",
                    parse_mode='HTML'
                )
                
                await query.edit_message_text(
                    "✅ <b>Тест завершен!</b>\n\n"
                    "Проверьте уведомление от бота.",
                    parse_mode='HTML'
                )
                
            except Exception as e:
                logger.error(f"Ошибка test_admin_notify button: {e}")
                await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
                
        elif query.data == "trial":
            user = query.from_user
            user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
            
            if db.activate_premium(user_id, 7):
                keyboard = [
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "🎉 <b>Тестовый премиум активирован!</b>\n\n"
                    "Вам доступны все функции премиума на 7 дней:\n\n"
                    "• ♾️ Неограниченные напоминания\n"
                    "• 🔄 Повторяющиеся платежи\n"
                    "• 🔔 Уведомления за 3 и 7 дней\n\n"
                    "Наслаждайтесь! Если понравится - сможете оформить полную подписку. 💎",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Ошибка активации тестового периода.")
                
        # ========== ИСПРАВЛЕННЫЙ ОБРАБОТЧИК КНОПКИ "Я ОПЛАТИЛ" ==========
        elif query.data.startswith("manual_paid_"):
            """Обработчик кнопки 'Я оплатил' с уведомлением админу"""
            try:
                # Получаем период из callback_data: manual_paid_1 → period=1
                period = query.data.split("_")[2] if len(query.data.split("_")) > 2 else "1"
                
                if period in PREMIUM_PRICES:
                    price_info = PREMIUM_PRICES[period]
                    user = query.from_user
                    
                    # 1. Логируем нажатие
                    logger.info(f"💰 Кнопка 'Я оплатил' нажата: user_id={user.id}, username=@{user.username}, period={period}")
                    
                    # 2. Сообщение пользователю
                    await query.edit_message_text(
                        f"✅ <b>Заявка принята!</b>\n\n"
                        f"<b>Детали оплаты:</b>\n"
                        f"• Подписка: {price_info['text']}\n"
                        f"• Сумма: {price_info['amount']}₽\n"
                        f"• Срок: {price_info['days']} дней\n\n"
                        f"<b>Что дальше:</b>\n"
                        f"1. Администратор получил уведомление\n"
                        f"2. Он активирует ваш премиум вручную\n"
                        f"3. Вы получите сообщение о активации\n\n"
                        f"Обычно это занимает до 24 часов.\n\n"
                        f"Спасибо за покупку! 💎",
                        parse_mode='HTML'
                    )
                    
                    # 3. Формируем уведомление для администратора
                    try:
                        username_display = f"@{user.username}" if user.username else f"ID_{user.id}"
                        first_name_display = user.first_name or "Не указано"
                        last_name_display = user.last_name or "Не указана"
                        
                        admin_message = (
                            f"💰 <b>НОВАЯ ЗАЯВКА НА ОПЛАТУ!</b>\n\n"
                            f"<b>👤 Пользователь:</b>\n"
                            f"├ Имя: {first_name_display}\n"
                            f"├ Фамилия: {last_name_display}\n"
                            f"├ Username: {username_display}\n"
                            f"└ ID: <code>{user.id}</code>\n\n"
                            f"<b>📦 Подписка:</b>\n"
                            f"├ Период: {price_info['text']}\n"
                            f"├ Сумма: {price_info['amount']}₽\n"
                            f"└ Дней: {price_info['days']}\n\n"
                            f"<b>⚡ Быстрая активация:</b>\n"
                            f"<code>/admin_activate {username_display.replace('@', '')} {price_info['days']}</code>\n"
                            f"или\n"
                            f"<code>/admin_activate {user.id} {price_info['days']}</code>\n\n"
                            f"<b>⏰ Время заявки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                            f"<i>Для просмотра всех заявок: /admin_requests</i>"
                        )
                        
                        # 4. Отправляем уведомление администратору
                        sent_message = await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=admin_message,
                            parse_mode='HTML'
                        )
                        
                        logger.info(f"✅ Уведомление отправлено администратору {ADMIN_ID}. Message ID: {sent_message.message_id}")
                        
                    except Exception as admin_error:
                        error_msg = str(admin_error)
                        logger.error(f"❌ Ошибка отправки уведомления админу: {error_msg}")
                        
                        # Сообщаем пользователю
                        await query.message.reply_text(
                            f"⚠️ <b>Внимание!</b>\n\n"
                            f"Не удалось автоматически уведомить администратора.\n\n"
                            f"<b>Ваши данные для ручной активации:</b>\n"
                            f"• Ваш ID: <code>{user.id}</code>\n"
                            f"• Подпика: {price_info['text']}\n"
                            f"• Сумма: {price_info['amount']}₽\n\n"
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
        
        # Админ рассылка кнопки (упрощенная версия)
        elif query.data == "broadcast_text":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📝 <b>ТЕКСТОВАЯ РАССЫЛКА</b>\n\n"
                "Используйте команду:\n"
                "<code>/broadcast Ваш текст</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/broadcast Новое обновление! Добавлены крутые функции</code>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif query.data == "broadcast_photo":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🖼️ <b>РАССЫЛКА С ФОТО</b>\n\n"
                "Используйте команду:\n"
                "<code>/broadcast_photo</code>\n\n"
                "Затем отправьте фото и текст.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif query.data == "broadcast_premium":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "💎 <b>РАССЫЛКА ПРЕМИУМ ПОЛЬЗОВАТЕЛЯМ</b>\n\n"
                "Используйте команду:\n"
                "<code>/broadcast_premium Ваш текст</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>/broadcast_premium Специальное предложение для наших премиум пользователей!</code>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif query.data == "broadcast_free":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🆓 <b>РАССЫЛКА БЕСПЛАТНЫМ ПОЛЬЗОВАТЕЛЯМ</b>\n\n"
                "Используйте команду:\n"
                "<code>/broadcast Ваш текст</code>\n\n"
                "А затем выберите 'Только бесплатные'",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")

# ========== ОБНОВЛЕННАЯ ФУНКЦИЯ АДМИН-ПАНЕЛИ ==========

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
            else:
                total_users = premium_users = total_reminders = 0
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        total_users = premium_users = total_reminders = 0
    
    # Клавиатура с рассылкой
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="broadcast_text")],
        [
            InlineKeyboardButton("💎 Активировать", callback_data="admin_activate"),
            InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
            f"<b>Статистика:</b>\n"
            f"• 👥 Пользователей: {total_users}\n"
            f"• 💎 Премиум: {premium_users}\n"
            f"• 📝 Напоминаний: {total_reminders}\n\n"
            f"<b>Доступные функции:</b>\n"
            f"• 📨 Рассылка сообщений\n"
            f"• 💎 Управление премиумом\n"
            f"• 📊 Просмотр статистики\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
            f"<b>Статистика:</b>\n"
            f"• 👥 Пользователей: {total_users}\n"
            f"• 💎 Премиум: {premium_users}\n"
            f"• 📝 Напоминаний: {total_reminders}\n\n"
            f"<b>Доступные функции:</b>\n"
            f"• 📨 Рассылка сообщений\n"
            f"• 💎 Управление премиумом\n"
            f"• 📊 Просмотр статистики\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

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
            else:
                total = premium = reminders = 0
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
            f"• 👥 Всего пользователей: {total}\n"
            f"• 💎 Премиум пользователей: {premium}\n"
            f"• 📝 Всего напоминаний: {reminders}\n\n"
            f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>",
            reply_markup=reply_markup,
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
            premium = "💎" if is_premium else "🆓"
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
                InlineKeyboardButton("💎 Активировать", callback_data="admin_activate"),
                InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота с веб-сервером"""
    print("=" * 60)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
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
    
    print(f"💳 Система оплаты: РУЧНАЯ")
    
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
    
    # ConversationHandler для рассылки с фото
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
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    app.add_handler(CommandHandler("admin_deactivate", admin_deactivate_command))
    app.add_handler(CommandHandler("broadcast", admin_broadcast_command))
    app.add_handler(CommandHandler("broadcast_premium", admin_broadcast_premium_command))
    app.add_handler(CommandHandler("broadcast_test", admin_broadcast_test_command))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CommandHandler("test_notify", test_notify_command))
    app.add_handler(CommandHandler("test_admin", test_admin_notify_command))
    app.add_handler(CommandHandler("test_payment", test_payment_notify))
    app.add_handler(CommandHandler("admin_requests", admin_requests_command))
    app.add_handler(conv_handler)
    app.add_handler(broadcast_conv_handler)
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
    print("  • /start, /new, /list, /premium, /buy, /status, /help")
    print("  • /admin, /admin_activate, /admin_deactivate")
    print("  • /broadcast, /broadcast_premium, /broadcast_photo, /broadcast_test")
    print("  • /test, /test_notify, /test_admin, /test_payment")
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
    
    # Запускаем бота (блокирующий вызов)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ========== ТОЧКА ВХОДА ==========

if __name__ == "__main__":
    main()
