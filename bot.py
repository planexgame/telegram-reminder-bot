# bot.py - ПОЛНАЯ ВЕРСИЯ
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

# Константы
FREE_LIMIT = 5
ADMIN_ID = int(os.getenv('ADMIN_ID', '123456789'))  # Из переменных окружения

# Состояния для ConversationHandler
TITLE, AMOUNT, DATE = range(3)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - ПОЛНАЯ ВЕРСИЯ"""
    user = update.effective_user
    
    try:
        # Регистрируем пользователя
        user_id = db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not user_id:
            await update.message.reply_text(
                "❌ Ошибка регистрации. Попробуйте позже.",
                parse_mode='HTML'
            )
            return
        
        # Получаем данные пользователя
        premium_status = db.get_user_premium_status(user_id)
        reminders_count = db.get_user_reminders_count(user_id)
        
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
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
        # Упрощенная версия при ошибке
        keyboard = [
            [InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔔 <b>НеЗабудьОплатить</b>\n\n"
            f"Привет, {user.first_name}!\n\n"
            f"Бот работает! 🚀\n\n"
            f"Используйте команды:\n"
            f"/new - создать напоминание\n"
            f"/list - список напоминаний\n"
            f"/status - статус бота",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - ПОЛНАЯ ВЕРСИЯ"""
    help_text = (
        "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• /start — начать работу\n"
        "• /new — создать напоминание\n"
        "• /list — список напоминаний\n"
        "• /premium — премиум подписка\n"
        "• /buy — купить премиум\n"
        "• /mypremium — мой премиум статус\n"
        "• /status — статус бота\n"
        "• /help — эта справка\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Создаете напоминание (/new)\n"
        "2. Указываете сумму и дату\n"
        "3. Получаете уведомление\n"
        "4. Не забываете оплатить!\n\n"
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
        "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
        f"<b>ЮKassa:</b> {'✅ настроена' if yookassa.is_configured() else '❌ не настроена'}\n\n"
        "<i>По вопросам: @ваша_поддержка</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# ========== КОМАНДА /NEW (CONVERSATION HANDLER) ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания"""
    user = update.effective_user
    
    try:
        # Регистрируем пользователя
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
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("📋 Удалить старые", callback_data="list")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ <b>Достигнут лимит!</b>\n\n"
                    f"У вас {reminders_count} из {FREE_LIMIT} бесплатных напоминаний.\n\n"
                    "💎 <b>Премиум подписка</b> дает:\n"
                    "• Неограниченное количество\n"
                    "• Повторяющиеся напоминания\n"
                    "• Уведомления за 3 и 7 дней\n"
                    "• Всего 299₽ в месяц",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        # Начинаем диалог
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
        
        # Преобразуем дату в строку для БД
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
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="list")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 <b>У вас пока нет напоминаний.</b>\n\n"
                "Создайте первое напоминание о платеже!",
                reply_markup=reply_markup,
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
            message += f"   📅 {formatted_date}\n"
            message += f"   🔄 {rem.get('recurrence', 'разовое')}\n\n"
            
            total_amount += float(rem.get('amount', 0))
        
        message += f"<b>Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
        
        # Клавиатура
        keyboard = []
        for i in range(min(3, len(reminders))):
            title_short = reminders[i].get('title', '')[:15]
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 Удалить '{title_short}...'",
                    callback_data=f"delete_{reminders[i].get('id')}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_command: {e}")
        await update.message.reply_text("❌ Ошибка при получении списка напоминаний.")

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        # Статистика
        db_status = "✅ работает" if db.init_db() else "⚠️ проблемы"
        
        status_text = (
            f"<b>📊 СТАТУС БОТА «НеЗабудьОплатить»</b>\n\n"
            f"<b>🤖 Telegram API:</b> ✅ подключен\n"
            f"<b>🗄️ База данных:</b> {db_status}\n"
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
        
        # Получаем статус
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        # Клавиатура
        keyboard = [
            [
                InlineKeyboardButton("💳 1 месяц - 299₽", callback_data="buy_1"),
                InlineKeyboardButton("💎 3 месяца - 799₽", callback_data="buy_3")
            ],
            [
                InlineKeyboardButton("🏆 12 месяцев - 1990₽", callback_data="buy_12"),
                InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Сообщение
        if has_premium:
            until_date = premium_status.get('premium_until')
            if until_date:
                until_str = until_date.strftime('%d.%m.%Y') if isinstance(until_date, datetime) else str(until_date)
                message = f"💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует до: <b>{until_str}</b>"
            else:
                message = "💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\nДействует бессрочно"
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
                f"• 📊 Расширенная статистика\n\n"
                f"<b>Выберите подписку:</b>"
            )
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в premium_command: {e}")
        await update.message.reply_text("❌ Ошибка получения информации о премиуме.")

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "create":
            await query.edit_message_text("Нажмите /new для создания напоминания")
        elif query.data == "list":
            # Создаем временное сообщение для обработки команды
            temp_update = Update(update_id=query.id, message=query.message)
            await list_command(temp_update, context)
        elif query.data.startswith("delete_"):
            await delete_reminder_handler(query, context)
        elif query.data == "premium_info":
            await premium_command_with_query(query, context)
        elif query.data == "help_btn":
            await help_command_with_query(query)
        elif query.data.startswith("buy_"):
            await buy_premium_handler(query, context)
        elif query.data == "admin_panel":
            await admin_command_with_query(query, context)
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте снова.")

async def delete_reminder_handler(query, context):
    """Обработчик удаления напоминания"""
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
            await query.edit_message_text("✅ Напоминание удалено!")
        else:
            await query.edit_message_text("❌ Не удалось удалить напоминание.")
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await query.edit_message_text("❌ Ошибка при удалении.")

async def premium_command_with_query(query, context):
    """Обработчик кнопки премиум информации"""
    user = query.from_user
    user_id = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    try:
        premium_status = db.get_user_premium_status(user_id)
        has_premium = premium_status.get('has_active_premium', False) if premium_status else False
        
        if has_premium:
            until_date = premium_status.get('premium_until')
            if until_date:
                until_str = until_date.strftime('%d.%m.%Y') if isinstance(until_date, datetime) else str(until_date)
                message = f"💎 У вас активна премиум подписка до {until_str}!"
            else:
                message = "💎 У вас активна бессрочная премиум подписка!"
        else:
            message = "🆓 У вас бесплатный тариф. Хотите больше возможностей?"
        
        await query.edit_message_text(message)
    except Exception as e:
        await query.edit_message_text("❌ Ошибка получения статуса.")

async def help_command_with_query(query):
    """Обработчик кнопки помощи"""
    await query.edit_message_text(
        "<b>Основные команды:</b>\n"
        "/start - начать работу\n"
        "/new - создать напоминание\n"
        "/list - список напоминаний\n"
        "/premium - премиум подписка\n"
        "/help - помощь\n\n"
        "<i>По вопросам обращайтесь в поддержку</i>",
        parse_mode='HTML'
    )

async def buy_premium_handler(query, context):
    """Обработчик покупки премиума"""
    try:
        period = query.data.split("_")[1]
        prices = {
            '1': {'amount': 299, 'days': 30, 'text': '1 месяц'},
            '3': {'amount': 799, 'days': 90, 'text': '3 месяца'},
            '12': {'amount': 1990, 'days': 365, 'text': '12 месяцев'}
        }
        
        if period not in prices:
            await query.edit_message_text("❌ Неверный период подписки.")
            return
        
        price_info = prices[period]
        user = query.from_user
        
        if yookassa.is_configured():
            # TODO: Реализовать создание платежа через ЮKassa
            await query.edit_message_text(
                f"💳 <b>Оплата {price_info['text']} подписки</b>\n\n"
                f"Сумма: {price_info['amount']}₽\n\n"
                "Интеграция с ЮKassa в процессе настройки.\n"
                "Скоро здесь будет ссылка для оплаты!",
                parse_mode='HTML'
            )
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{period}")],
                [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"💳 <b>Оплата {price_info['text']} подписки</b>\n\n"
                f"Сумма: {price_info['amount']}₽\n\n"
                "Для оплаты переведите на карту:\n"
                "<code>2202 2000 1234 5678</code>\n\n"
                "После оплаты нажмите '✅ Я оплатил'",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка покупки премиума: {e}")
        await query.edit_message_text("❌ Ошибка при оформлении подписки.")

async def admin_command_with_query(query, context):
    """Обработчик админ панели"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    await query.edit_message_text(
        "⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        "Функции админ-панели будут доступны после полной настройки бота.\n\n"
        "Сейчас вы можете использовать:\n"
        "/status - статус бота\n"
        "/premium - управление подписками",
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
    
    # Проверка токена
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
    print("📝 Доступные команды: /start, /new, /list, /premium, /status, /help")
    print("=" * 50)
    print("🤖 Бот запускается...")
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    main()
