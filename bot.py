# bot.py - полная версия с работающей кнопкой создания и почтой
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
except:
    ADMIN_ID = 0

# Почта администратора
ADMIN_EMAIL = "support@nezabudioplatit.ru"

# Константы
FREE_LIMIT = 5
PREMIUM_PRICES = {
    '1': {'amount': 299, 'days': 30, 'text': '1 месяц'},
    '3': {'amount': 799, 'days': 90, 'text': '3 месяца'},
    '12': {'amount': 1990, 'days': 365, 'text': '12 месяцев'}
}

# Состояния для ConversationHandler
TITLE, AMOUNT, DATE = range(3)

# ========== БАЗА ДАННЫХ В ПАМЯТИ ==========

class SimpleDB:
    def __init__(self):
        self.users = {}
        self.reminders = []
        self.next_user_id = 1
        self.next_reminder_id = 1
    
    def get_or_create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        if telegram_id not in self.users:
            self.users[telegram_id] = {
                'id': self.next_user_id,
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'is_premium': False,
                'premium_until': None,
                'created_at': datetime.now()
            }
            self.next_user_id += 1
        return self.users[telegram_id]['id']
    
    def get_user_premium_status(self, user_id):
        for user in self.users.values():
            if user['id'] == user_id:
                # Проверяем срок действия премиума
                if user['is_premium'] and user['premium_until']:
                    if datetime.now().date() > user['premium_until']:
                        user['is_premium'] = False
                        user['premium_until'] = None
                
                return {
                    'has_active_premium': user['is_premium'],
                    'premium_until': user['premium_until']
                }
        return {'has_active_premium': False}
    
    def get_user_reminders_count(self, user_id):
        count = 0
        for reminder in self.reminders:
            if reminder['user_id'] == user_id and reminder.get('is_active', True):
                count += 1
        return count
    
    def get_user_reminders(self, user_id):
        user_reminders = []
        for reminder in self.reminders:
            if reminder['user_id'] == user_id and reminder.get('is_active', True):
                user_reminders.append(reminder)
        # Сортируем по дате
        user_reminders.sort(key=lambda x: x['payment_date'])
        return user_reminders
    
    def add_reminder(self, user_id, title, amount, payment_date, recurrence='once'):
        reminder = {
            'id': self.next_reminder_id,
            'user_id': user_id,
            'title': title,
            'amount': amount,
            'payment_date': payment_date,
            'recurrence': recurrence,
            'is_active': True,
            'created_at': datetime.now()
        }
        self.reminders.append(reminder)
        self.next_reminder_id += 1
        return reminder['id']
    
    def delete_reminder(self, user_id, reminder_id):
        for reminder in self.reminders:
            if reminder['id'] == reminder_id and reminder['user_id'] == user_id:
                reminder['is_active'] = False
                return True
        return False
    
    def activate_premium(self, user_id, days):
        for user in self.users.values():
            if user['id'] == user_id:
                user['is_premium'] = True
                if days > 0:
                    user['premium_until'] = datetime.now().date() + timedelta(days=days)
                else:
                    user['premium_until'] = None  # Бессрочно
                return True
        return False
    
    def get_all_users(self):
        return list(self.users.values())
    
    def get_premium_users(self):
        return [user for user in self.users.values() if user['is_premium']]
    
    def get_all_reminders(self):
        return self.reminders
    
    def find_user_by_username(self, username):
        for user in self.users.values():
            if user['username'] == username:
                return user
        return None

# Создаем экземпляр базы данных
db = SimpleDB()

# ========== ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE ==========

def run_web_server():
    """Запуск веб-сервера для keep-alive"""
    try:
        from flask import Flask
        web_app = Flask(__name__)
        
        @web_app.route('/')
        def home():
            return "✅ Telegram Reminder Bot is running"
        
        @web_app.route('/ping')
        def ping():
            return "pong"
        
        @web_app.route('/status')
        def status():
            return {
                "status": "active",
                "users": len(db.get_all_users()),
                "reminders": len([r for r in db.get_all_reminders() if r.get('is_active', True)]),
                "premium_users": len(db.get_premium_users()),
                "timestamp": datetime.now().isoformat()
            }
        
        port = int(os.getenv('PORT', 8080))
        print(f"🌐 Веб-сервер запущен на порту {port}")
        web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ Ошибка веб-сервера: {e}")

def start_keep_alive():
    """Keep-alive для Render"""
    import requests
    
    print("=" * 50)
    print("🔄 ЗАПУСКАЮ KEEP-ALIVE")
    print("⏰ Интервал: 5 минут")
    print("=" * 50)
    
    ping_count = 0
    
    while True:
        try:
            ping_count += 1
            url = f"https://{os.getenv('RENDER_SERVICE_NAME', 'telegram-reminder-bot')}.onrender.com/ping"
            
            response = requests.get(url, timeout=15)
            current_time = time_module.strftime('%H:%M:%S')
            
            if response.status_code == 200 and response.text.strip() == 'pong':
                print(f"✅ [{current_time}] Keep-alive #{ping_count}: OK")
            else:
                print(f"⚠️ [{current_time}] Keep-alive #{ping_count}: Проблема")
                
            time_module.sleep(300)  # 5 минут
                
        except Exception as e:
            current_time = time_module.strftime('%H:%M:%S')
            print(f"🚨 [{current_time}] Keep-alive #{ping_count}: Ошибка")
            time_module.sleep(300)

# ========== УВЕДОМЛЕНИЯ ==========

async def send_reminder_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Отправка ежедневных уведомлений"""
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        notifications_sent = 0
        
        for reminder in db.get_all_reminders():
            if not reminder.get('is_active', True):
                continue
            
            payment_date = reminder['payment_date']
            if isinstance(payment_date, str):
                try:
                    payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
                except:
                    continue
            
            # Проверяем, если платеж завтра
            if payment_date == tomorrow:
                user_id = reminder['user_id']
                user = None
                for u in db.get_all_users():
                    if u['id'] == user_id:
                        user = u
                        break
                
                if user and 'telegram_id' in user:
                    try:
                        message = (
                            f"🔔 <b>НАПОМИНАНИЕ О ПЛАТЕЖЕ</b>\n\n"
                            f"<b>{reminder['title']}</b>\n"
                            f"💰 Сумма: {reminder['amount']}₽\n"
                            f"📅 Дата: {payment_date.strftime('%d.%m.%Y')}\n\n"
                            f"Не забудьте оплатить завтра!"
                        )
                        
                        await context.bot.send_message(
                            chat_id=user['telegram_id'],
                            text=message,
                            parse_mode='HTML'
                        )
                        
                        notifications_sent += 1
                        
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления: {e}")
        
        if notifications_sent > 0:
            logger.info(f"📨 Отправлено {notifications_sent} уведомлений")
            
    except Exception as e:
        logger.error(f"Ошибка в send_reminder_notifications: {e}")

# ========== КОМАНДА /START ==========

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
        
        premium_status = db.get_user_premium_status(user_id)
        reminders_count = db.get_user_reminders_count(user_id)
        
        has_premium = premium_status.get('has_active_premium', False)
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_reminder")],
            [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
            [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
            [InlineKeyboardButton("📧 Помощь", callback_data="help_info")]
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
            f"<b>📧 Почта админа:</b>\n"
            f"<code>{ADMIN_EMAIL}</code>\n\n"
            f"Выберите действие:"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await update.message.reply_text(
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"📧 Почта: {ADMIN_EMAIL}\n\n"
            f"Используйте команды:\n"
            f"/new - создать напоминание\n"
            f"/list - список напоминаний\n"
            f"/help - помощь"
        )

# ========== ПОМОЩЬ ==========

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
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
        f"<b>📧 Почта администратора (для оплаты и вопросов):</b>\n"
        f"<code>{ADMIN_EMAIL}</code>\n\n"
        f"<b>💳 Способ оплаты премиума:</b>\n"
        f"1. Напишите на почту {ADMIN_EMAIL}\n"
        f"2. Укажите ваш Telegram @username\n"
        f"3. Выберите период подписки\n"
        f"4. Админ активирует премиум\n\n"
        f"<i>Ответ в течение 24 часов</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_reminder")],
        [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='HTML')
    elif update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

# ========== СОЗДАНИЕ НАПОМИНАНИЯ ==========

async def create_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки создания напоминания"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Проверяем лимит
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    
    if not has_premium:
        reminders_count = db.get_user_reminders_count(user_id)
        if reminders_count >= FREE_LIMIT:
            await query.edit_message_text(
                f"⚠️ <b>Достигнут лимит!</b>\n\n"
                f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                f"💎 <b>Купите премиум для неограниченных напоминаний!</b>\n\n"
                f"📧 Напишите на почту: {ADMIN_EMAIL}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("🏠 В начало", callback_data="start")]
                ])
            )
            return ConversationHandler.END
    
    # Начинаем процесс создания
    context.user_data['creating_for'] = user_id
    
    await query.edit_message_text(
        "📝 <b>Создание напоминания</b>\n\n"
        "Отправьте мне данные в формате:\n"
        "<code>Название | Сумма | Дата</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>Интернет | 500 | 25.01.2024</code>\n\n"
        "<i>Или напишите 'отмена' для отмены</i>",
        parse_mode='HTML'
    )
    
    return TITLE

async def process_reminder_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка создания напоминания"""
    try:
        text = update.message.text.strip()
        
        if text.lower() == 'отмена':
            await update.message.reply_text("❌ Создание отменено.")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Парсим введенные данные
        parts = [p.strip() for p in text.split('|')]
        if len(parts) != 3:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте:\n"
                "<code>Название | Сумма | Дата</code>\n\n"
                "<b>Пример:</b>\n"
                "<code>Интернет | 500 | 25.01.2024</code>",
                parse_mode='HTML'
            )
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
        user_id = context.user_data.get('creating_for')
        if not user_id:
            await update.message.reply_text("❌ Ошибка. Начните заново.")
            context.user_data.clear()
            return ConversationHandler.END
        
        date_str_db = payment_date.strftime('%Y-%m-%d')
        
        reminder_id = db.add_reminder(
            user_id=user_id,
            title=title,
            amount=amount,
            payment_date=date_str_db
        )
        
        if reminder_id:
            await update.message.reply_text(
                f"✅ <b>Напоминание создано!</b>\n\n"
                f"<b>Название:</b> {title}\n"
                f"<b>Сумма:</b> {amount}₽\n"
                f"<b>Дата:</b> {date_str}\n\n"
                f"Вы получите уведомление за день до платежа.\n\n"
                f"📧 По вопросам: {ADMIN_EMAIL}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                    [InlineKeyboardButton("➕ Еще напоминание", callback_data="create_reminder")],
                    [InlineKeyboardButton("🏠 В начало", callback_data="start")]
                ])
            )
        else:
            await update.message.reply_text("❌ Ошибка сохранения.")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка создания: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуйте снова.")
        return ConversationHandler.END

# ========== СПИСОК НАПОМИНАНИЙ ==========

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list"""
    user = update.effective_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    reminders = db.get_user_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text(
            "📭 <b>У вас пока нет напоминаний.</b>\n\n"
            "Создайте первое напоминание!\n\n"
            f"📧 По вопросам: {ADMIN_EMAIL}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать", callback_data="create_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")]
            ])
        )
        return
    
    message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
    total = 0
    
    for i, rem in enumerate(reminders[:15], 1):
        date_str = rem.get('payment_date', '')
        if isinstance(date_str, str):
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_display = date_obj.strftime('%d.%m.%Y')
            except:
                date_display = date_str
        else:
            date_display = str(date_str)
        
        amount = rem.get('amount', 0)
        total += float(amount)
        
        message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
        message += f"   💰 {amount}₽ | 📅 {date_display}\n\n"
    
    message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на {total:.2f}₽\n\n"
    
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    limit_text = '∞' if has_premium else FREE_LIMIT
    message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n\n"
    
    if not has_premium and len(reminders) >= FREE_LIMIT:
        message += f"⚠️ <b>Достигнут лимит!</b> Купите премиум.\n"
    
    message += f"📧 По вопросам: {ADMIN_EMAIL}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать еще", callback_data="create_reminder")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")]
    ]
    
    if not has_premium and len(reminders) >= FREE_LIMIT - 2:
        keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")])
    
    keyboard.append([InlineKeyboardButton("🏠 В начало", callback_data="start")])
    
    await update.message.reply_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== УДАЛЕНИЕ НАПОМИНАНИЙ ==========

async def delete_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик удаления напоминаний"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data.startswith("delete_"):
            reminder_id = int(query.data.split("_")[1])
            user = query.from_user
            
            user_id = db.get_or_create_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            if db.delete_reminder(user_id, reminder_id):
                await query.edit_message_text(
                    "✅ Напоминание удалено!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
                        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
                    ])
                )
            else:
                await query.edit_message_text("❌ Не удалось удалить напоминание.")
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await query.edit_message_text("❌ Ошибка при удалении.")

# ========== ПРЕМИУМ ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium"""
    user = update.effective_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    
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
            f"<b>Бесплатный тариф:</b>\n"
            f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
            f"• ⏰ Уведомления за 1 день\n\n"
            f"<b>С премиумом:</b>\n"
            f"• ♾️ Неограниченные напоминания\n"
            f"• 🔔 Уведомления за 3 и 7 дней\n\n"
            f"<b>Тарифы:</b>\n"
            f"• 1 месяц — 299₽\n"
            f"• 3 месяца — 799₽\n"
            f"• 12 месяцев — 1990₽\n\n"
            f"<b>📧 Для оплаты напишите на почту:</b>\n"
            f"<code>{ADMIN_EMAIL}</code>\n\n"
            f"<b>В письме укажите:</b>\n"
            f"1. Ваш Telegram @username\n"
            f"2. Выбранный период\n"
            f"3. Админ активирует премиум"
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

# ========== ОБРАБОТЧИК ОСТАЛЬНЫХ КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик остальных кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "start":
            await start_callback(update, context)
        elif query.data == "help_info":
            await help_command(update, context)
        elif query.data == "premium_info":
            await premium_command(update, context)
        elif query.data == "list_reminders":
            await list_reminders_callback(update, context)
        elif query.data.startswith("buy_"):
            await buy_premium_handler(update, context)
        elif query.data == "trial":
            await trial_handler(update, context)
        elif query.data == "admin_panel":
            await admin_panel_callback(update, context)
        elif query.data == "admin_stats":
            await admin_stats_callback(update, context)
        elif query.data == "admin_users":
            await admin_users_callback(update, context)
        elif query.data == "admin_activate":
            await admin_activate_callback(update, context)
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text("⚠️ Ошибка. Попробуйте /start")

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка старта"""
    query = update.callback_query
    user = query.from_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    premium_status = db.get_user_premium_status(user_id)
    reminders_count = db.get_user_reminders_count(user_id)
    
    has_premium = premium_status.get('has_active_premium', False)
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="create_reminder")],
        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
        [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton("📧 Помощь", callback_data="help_info")]
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
        f"<b>📧 Почта админа:</b>\n"
        f"<code>{ADMIN_EMAIL}</code>\n\n"
        f"Выберите действие:"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def list_reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка списка напоминаний"""
    query = update.callback_query
    user = query.from_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    reminders = db.get_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text(
            "📭 <b>У вас пока нет напоминаний.</b>\n\n"
            "Создайте первое напоминание!\n\n"
            f"📧 По вопросам: {ADMIN_EMAIL}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать", callback_data="create_reminder")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                [InlineKeyboardButton("🏠 В начало", callback_data="start")]
            ])
        )
        return
    
    message = "📋 <b>ВАШИ НАПОМИНАНИЯ:</b>\n\n"
    total = 0
    
    for i, rem in enumerate(reminders[:10], 1):
        date_str = rem.get('payment_date', '')
        if isinstance(date_str, str):
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_display = date_obj.strftime('%d.%m.%Y')
            except:
                date_display = date_str
        else:
            date_display = str(date_str)
        
        amount = rem.get('amount', 0)
        total += float(amount)
        
        message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
        message += f"   💰 {amount}₽ | 📅 {date_display}\n\n"
    
    message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на {total:.2f}₽\n"
    
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    limit_text = '∞' if has_premium else FREE_LIMIT
    message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n\n"
    
    if not has_premium and len(reminders) >= FREE_LIMIT:
        message += f"⚠️ <b>Достигнут лимит!</b> Купите премиум.\n"
    
    message += f"📧 По вопросам: {ADMIN_EMAIL}"
    
    keyboard = []
    
    # Кнопки удаления для первых 3 напоминаний
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
        InlineKeyboardButton("➕ Создать еще", callback_data="create_reminder"),
        InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")
    ])
    
    if not has_premium and len(reminders) >= FREE_LIMIT - 2:
        keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")])
    
    keyboard.append([InlineKeyboardButton("🏠 В начало", callback_data="start")])
    
    await query.edit_message_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buy_premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик покупки премиума"""
    query = update.callback_query
    
    period = query.data.split("_")[1]
    if period in PREMIUM_PRICES:
        price_info = PREMIUM_PRICES[period]
        user = query.from_user
        
        message = (
            f"💳 <b>ИНСТРУКЦИИ ДЛЯ ОПЛАТЫ</b>\n\n"
            f"<b>Сумма к оплате:</b> {price_info['amount']}₽\n"
            f"<b>Период подписки:</b> {price_info['text']}\n"
            f"<b>Ваш username:</b> @{user.username or user.id}\n\n"
            f"<b>📧 Для оплаты напишите на почту:</b>\n"
            f"<code>{ADMIN_EMAIL}</code>\n\n"
            f"<b>В письме укажите:</b>\n"
            f"1. Ваш Telegram: @{user.username or user.id}\n"
            f"2. Выбранный период: {price_info['text']}\n"
            f"3. Сумму: {price_info['amount']}₽\n\n"
            f"<b>После письма:</b>\n"
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
            message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def trial_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовый премиум"""
    query = update.callback_query
    user = query.from_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
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

# ========== АДМИН ПАНЕЛЬ ==========

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ панель"""
    query = update.callback_query
    user = query.from_user
    
    if user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    total_users = len(db.get_all_users())
    premium_users = len(db.get_premium_users())
    total_reminders = len([r for r in db.get_all_reminders() if r.get('is_active', True)])
    
    message = (
        f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {total_reminders}\n\n"
        f"<b>📧 Почта:</b> {ADMIN_EMAIL}\n\n"
        f"Выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Активировать", callback_data="admin_activate")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная статистика"""
    query = update.callback_query
    user = query.from_user
    
    if user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    total_users = len(db.get_all_users())
    premium_users = len(db.get_premium_users())
    total_reminders = len([r for r in db.get_all_reminders() if r.get('is_active', True)])
    
    # Активные пользователи (с напоминаниями)
    active_users = 0
    for user_data in db.get_all_users():
        if db.get_user_reminders_count(user_data['id']) > 0:
            active_users += 1
    
    message = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
        f"<b>Основные метрики:</b>\n"
        f"• 👥 Всего пользователей: {total_users}\n"
        f"• 💎 Премиум пользователей: {premium_users}\n"
        f"• 📝 Всего напоминаний: {total_reminders}\n"
        f"• 🎯 Активных пользователей: {active_users}\n"
    )
    
    if total_users > 0:
        message += f"• 📈 Конверсия в премиум: {premium_users/total_users*100:.1f}%\n"
        message += f"• 📊 Среднее напоминаний на пользователя: {total_reminders/total_users:.1f}\n"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_panel")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    query = update.callback_query
    user = query.from_user
    
    if user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    users = db.get_all_users()
    
    if users:
        message = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n"
        for user_data in users[:20]:  # Показываем первые 20
            premium_status = "💎" if user_data['is_premium'] else "🆓"
            username_display = f"@{user_data['username']}" if user_data['username'] else f"ID:{user_data['telegram_id']}"
            name = f"{user_data['first_name'] or ''} {user_data['last_name'] or ''}".strip() or "Без имени"
            
            message += f"{premium_status} <b>{name}</b>\n"
            message += f"   {username_display}\n"
            message += f"   ID: <code>{user_data['telegram_id']}</code>\n\n"
    else:
        message = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\nПользователей пока нет."
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_panel")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def admin_activate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инструкции по активации"""
    query = update.callback_query
    user = query.from_user
    
    if user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    message = (
        "💎 <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
        "<b>Используйте команду:</b>\n"
        "<code>/admin_activate @username дни</code>\n\n"
        "<b>Примеры:</b>\n"
        "<code>/admin_activate @ivanov 30</code> - на 30 дней\n"
        "<code>/admin_activate 123456789 90</code> - по ID на 90 дней\n\n"
        "<b>Или вернитесь в админ-панель:</b>"
    )
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_panel")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    total_users = len(db.get_all_users())
    premium_users = len(db.get_premium_users())
    total_reminders = len([r for r in db.get_all_reminders() if r.get('is_active', True)])
    
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
    
    # Ищем пользователя
    user_data = db.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
        return
    
    user_id = user_data['id']
    
    if db.activate_premium(user_id, days):
        try:
            await context.bot.send_message(
                chat_id=user_data['telegram_id'],
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
            f"Пользователь: {user_data['first_name'] or '@'+username}\n"
            f"Telegram ID: <code>{user_data['telegram_id']}</code>\n"
            f"Срок: {days} дней",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(f"❌ Ошибка активации премиума для @{username}.")

# ========== КОМАНДА /NEW ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /new - создание напоминания"""
    user = update.effective_user
    
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Проверяем лимит
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    
    if not has_premium:
        reminders_count = db.get_user_reminders_count(user_id)
        if reminders_count >= FREE_LIMIT:
            await update.message.reply_text(
                f"⚠️ <b>Достигнут лимит!</b>\n\n"
                f"У вас {reminders_count} из {FREE_LIMIT} напоминаний.\n\n"
                f"💎 Купите премиум!\n"
                f"📧 {ADMIN_EMAIL}",
                parse_mode='HTML'
            )
            return ConversationHandler.END
    
    context.user_data['creating_for'] = user_id
    
    await update.message.reply_text(
        "📝 <b>Создание напоминания</b>\n\n"
        "Отправьте данные в формате:\n"
        "<code>Название | Сумма | Дата</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>Интернет | 500 | 25.01.2024</code>\n\n"
        "<i>Или 'отмена' для отмены</i>",
        parse_mode='HTML'
    )
    
    return TITLE

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    total_users = len(db.get_all_users())
    total_reminders = len([r for r in db.get_all_reminders() if r.get('is_active', True)])
    
    message = (
        f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить»</b>\n\n"
        f"<b>🤖 Бот:</b> ✅ работает\n"
        f"<b>💳 Оплата:</b> через почту\n"
        f"<b>📧 Почта админа:</b> {ADMIN_EMAIL}\n"
        f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
        f"<b>👥 Пользователей:</b> {total_users}\n"
        f"<b>📝 Напоминаний:</b> {total_reminders}\n"
        f"<b>🕒 Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"<b>Команды:</b>\n"
        f"✅ /start — главное меню\n"
        f"✅ /new — создать\n"
        f"✅ /list — список\n"
        f"✅ /premium — премиум\n"
        f"✅ /status — этот статус\n"
        f"✅ /help — помощь\n\n"
        f"<i>Все работает! 🎉</i>"
    )
    
    await update.message.reply_text(message, parse_mode='HTML')

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания"""
    await update.message.reply_text("❌ Создание отменено.")
    context.user_data.clear()
    return ConversationHandler.END

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
    print("🚀 ЗАПУСК БОТА «НеЗабудьОплатить»")
    print(f"📧 Почта админа: {ADMIN_EMAIL}")
    print(f"👑 ADMIN_ID: {ADMIN_ID}")
    print("=" * 60)
    
    print(f"✅ Токен: {'найден' if TOKEN else 'НЕ НАЙДЕН'}")
    print(f"✅ База данных: инициализирована")
    print(f"🌐 Веб-порт: {os.getenv('PORT', 8080)}")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для создания напоминаний
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('new', new_command),
            CallbackQueryHandler(create_reminder_callback, pattern='^create_reminder$')
        ],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_reminder_creation)],
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
    
    app.add_handler(conv_handler)
    
    # Обработчики кнопок (сначала удаление, потом остальные)
    app.add_handler(CallbackQueryHandler(delete_reminder_handler, pattern='^delete_'))
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(?!create_reminder|delete_).*$'))
    
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
