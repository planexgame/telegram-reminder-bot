# bot.py - полный обновленный код
import os
import logging
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
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

# ========== ПРОСТОЙ ВЕБ-СЕРВЕР ==========

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
        print(f"🌐 Веб-сервер запущен на порту {port}")
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

# ========== ГЛАВНОЕ МЕНЮ ==========

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
            f"Привет, {user.first_name}! Как твои дела?🙂\n\n"
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
        error_msg = "❌ Ошибка. Попробуйте снова."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

# ========== СОЗДАНИЕ НАПОМИНАНИЯ ==========

async def start_new_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания - вызывается из кнопки или команды"""
    query = update.callback_query
    user = query.from_user if query else update.effective_user
    
    try:
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            if query:
                await query.edit_message_text("❌ Ошибка базы данных.")
            else:
                await update.message.reply_text("❌ Ошибка базы данных.")
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
                
                text = (
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!"
                )
                
                if query:
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
                return
        
        # Сохраняем состояние - пользователь начал создание
        context.user_data['creating_reminder'] = True
        context.user_data['step'] = 'title'
        context.user_data['user_id'] = user_id
        
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="start_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "📝 <b>Создание напоминания</b>\n\n"
            "Шаг 1 из 3\n"
            "Введите <b>название платежа</b>:\n\n"
            "Например: <i>Коммунальные услуги, Интернет, Кредит</i>"
        )
        
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в start_new_reminder: {e}")
        error_msg = "❌ Ошибка при создании напоминания."
        if query:
            await query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений для создания напоминания"""
    if not context.user_data.get('creating_reminder'):
        return
    
    user = update.effective_user
    text = update.message.text.strip()
    
    try:
        step = context.user_data.get('step')
        
        if step == 'title':
            # Сохраняем название
            context.user_data['title'] = text
            context.user_data['step'] = 'amount'
            
            keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="start_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Шаг 2 из 3\n"
                "Введите <b>сумму платежа</b> (в рублях):\n\n"
                "Например: <i>4500</i> или <i>1250.50</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif step == 'amount':
            # Проверяем и сохраняем сумму
            try:
                amount_text = text.replace(',', '.').strip()
                amount = float(amount_text)
                
                if amount <= 0:
                    await update.message.reply_text("❌ Сумма должна быть больше 0. Введите снова:")
                    return
                
                context.user_data['amount'] = amount
                context.user_data['step'] = 'date'
                
                keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="start_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "Шаг 3 из 3\n"
                    "Введите <b>дату платежа</b> (ДД.ММ.ГГГГ):\n\n"
                    "Например: <i>25.01.2024</i>",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
            except ValueError:
                await update.message.reply_text("❌ Неверный формат суммы. Введите число:")
                
        elif step == 'date':
            # Сохраняем напоминание
            try:
                day, month, year = map(int, text.split('.'))
                payment_date = datetime(year, month, day).date()
                
                # Проверяем что дата в будущем
                if payment_date < datetime.now().date():
                    await update.message.reply_text("❌ Дата должна быть в будущем. Введите снова:")
                    return
                
                # Получаем данные
                user_id = context.user_data.get('user_id')
                title = context.user_data.get('title')
                amount = context.user_data.get('amount')
                
                if not all([user_id, title, amount]):
                    await update.message.reply_text("❌ Ошибка данных. Начните заново.")
                    return
                
                date_str = payment_date.strftime('%Y-%m-%d')
                
                # Сохраняем в БД
                reminder_id = db.add_reminder(
                    user_id=user_id,
                    title=title,
                    amount=amount,
                    payment_date=date_str
                )
                
                if reminder_id:
                    # Очищаем состояние
                    context.user_data.clear()
                    
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
                        f"<b>Дата:</b> {text}\n\n"
                        f"Вы получите уведомление за день до платежа.",
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text("❌ Ошибка сохранения.")
                    context.user_data.clear()
                
            except Exception as e:
                logger.error(f"Ошибка при сохранении напоминания: {e}")
                await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")
        context.user_data.clear()

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
            # ЗАПУСК СОЗДАНИЯ НАПОМИНАНИЯ!
            await start_new_reminder(update, context)
            
        elif query.data == "list":
            # Показ списка напоминаний
            await show_reminders(update, context)
            
        elif query.data == "premium_info":
            # Информация о премиуме
            await show_premium_info(update, context)
            
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
                "<i>По вопросам обращайтесь к администратору</i>\n"
                "Почта администратора для связи: planexgame@gmail.com",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        elif query.data == "buy_premium":
            # Перенаправляем на информацию о премиуме
            await show_premium_info(update, context)
            
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
                    await show_reminders(update, context)
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
            await show_admin_panel(update, context)
            
        elif query.data == "admin_stats":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await show_admin_stats(update, context)
            
        elif query.data == "admin_users":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await show_admin_users(update, context)
            
        elif query.data == "admin_activate_user":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await show_admin_activate_form(update, context)
            
        elif query.data == "admin_deactivate_user":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await show_admin_deactivate_form(update, context)
            
        elif query.data == "admin_broadcast":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await show_admin_broadcast_form(update, context)
            
        elif query.data == "broadcast_all":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await execute_broadcast(update, context, premium_only=False)
            
        elif query.data == "broadcast_premium_only":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await execute_broadcast(update, context, premium_only=True)
            
        elif query.data == "broadcast_photo":
            if user.id != ADMIN_ID:
                await query.edit_message_text("❌ Доступ запрещен.")
                return
            await query.edit_message_text("ℹ️ Для рассылки с фото используйте команду /broadcast в ответ на фото")
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        try:
            await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")
        except:
            pass

# ========== ФУНКЦИИ ДЛЯ ПОКАЗА РАЗНЫХ МЕНЮ ==========

async def show_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список напоминаний"""
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
                "Создайте первое напоминание о платеже!",
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
        keyboard = []
        
        # Кнопки удаления (первые 2 напоминания)
        for i in range(min(2, len(reminders))):
            reminder = reminders[i]
            reminder_id = reminder.get('id')
            if reminder_id:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 Удалить {i+1}. {reminder.get('title', 'Без названия')[:15]}...",
                        callback_data=f"delete_{reminder_id}"
                    )
                ])
        
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="new_reminder"),
            InlineKeyboardButton("🔙 Назад", callback_data="start_menu")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в show_reminders: {e}")
        await query.edit_message_text("❌ Ошибка при получении списка.")

async def show_premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о премиуме"""
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
        logger.error(f"Ошибка в show_premium_info: {e}")
        await query.edit_message_text("❌ Ошибка получения информации о премиуме.")

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель"""
    query = update.callback_query
    
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
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("✅ Активировать премиум", callback_data="admin_activate_user")],
        [InlineKeyboardButton("❌ Деактивировать премиум", callback_data="admin_deactivate_user")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {total_reminders}\n\n"
        f"<b>Действия:</b>"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику админа"""
    query = update.callback_query
    
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
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        total = premium = reminders = 0
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"• 👥 Всего пользователей: {total}\n"
        f"• 💎 Премиум пользователей: {premium}\n"
        f"• 📝 Всего напоминаний: {reminders}\n\n"
        f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def show_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список пользователей"""
    query = update.callback_query
    
    try:
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, first_name, is_premium, created_at 
                    FROM users 
                    ORDER BY created_at DESC 
                    LIMIT 10
                """)
                users = cursor.fetchall()
            else:
                users = []
        
        if not users:
            await query.edit_message_text("📭 Пользователей пока нет.")
            return
        
        message = "👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ:</b>\n\n"
        
        for i, (username, first_name, is_premium, created_at) in enumerate(users, 1):
            username_display = f"@{username}" if username else "нет username"
            premium = "💎" if is_premium else "🆓"
            date_str = created_at.strftime('%d.%m') if hasattr(created_at, 'strftime') else str(created_at)[:10]
            
            message += f"{i}. {premium} {first_name or 'Без имени'} ({username_display}) - {date_str}\n"
        
        message += f"\n<i>Всего пользователей: {len(users)}</i>"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка в show_admin_users: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

async def show_admin_activate_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать форму активации премиума"""
    query = update.callback_query
    
    message = (
        "✅ <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
        "Используйте команду:\n"
        "<code>/admin_activate &lt;user_id&gt; &lt;days&gt;</code>\n\n"
        "Пример: <code>/admin_activate 123456789 30</code>\n\n"
        "<i>Где user_id - Telegram ID пользователя, days - количество дней</i>"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def show_admin_deactivate_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать форму деактивации премиума"""
    query = update.callback_query
    
    message = (
        "❌ <b>ДЕАКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
        "Используйте команду:\n"
        "<code>/admin_deactivate &lt;user_id&gt;</code>\n\n"
        "Пример: <code>/admin_deactivate 123456789</code>\n\n"
        "<i>Где user_id - Telegram ID пользователя</i>"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def show_admin_broadcast_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать форму рассылки"""
    query = update.callback_query
    
    message = (
        "📢 <b>РАССЫЛКА СООБЩЕНИЙ</b>\n\n"
        "Используйте команды:\n\n"
        "• <code>/broadcast &lt;текст сообщения&gt;</code>\n"
        "   - Отправить текстовое сообщение\n\n"
        "• <code>/broadcast_premium &lt;текст&gt;</code>\n"
        "   - Отправить только премиум пользователям\n\n"
        "• <code>/broadcast_test</code>\n"
        "   - Тестовая рассылка (только админу)\n\n"
        "• <code>/broadcast_photo</code>\n"
        "   - Рассылка с фото (ответьте на фото командой)"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, premium_only: bool = False):
    """Выполнить рассылку"""
    query = update.callback_query
    
    message_text = context.user_data.get('broadcast_message', '')
    if not message_text:
        await query.edit_message_text("❌ Сообщение для рассылки не найдено.")
        return
    
    try:
        await query.edit_message_text("🔄 Начинаю рассылку...")
        
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                if premium_only:
                    cursor.execute("SELECT telegram_id FROM users WHERE is_premium = TRUE")
                else:
                    cursor.execute("SELECT telegram_id FROM users")
                
                users = cursor.fetchall()
                
                success = 0
                failed = 0
                
                for (telegram_id,) in users:
                    try:
                        await context.bot.send_message(
                            chat_id=telegram_id,
                            text=f"📢 <b>РАССЫЛКА ОТ АДМИНИСТРАТОРА</b>\n\n{message_text}",
                            parse_mode='HTML'
                        )
                        success += 1
                        # Небольшая задержка чтобы не превысить лимиты Telegram
                        import time
                        time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Ошибка отправки пользователю {telegram_id}: {e}")
                        failed += 1
                
                result_message = (
                    f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
                    f"<b>Аудитория:</b> {'💎 Только премиум' if premium_only else '👥 Все пользователи'}\n"
                    f"<b>Отправлено успешно:</b> {success}\n"
                    f"<b>Не удалось отправить:</b> {failed}\n"
                    f"<b>Всего пользователей:</b> {len(users)}"
                )
                
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(result_message, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await query.edit_message_text("❌ Ошибка подключения к базе данных.")
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        await query.edit_message_text(f"❌ Ошибка при рассылке: {e}")

# ========== КОМАНДЫ ==========

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
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
        "<i>По вопросам обращайтесь к администратору</i>\n"
        "Почта администратора для связи: planexgame@gmail.com",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def list_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list"""
    # Создаем объект callback_query для работы с существующей функцией
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.edit_message_text = message.edit_text
            self.message = message
            self.data = "list"
    
    query = FakeQuery(update.effective_user, update.message)
    update.callback_query = query
    await show_reminders(update, context)

async def premium_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium"""
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.edit_message_text = message.edit_text
            self.message = message
            self.data = "premium_info"
    
    query = FakeQuery(update.effective_user, update.message)
    update.callback_query = query
    await show_premium_info(update, context)

async def buy_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /buy"""
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.edit_message_text = message.edit_text
            self.message = message
            self.data = "premium_info"
    
    query = FakeQuery(update.effective_user, update.message)
    update.callback_query = query
    await show_premium_info(update, context)

async def status_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
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
        logger.error(f"Ошибка статуса: {e}")
        total_users = premium_users = total_reminders = 0
    
    message = (
        f"📊 <b>СТАТУС БОТА</b>\n\n"
        f"✅ <b>Бот работает</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {total_reminders}\n\n"
        f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    await update.message.reply_text(message, parse_mode='HTML')

async def new_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /new"""
    await start_new_reminder(update, context)

async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.edit_message_text = message.edit_text
            self.message = message
            self.data = "admin_panel"
    
    query = FakeQuery(update.effective_user, update.message)
    update.callback_query = query
    await show_admin_panel(update, context)

async def admin_activate_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_activate"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /admin_activate <user_id> <days>\n\n"
            "Пример: /admin_activate 123456789 30"
        )
        return
    
    try:
        user_id_to_activate = int(context.args[0])
        days = int(context.args[1])
        
        # Получаем пользователя по telegram_id
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id_to_activate,))
                result = cursor.fetchone()
                
                if result:
                    internal_user_id = result[0]
                    if db.activate_premium(internal_user_id, days):
                        # Уведомляем пользователя
                        try:
                            await context.bot.send_message(
                                chat_id=user_id_to_activate,
                                text=f"🎉 <b>ВАШ ПРЕМИУМ АКТИВИРОВАН!</b>\n\n"
                                     f"Администратор активировал вам премиум подписку на {days} дней.\n"
                                     f"Теперь у вас есть неограниченные напоминания и расширенные уведомления! 💎",
                                parse_mode='HTML'
                            )
                        except:
                            pass
                        
                        await update.message.reply_text(
                            f"✅ Премиум активирован для пользователя {user_id_to_activate} на {days} дней."
                        )
                    else:
                        await update.message.reply_text("❌ Ошибка активации премиума.")
                else:
                    await update.message.reply_text("❌ Пользователь не найден.")
    except Exception as e:
        logger.error(f"Ошибка в admin_activate: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def admin_deactivate_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_deactivate"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /admin_deactivate <user_id>\n\n"
            "Пример: /admin_deactivate 123456789"
        )
        return
    
    try:
        user_id_to_deactivate = int(context.args[0])
        
        # Получаем пользователя по telegram_id
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id_to_deactivate,))
                result = cursor.fetchone()
                
                if result:
                    internal_user_id = result[0]
                    if db.deactivate_premium(internal_user_id):
                        await update.message.reply_text(
                            f"✅ Премиум деактивирован для пользователя {user_id_to_deactivate}."
                        )
                    else:
                        await update.message.reply_text("❌ Ошибка деактивации премиума.")
                else:
                    await update.message.reply_text("❌ Пользователь не найден.")
    except Exception as e:
        logger.error(f"Ошибка в admin_deactivate: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def broadcast_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /broadcast <сообщение>\n\n"
            "Пример: /broadcast Важное обновление бота!"
        )
        return
    
    message_text = " ".join(context.args)
    
    # Создаем клавиатуру с кнопками для выбора типа рассылки
    keyboard = [
        [
            InlineKeyboardButton("📢 Всем пользователям", callback_data="broadcast_all"),
            InlineKeyboardButton("💎 Только премиум", callback_data="broadcast_premium_only")
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['broadcast_message'] = message_text
    
    await update.message.reply_text(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"<b>Сообщение:</b>\n{message_text}\n\n"
        f"<b>Выберите аудиторию:</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def broadcast_premium_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast_premium - рассылка только премиум пользователям"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /broadcast_premium <сообщение>\n\n"
            "Пример: /broadcast_premium Специальное предложение для премиум пользователей!"
        )
        return
    
    message_text = " ".join(context.args)
    
    keyboard = [
        [
            InlineKeyboardButton("💎 Да, отправить премиум", callback_data="broadcast_premium_only"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['broadcast_message'] = message_text
    
    await update.message.reply_text(
        f"📢 <b>РАССЫЛКА ПРЕМИУМ ПОЛЬЗОВАТЕЛЯМ</b>\n\n"
        f"<b>Сообщение:</b>\n{message_text}\n\n"
        f"<b>Подтвердите отправку:</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def broadcast_test_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast_test - тестовая рассылка только админу"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    message_text = "Тестовое сообщение от бота " + datetime.now().strftime('%d.%m.%Y %H:%M')
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📋 <b>ТЕСТОВАЯ РАССЫЛКА</b>\n\n{message_text}",
            parse_mode='HTML'
        )
        await update.message.reply_text("✅ Тестовое сообщение отправлено вам.")
    except Exception as e:
        logger.error(f"Ошибка тестовой рассылки: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def broadcast_photo_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast_photo - рассылка фото"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "Для рассылки фото:\n"
            "1. Отправьте фото в чат\n"
            "2. Ответьте на фото командой /broadcast_photo\n"
            "3. Добавьте подпись к команде если нужно\n\n"
            "Пример: /broadcast_photo Новое обновление!"
        )
        return
    
    caption = " ".join(context.args) if context.args else ""
    
    keyboard = [
        [
            InlineKeyboardButton("📢 Всем с фото", callback_data="broadcast_all_photo"),
            InlineKeyboardButton("💎 Премиум с фото", callback_data="broadcast_premium_photo")
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Сохраняем информацию о фото
    context.user_data['broadcast_photo'] = update.message.reply_to_message.photo[-1].file_id
    context.user_data['broadcast_caption'] = caption
    
    await update.message.reply_text(
        f"🖼️ <b>РАССЫЛКА ФОТО</b>\n\n"
        f"<b>Подпись:</b> {caption if caption else 'Без подписи'}\n\n"
        f"<b>Выберите аудиторию:</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def test_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test"""
    await update.message.reply_text(
        f"✅ <b>Бот работает</b>\n\n"
        f"Время сервера: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"Ваш ID: {update.effective_user.id}",
        parse_mode='HTML'
    )

async def test_notify_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test_notify - тест уведомления"""
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="🔔 <b>ТЕСТОВОЕ УВЕДОМЛЕНИЕ</b>\n\nЭто тестовое уведомление от бота.",
            parse_mode='HTML'
        )
        await update.message.reply_text("✅ Тестовое уведомление отправлено.")
    except Exception as e:
        logger.error(f"Ошибка тестового уведомления: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def test_admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test_admin"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    await update.message.reply_text(
        f"✅ <b>АДМИН ТЕСТ</b>\n\n"
        f"Ваш ID: {user.id}\n"
        f"Требуемый ADMIN_ID: {ADMIN_ID}\n"
        f"Соответствие: {'✅' if user.id == ADMIN_ID else '❌'}",
        parse_mode='HTML'
    )

async def test_payment_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test_payment"""
    await update.message.reply_text(
        "💳 <b>ТЕСТ ПЛАТЕЖНОЙ СИСТЕМЫ</b>\n\n"
        "Для теста оплаты нажмите кнопки ниже:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1 месяц - 299₽", callback_data="buy_1")],
            [InlineKeyboardButton("3 месяца - 799₽", callback_data="buy_3")],
            [InlineKeyboardButton("12 месяцев - 1990₽", callback_data="buy_12")],
            [InlineKeyboardButton("🎁 Тест 7 дней", callback_data="trial")]
        ]),
        parse_mode='HTML'
    )

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
    app.add_handler(CommandHandler("help", help_command_handler))
    app.add_handler(CommandHandler("list", list_command_handler))
    app.add_handler(CommandHandler("premium", premium_command_handler))
    app.add_handler(CommandHandler("buy", buy_command_handler))
    app.add_handler(CommandHandler("status", status_command_handler))
    app.add_handler(CommandHandler("new", new_command_handler))
    app.add_handler(CommandHandler("admin", admin_command_handler))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command_handler))
    app.add_handler(CommandHandler("admin_deactivate", admin_deactivate_command_handler))
    app.add_handler(CommandHandler("broadcast", broadcast_command_handler))
    app.add_handler(CommandHandler("broadcast_premium", broadcast_premium_command_handler))
    app.add_handler(CommandHandler("broadcast_test", broadcast_test_command_handler))
    app.add_handler(CommandHandler("broadcast_photo", broadcast_photo_command_handler))
    app.add_handler(CommandHandler("test", test_command_handler))
    app.add_handler(CommandHandler("test_notify", test_notify_command_handler))
    app.add_handler(CommandHandler("test_admin", test_admin_command_handler))
    app.add_handler(CommandHandler("test_payment", test_payment_command_handler))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений для создания напоминаний
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
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
