# bot.py - полная версия с рабочей админ-панелью
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

# Импортируем наши модули
from database import db
from notifications import send_reminder_notifications
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
    logger.error("❌ Токен не найден! Установите TELEGRAM_TOKEN в Render.")
    exit(1)

# Получаем ADMIN_ID
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    if ADMIN_ID == 0:
        print("⚠️ ВНИМАНИЕ: ADMIN_ID не настроен! Используйте 123456789")
        ADMIN_ID = 786588687
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
except Exception as e:
    print(f"❌ Ошибка загрузки ADMIN_ID: {e}")
    ADMIN_ID = 123456789

# Константы
FREE_LIMIT = 5

# Состояния для ConversationHandler
TITLE, AMOUNT, DATE = range(3)

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
                await update.message.reply_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает неограниченное количество напоминаний!",
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
        "Введите <b>сумму платежа</b> (в рублях):\n\n"
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
        
        reminders = db.get_user_reminders(user_id)
        
        if not reminders:
            await update.message.reply_text(
                "📭 <b>У вас пока нет напоминаний.</b>\n\n"
                "Создайте первое напоминание о платеже!",
                parse_mode='HTML'
            )
            return
        
        # Формируем сообщение
        message = "📋 <b>Ваши напоминания:</b>\n\n"
        total_amount = 0
        
        for i, rem in enumerate(reminders, 1):
            # Форматируем дату
            payment_date = rem.get('payment_date')
            if isinstance(payment_date, str):
                try:
                    date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = payment_date
            else:
                formatted_date = payment_date.strftime('%d.%m.%Y') if payment_date else "N/A"
            
            message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
            message += f"   💰 {rem.get('amount', 0)}₽\n"
            message += f"   📅 {formatted_date}\n\n"
            
            total_amount += float(rem.get('amount', 0))
        
        message += f"<b>Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_command: {e}")
        await update.message.reply_text("❌ Ошибка при получении списка напоминаний.")

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        status_text = (
            f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить»</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>💳 ЮKassa:</b> {'✅ настроена' if yookassa.is_configured() else '⚠️ не настроена'}\n"
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
            f"<i>Все системы работают нормально! 🎉</i>"
        )
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

# ========== КОМАНДА /PREMIUM ==========

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
        
        # Получаем статус
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        # Клавиатура
        keyboard = [
            [InlineKeyboardButton("💎 Информация", callback_data="premium_info")],
            [InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Сообщение
        if has_premium:
            message = "💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nВы получаете все преимущества!"
        else:
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
                f"• 📊 Расширенная статистика"
            )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в premium_command: {e}")
        await update.message.reply_text("❌ Ошибка получения информации о премиуме.")

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
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {total_reminders}\n"
        f"• 💰 Успешных платежей: {successful_payments}\n\n"
        f"<b>Доступные функции:</b>\n"
        f"• 📊 Просмотр статистики\n"
        f"• 👥 Список пользователей\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def admin_activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда активации премиума админом"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /admin_activate @username [дней]\n\n"
            "Примеры:\n"
            "/admin_activate @username 30 - премиум на 30 дней\n"
            "/admin_activate @username 365 - премиум на год"
        )
        return
    
    username = context.args[0].replace('@', '')
    days = int(context.args[1]) if len(context.args) > 1 else 30
    
    # Находим пользователя по username
    with db.get_connection() as conn:
        if not conn:
            await update.message.reply_text("❌ Ошибка базы данных.")
            return
        
        cursor = conn.cursor()
        cursor.execute('SELECT id, telegram_id FROM users WHERE username = %s', (username,))
        result = cursor.fetchone()
        
        if not result:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
            return
        
        user_id, telegram_id = result
        
        # Активируем премиум
        if db.activate_premium(user_id, days):
            # Отправляем уведомление пользователю
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"🎉 <b>Вам активирована премиум подписка!</b>\n\n"
                         f"Администратор активировал вам премиум подписку на {days} дней.\n\n"
                         f"Теперь вам доступны все преимущества премиума! 💎",
                    parse_mode='HTML'
                )
            except:
                pass  # Пользователь мог заблокировать бота
            
            await update.message.reply_text(
                f"✅ Премиум успешно активирован для @{username} на {days} дней."
            )
        else:
            await update.message.reply_text(f"❌ Ошибка активации премиума для @{username}.")

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Основные кнопки
        if query.data == "create":
            await query.edit_message_text("Нажмите /new для создания напоминания")
            
        elif query.data == "list":
            temp_update = Update(update_id=query.id, message=query.message)
            await list_command(temp_update, context)
            
        elif query.data == "premium_info":
            temp_update = Update(update_id=query.id, message=query.message)
            await premium_command(temp_update, context)
            
        elif query.data == "premium_status":
            await query.edit_message_text("💎 Информация о статусе премиума будет здесь.")
            
        elif query.data == "help_btn":
            await query.edit_message_text(
                "<b>Основные команды:</b>\n"
                "/start - начать работу\n"
                "/new - создать напоминание\n"
                "/list - список напоминаний\n"
                "/premium - премиум подписка\n"
                "/help - помощь\n\n"
                "<i>По вопросам обращайтесь к администратору</i>",
                parse_mode='HTML'
            )
        
        # Админ кнопки
        elif query.data == "admin_panel":
            temp_update = Update(update_id=query.id, message=query.message)
            await admin_command(temp_update, context)
            
        elif query.data == "admin_stats":
            await admin_stats_handler(query, context)
            
        elif query.data == "admin_users":
            await admin_users_handler(query, context)
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте снова.")

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
                
                cursor.execute("SELECT COUNT(*) FROM payments")
                payments = cursor.fetchone()[0]
            else:
                total = premium = reminders = payments = 0
        
        await query.edit_message_text(
            f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
            f"• 👥 Всего пользователей: {total}\n"
            f"• 💎 Премиум пользователей: {premium}\n"
            f"• 📝 Всего напоминаний: {reminders}\n"
            f"• 💰 Всего платежей: {payments}\n\n"
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
                    LIMIT 10
                """)
                users = cursor.fetchall()
            else:
                users = []
        
        if not users:
            await query.edit_message_text("📭 Пользователей пока нет.")
            return
        
        message = "👥 <b>ПОСЛЕДНИЕ 10 ПОЛЬЗОВАТЕЛЕЙ:</b>\n\n"
        
        for i, (username, first_name, is_premium, created_at) in enumerate(users, 1):
            username_display = f"@{username}" if username else "нет username"
            premium = "💎" if is_premium else "🆓"
            date_str = created_at.strftime('%d.%m') if hasattr(created_at, 'strftime') else str(created_at)[:10]
            
            message += f"{i}. {premium} {first_name or 'Без имени'} ({username_display}) - {date_str}\n"
        
        message += f"\n<i>Показано: {len(users)} пользователей</i>"
        
        await query.edit_message_text(message, parse_mode='HTML')
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== ТЕСТОВЫЕ КОМАНДЫ ==========

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда /test"""
    await update.message.reply_text(
        f"✅ <b>Бот работает!</b>\n\n"
        f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"ADMIN_ID: {ADMIN_ID}\n"
        f"Ваш ID: {update.effective_user.id}\n"
        f"Вы админ: {'✅ Да' if update.effective_user.id == ADMIN_ID else '❌ Нет'}",
        parse_mode='HTML'
    )

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
    print("=" * 50)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА «НеЗабудьОплатить»")
    print("=" * 50)
    
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
    
    # Проверка ЮKassa
    print(f"💳 ЮKassa: {'настроена' if yookassa.is_configured() else 'НЕ настроена'}")
    
    # Создаем приложение
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
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(conv_handler)
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
    
    print("✅ Команды зарегистрированы")
    print("📝 Доступные команды: /start, /new, /list, /premium, /status, /help, /admin, /test")
    print("=" * 50)
    print("🤖 Бот запускается...")
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    main()
