# bot.py - исправленный код с работающей кнопкой создания
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
        exit(1)
except Exception as e:
    logger.error(f"❌ Ошибка загрузки ADMIN_ID: {e}")
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

# ========== ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE ==========

def run_web_server():
    """Простой веб-сервер для keep-alive"""
    try:
        from flask import Flask
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return "Bot is running"
        
        @app.route('/ping')
        def ping():
            return "pong", 200
        
        port = int(os.getenv('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
    except ImportError:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Bot is running')
            
            def log_message(self, format, *args):
                pass
        
        port = int(os.getenv('PORT', 8080))
        server = HTTPServer(('0.0.0.0', port), Handler)
        server.serve_forever()

def start_keep_alive():
    """Keep-alive для Render"""
    import requests
    
    while True:
        try:
            url = "https://telegram-reminder-bot-vc4c.onrender.com/ping"
            requests.get(url, timeout=10)
        except:
            pass
        time_module.sleep(300)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - главное меню"""
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
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуйте снова.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = (
        "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• /start — главное меню\n"
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
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

# ========== КОМАНДА /NEW ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания - вызывается из кнопки"""
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

async def new_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания из кнопки"""
    query = update.callback_query
    await query.answer()
    
    # Создаем fake update для запуска new_command
    user = query.from_user
    
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
        
        # Проверяем лимиты
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if not has_premium:
            reminders_count = db.get_user_reminders_count(user_id)
            if reminders_count >= FREE_LIMIT:
                keyboard = [
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return
        
        # Отправляем сообщение о начале создания
        await query.edit_message_text(
            "📝 <b>Создание напоминания</b>\n\n"
            "Шаг 1 из 3\n"
            "Введите <b>название платежа</b>:\n\n"
            "Например: <i>Коммунальные услуги, Интернет, Кредит</i>\n\n"
            "Для отмены используйте команду /cancel",
            parse_mode='HTML'
        )
        
        # Устанавливаем состояние для ConversationHandler
        context.user_data['user_id'] = user_id
        context.user_data['from_button'] = True
        context.user_data['chat_id'] = query.message.chat.id
        context.user_data['message_id'] = query.message.message_id
        
        # Запускаем ConversationHandler вручную
        return await get_title_from_button(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в new_from_button: {e}")
        await query.edit_message_text("❌ Ошибка при создании напоминания.")

async def get_title_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидаем ввода названия после нажатия кнопки"""
    # Эта функция будет вызываться для обработки следующего сообщения пользователя
    return TITLE

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
                [InlineKeyboardButton("🔙 В меню", callback_data="start_menu")]
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
        [InlineKeyboardButton("🔙 В меню", callback_data="start_menu")],
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
        reminders = db.get_user_reminders(user_id)
        
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
        
        # Получаем статус премиума
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False)
        limit_text = '∞' if has_premium else FREE_LIMIT
        message += f"<b>🎯 Лимит:</b> {len(reminders)}/{limit_text}\n"
        
        if not has_premium and len(reminders) >= FREE_LIMIT:
            message += f"\n⚠️ <b>Достигнут бесплатный лимит!</b>\n"
            message += f"Купите премиум для неограниченных напоминаний 💎\n"
        
        # Клавиатура
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
        
        # Добавляем кнопки удаления
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
        await update.message.reply_text("❌ Ошибка при получении списка.")

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        user = query.from_user
        
        if query.data == "start_menu":
            # Возврат в главное меню
            await start(update, context)
            
        elif query.data == "new_reminder":
            # ЗАПУСК СОЗДАНИЯ НАПОМИНАНИЯ ИЗ КНОПКИ!
            await new_from_button(update, context)
            
        elif query.data == "list":
            # Показ списка напоминаний
            await list_handler(update, context)
            
        elif query.data == "premium_info":
            # Информация о премиуме
            await premium_handler(update, context)
            
        elif query.data == "help_btn":
            # Помощь
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
                "<b>Основные команды:</b>\n"
                "• /start — главное меню\n"
                "• /new — создать напоминание\n"
                "• /list — список напоминаний\n"
                "• /premium — премиум подписка\n"
                "• /buy — купить премиум\n"
                "• /status — статус бота\n"
                "• /help — эта справка\n\n"
                f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
                "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
                "<i>По вопросам обращайтесь к администратору</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif query.data.startswith("delete_"):
            # Удаление напоминания
            try:
                reminder_id = int(query.data.split("_")[1])
                user_id = db.get_or_create_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                
                if db.delete_reminder(user_id, reminder_id):
                    await query.edit_message_text("✅ Напоминание удалено!")
                    # Показываем обновленный список
                    await list_handler(update, context)
                else:
                    await query.edit_message_text("❌ Не удалось удалить напоминание.")
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
                await query.edit_message_text("❌ Ошибка при удалении.")
                
        elif query.data.startswith("buy_"):
            # Покупка подписки
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
                    "Администратор активирует премиум вручную.",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
        elif query.data == "trial":
            # Тестовый период
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
                    "• 🔔 Уведомления за 3 и 7 дней\n\n"
                    "Наслаждайтесь! Если понравится - сможете оформить полную подписку. 💎",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Ошибка активации тестового периода.")
                
        elif query.data.startswith("manual_paid_"):
            # Обработка оплаты
            period = query.data.split("_")[2] if len(query.data.split("_")) > 2 else "1"
            
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                
                # Сообщение пользователю
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
                
                # Уведомление администратору
                username_display = f"@{user.username}" if user.username else f"ID_{user.id}"
                admin_message = (
                    f"💰 <b>НОВАЯ ЗАЯВКА НА ОПЛАТУ!</b>\n\n"
                    f"<b>👤 Пользователь:</b>\n"
                    f"├ Имя: {user.first_name or 'Не указано'}\n"
                    f"├ Username: {username_display}\n"
                    f"└ ID: <code>{user.id}</code>\n\n"
                    f"<b>📦 Подписка:</b>\n"
                    f"├ Период: {price_info['text']}\n"
                    f"├ Сумма: {price_info['amount']}₽\n"
                    f"└ Дней: {price_info['days']}\n\n"
                    f"<b>⚡ Быстрая активация:</b>\n"
                    f"<code>/admin_activate {user.id} {price_info['days']}</code>\n\n"
                    f"<b>⏰ Время заявки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_message,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления админу: {e}")
                    
        # Админ кнопки
        elif query.data == "admin_panel":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await admin_handler(update, context)
            
        elif query.data == "admin_stats":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await admin_stats_handler(update, context)
            
        elif query.data == "admin_users":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await admin_users_handler(update, context)
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")

async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки списка напоминаний"""
    query = update.callback_query
    user = query.from_user
    
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
            payment_date = rem.get('payment_date', '')
            if isinstance(payment_date, str):
                try:
                    date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = payment_date
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
        
        # Клавиатура
        keyboard = [
            [InlineKeyboardButton("➕ Создать еще", callback_data="new_reminder")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
        ]
        
        # Если есть напоминания, добавляем кнопки удаления
        if reminders:
            # Добавляем кнопку удаления первого напоминания
            first_reminder = reminders[0]
            reminder_id = first_reminder.get('id')
            if reminder_id:
                keyboard.insert(0, [
                    InlineKeyboardButton(
                        f"🗑 Удалить первое",
                        callback_data=f"delete_{reminder_id}"
                    )
                ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_handler: {e}")
        await query.edit_message_text("❌ Ошибка при получении списка.")

async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки премиума"""
    query = update.callback_query
    user = query.from_user
    
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
        
        # Получаем статус
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
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
            ]
        else:
            message = (
                f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                f"<b>Бесплатный тариф ограничен:</b>\n"
                f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
                f"• ⏰ Уведомления только за 1 день\n\n"
                f"<b>С премиум вы получаете:</b>\n"
                f"• ♾️ Неограниченные напоминания\n"
                f"• 🔔 Уведомления за 3 и 7 дней\n\n"
                f"<b>Выберите подписку:</b>"
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
                [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в premium_handler: {e}")
        await query.edit_message_text("❌ Ошибка получения информации о премиуме.")

# ========== ПРОСТОЙ СПОСОБ: НОВЫЙ HANDLER ДЛЯ КНОПКИ ==========

async def handle_new_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Простой обработчик кнопки создания напоминания"""
    query = update.callback_query
    await query.answer()
    
    # Просто отправляем команду /new от имени пользователя
    fake_message = type('obj', (object,), {
        'text': '/new',
        'from_user': query.from_user,
        'chat': query.message.chat,
        'reply_text': query.message.reply_text
    })
    
    fake_update = Update(update_id=update.update_id, message=fake_message)
    
    # Вызываем команду /new
    await new_command(fake_update, context)

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота"""
    print("=" * 60)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
    print("=" * 60)
    
    print(f"✅ Токен: {'найден' if TOKEN else 'НЕ НАЙДЕН'}")
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
    
    # Проверка БД
    try:
        if db.init_db():
            print("✅ База данных: подключена")
        else:
            print("⚠️ База данных: проблемы с подключением")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    
    # Создаем приложение бота
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    
    # ConversationHandler для создания напоминаний
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('new', new_command),
            CallbackQueryHandler(handle_new_from_button, pattern='^new_reminder$')
        ],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    
    # Обработчик остальных кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Настраиваем планировщик уведомлений
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(
            send_reminder_notifications,
            time=time(hour=7, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6),
            name="daily_reminders"
        )
        print("📅 Планировщик уведомлений настроен")
    
    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    print("✅ Веб-сервер запущен")
    
    # Запускаем keep-alive в отдельном потоке
    keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
    keep_alive_thread.start()
    print("✅ Keep-alive механизм запущен")
    
    print("🤖 Telegram бот запускается...")
    print("=" * 60)
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
