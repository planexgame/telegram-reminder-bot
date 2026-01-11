# bot.py
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

# Константы
FREE_LIMIT = 5  # Бесплатных напоминаний
ADMIN_ID = 786588687  # Замените на ваш Telegram ID

# Состояния для ConversationHandler (создание напоминания)
TITLE, AMOUNT, DATE = range(3)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    # Регистрируем/получаем пользователя в БД
    user_id = db.get_or_create_user(
        user.id, 
        user.username, 
        user.first_name, 
        user.last_name
    )
    
    # Получаем статус премиума и количество напоминаний
    premium_status = db.get_user_premium_status(user_id) if user_id else {'has_active_premium': False}
    reminders_count = db.get_user_reminders_count(user_id) if user_id else 0
    
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
    
    # Добавляем кнопку админа если это админ
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем сообщение
    premium_status_text = "💎 АКТИВЕН" if premium_status.get('has_active_premium') else "🆓 БЕСПЛАТНЫЙ"
    
    await update.message.reply_text(
        f"🔔 <b>НеЗабудьОплатить</b>\n\n"
        f"Привет, {user.first_name}!\n\n"
        f"<b>Ваша статистика:</b>\n"
        f"📊 Напоминаний: {reminders_count}/{FREE_LIMIT if not premium_status.get('has_active_premium') else '∞'}\n"
        f"💎 Статус: {premium_status_text}\n\n"
        f"<b>Ваши возможности:</b>\n"
        f"• {'♾️ Неограниченные' if premium_status.get('has_active_premium') else f'До {FREE_LIMIT}'} напоминаний\n"
        f"• 🔔 Уведомления за {'3 и 7 дней' if premium_status.get('has_active_premium') else '1 день'}\n"
        f"• {'🔄 Повторяющиеся платежи' if premium_status.get('has_active_premium') else '📅 Разовые напоминания'}\n\n"
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
        "• /buy — купить премиум\n"
        "• /mypremium — мой премиум статус\n"
        "• /help — эта справка\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Создаете напоминание (/new)\n"
        "2. Указываете сумму и дату\n"
        "3. Получаете уведомление\n"
        "4. Не забываете оплатить!\n\n"
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n"
        "<b>Уведомления:</b> каждый день в 10:00 по Москве\n\n"
        "<i>По вопросам: @your_support</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# ========== КОМАНДА /NEW С ПРОВЕРКОЙ ПРЕМИУМА ==========

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания напоминания"""
    user = update.effective_user
    
    # Регистрируем пользователя
    user_id = db.get_or_create_user(
        user.id, user.username, user.first_name, user.last_name
    )
    
    if not user_id:
        await update.message.reply_text(
            "❌ Ошибка базы данных. Попробуйте позже."
        )
        return ConversationHandler.END
    
    # Проверяем премиум статус
    premium_status = db.get_user_premium_status(user_id)
    has_premium = premium_status.get('has_active_premium', False)
    
    # Если нет премиума, проверяем лимит
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
    
    # Сохраняем user_id в context для использования в следующих шагах
    context.user_data['user_id'] = user_id
    
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем название от пользователя"""
    title = update.message.text.strip()
    
    if len(title) < 2:
        await update.message.reply_text(
            "❌ Название слишком короткое. Введите снова:"
        )
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
    """Получаем сумму от пользователя"""
    try:
        amount_text = update.message.text.replace(',', '.').strip()
        amount = float(amount_text)
        
        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше 0. Введите снова:"
            )
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
        await update.message.reply_text(
            "❌ Неверный формат суммы. Введите число:\n"
            "Например: <i>4500</i>"
        )
        return AMOUNT

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем дату и сохраняем напоминание"""
    date_text = update.message.text.strip()
    
    try:
        # Парсим дату
        day, month, year = map(int, date_text.split('.'))
        payment_date = f"{year:04d}-{month:02d}-{day:02d}"
        
        # Проверяем что дата в будущем
        today = datetime.now().date()
        input_date = datetime(year, month, day).date()
        
        if input_date < today:
            await update.message.reply_text(
                "❌ Дата должна быть в будущем. Введите снова:"
            )
            return DATE
        
    except (ValueError, AttributeError):
        await update.message.reply_text(
            "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:\n"
            "Например: <i>25.01.2024</i>"
        )
        return DATE
    
    # Сохраняем напоминание в БД
    user_id = context.user_data.get('user_id')
    title = context.user_data.get('title')
    amount = context.user_data.get('amount')
    
    if not all([user_id, title, amount]):
        await update.message.reply_text(
            "❌ Ошибка данных. Начните заново с /new"
        )
        return ConversationHandler.END
    
    reminder_id = db.add_reminder(user_id, title, amount, payment_date)
    
    if reminder_id:
        # Форматируем дату для показа пользователю
        formatted_date = f"{day:02d}.{month:02d}.{year}"
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")],
            [InlineKeyboardButton("➕ Еще напоминание", callback_data="create")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ <b>Напоминание создано!</b>\n\n"
            f"<b>Название:</b> {title}\n"
            f"<b>Сумма:</b> {amount}₽\n"
            f"<b>Дата:</b> {formatted_date}\n\n"
            f"Вы получите уведомление за 1 день до платежа (в 10:00 по Москве).",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка сохранения. Попробуйте позже."
        )
    
    # Очищаем временные данные
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания напоминания"""
    await update.message.reply_text("❌ Создание напоминания отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# ========== КОМАНДА /LIST ==========

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список напоминаний пользователя"""
    user = update.effective_user
    
    # Получаем пользователя
    user_id = db.get_or_create_user(
        user.id, user.username, user.first_name, user.last_name
    )
    
    if not user_id:
        await update.message.reply_text(
            "❌ Ошибка базы данных. Попробуйте позже."
        )
        return
    
    # Получаем напоминания
    reminders = db.get_user_reminders(user_id)
    
    if not reminders:
        keyboard = [
            [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
            [InlineKeyboardButton("🔄 Обновить список", callback_data="list")]
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
        payment_date = rem['payment_date']
        if isinstance(payment_date, str):
            # Преобразуем строку в дату
            try:
                date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = payment_date
        else:
            formatted_date = payment_date.strftime('%d.%m.%Y')
        
        message += f"{i}. <b>{rem['title']}</b>\n"
        message += f"   💰 {rem['amount']}₽\n"
        message += f"   📅 {formatted_date}\n"
        message += f"   🔄 {rem['recurrence']}\n\n"
        
        total_amount += float(rem['amount'] or 0)
    
    message += f"<b>Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
    
    # Проверяем премиум статус
    premium_status = db.get_user_premium_status(user_id)
    if premium_status.get('has_active_premium'):
        message += f"<b>Статус:</b> 💎 Премиум (активен до {premium_status['premium_until'].strftime('%d.%m.%Y') if premium_status['premium_until'] else 'бессрочно'})\n"
    else:
        message += f"<b>Статус:</b> 🆓 Бесплатный ({len(reminders)}/{FREE_LIMIT})\n"
    
    # Клавиатура для управления
    keyboard = []
    
    # Кнопки удаления (первые 3 напоминания)
    for i in range(min(3, len(reminders))):
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 Удалить '{reminders[i]['title'][:15]}...'",
                callback_data=f"delete_{reminders[i]['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("➕ Создать еще", callback_data="create"),
        InlineKeyboardButton("🔄 Обновить", callback_data="list")
    ])
    
    # Добавляем кнопку премиума если нет премиума и достигнут/почти достигнут лимит
    if not premium_status.get('has_active_premium') and len(reminders) >= FREE_LIMIT - 1:
        keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - проверка статуса бота"""
    try:
        # Получаем напоминания на завтра
        tomorrow_reminders = db.get_reminders_for_notification(days_before=1)
        
        # Получаем статистику
        with db.get_connection() as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                users_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM reminders WHERE is_active = TRUE")
                active_reminders = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                successful_payments = cursor.fetchone()[0]
            else:
                users_count = 0
                active_reminders = 0
                successful_payments = 0
        
        status_text = (
            f"<b>📊 Статус бота «НеЗабудьОплатить»</b>\n\n"
            f"<b>👥 Пользователи:</b> {users_count}\n"
            f"<b>📝 Активных напоминаний:</b> {active_reminders}\n"
            f"<b>🔔 Уведомлений на завтра:</b> {len(tomorrow_reminders)}\n"
            f"<b>💎 Успешных платежей:</b> {successful_payments}\n"
            f"<b>⏰ Время уведомлений:</b> 10:00 по Москве\n"
            f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
            f"<b>💳 ЮKassa:</b> {'✅ настроена' if yookassa.is_configured() else '❌ не настроена'}\n"
            f"<b>🕒 Серверное время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<i>Бот работает стабильно! ✅</i>"
        )
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка команды status: {e}")
        await update.message.reply_text("❌ Ошибка получения статуса.")

# ========== ПРЕМИУМ КОМАНДЫ ==========

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /premium - информация о премиум подписке"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_id:
        await update.message.reply_text("❌ Ошибка базы данных.")
        return
    
    # Получаем статус премиума
    premium_status = db.get_user_premium_status(user_id)
    
    # Клавиатура с вариантами подписки
    keyboard = [
        [
            InlineKeyboardButton("💳 1 месяц - 299₽", callback_data="buy_1"),
            InlineKeyboardButton("💎 3 месяца - 799₽", callback_data="buy_3")
        ],
        [
            InlineKeyboardButton("🏆 12 месяцев - 1990₽", callback_data="buy_12"),
            InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")
        ],
        [
            InlineKeyboardButton("❓ FAQ", callback_data="premium_faq"),
            InlineKeyboardButton("💬 Поддержка", url="https://t.me/your_support")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем сообщение в зависимости от статуса
    if premium_status['has_active_premium']:
        until_date = premium_status['premium_until'].strftime('%d.%m.%Y') if premium_status['premium_until'] else "бессрочно"
        message = (
            f"💎 <b>У ВАС АКТИВНА ПРЕМИУМ ПОДПИСКА!</b>\n\n"
            f"✅ Действует до: <b>{until_date}</b>\n\n"
            f"<b>Ваши преимущества:</b>\n"
            f"• ♾️ Неограниченные напоминания\n"
            f"• 🔄 Повторяющиеся платежи\n"
            f"• 🔔 Уведомления за 3 и 7 дней\n"
            f"• 📊 Расширенная статистика\n"
            f"• 🚀 Приоритетная поддержка\n\n"
            f"<i>Хотите продлить подписку?</i>"
        )
    else:
        message = (
            f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
            f"<b>Ваш текущий статус:</b> {'Премиум (истек)' if premium_status['is_premium'] else 'Бесплатный'}\n\n"
            f"<b>Бесплатный тариф ограничен:</b>\n"
            f"• 🛑 Всего {FREE_LIMIT} напоминаний\n"
            f"• ⏰ Уведомления только за 1 день\n"
            f"• 🔄 Нет повторяющихся платежей\n\n"
            f"<b>С премиум вы получаете:</b>\n"
            f"• ♾️ Неограниченные напоминания\n"
            f"• 🔄 Повторяющиеся платежи (ежемесячно/ежегодно)\n"
            f"• 🔔 Уведомления за 3 и 7 дней до платежа\n"
            f"• 📊 Расширенная статистика\n"
            f"• 🚀 Приоритетная поддержка\n\n"
            f"<b>Выберите подпику:</b>"
        )
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /buy - покупка премиум подписки"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_id:
        await update.message.reply_text("❌ Ошибка базы данных.")
        return
    
    # Проверяем, не активна ли уже подписка
    premium_status = db.get_user_premium_status(user_id)
    if premium_status['has_active_premium']:
        keyboard = [[InlineKeyboardButton("💎 Мой статус", callback_data="premium_status")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ У вас уже активна премиум подписка!\n\n"
            "Используйте команду /premium чтобы увидеть детали.",
            reply_markup=reply_markup
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
        [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")]
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

async def mypremium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mypremium - информация о моей подписке"""
    user = update.effective_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_id:
        await update.message.reply_text("❌ Ошибка базы данных.")
        return
    
    premium_status = db.get_user_premium_status(user_id)
    
    if premium_status['has_active_premium']:
        until_date = premium_status['premium_until'].strftime('%d.%m.%Y') if premium_status['premium_until'] else "бессрочно"
        
        # Получаем статистику использования
        reminders_count = db.get_user_reminders_count(user_id)
        
        # Получаем историю платежей
        payments = db.get_user_payments(user_id)
        successful_payments = [p for p in payments if p['status'] == 'succeeded']
        
        keyboard = [
            [InlineKeyboardButton("🔄 Продлить", callback_data="premium_info")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"💎 <b>ВАША ПРЕМИУМ ПОДПИСКА</b>\n\n"
            f"<b>Статус:</b> Активна ✅\n"
            f"<b>Действует до:</b> {until_date}\n"
            f"<b>Ваших напоминаний:</b> {reminders_count}\n"
            f"<b>Оплаченных подписок:</b> {len(successful_payments)}\n\n"
            f"<b>Ваши преимущества:</b>\n"
            f"• ♾️ Неограниченные напоминания\n"
            f"• 🔄 Повторяющиеся платежи\n"
            f"• 🔔 Расширенные уведомления\n"
            f"• 🚀 Приоритетная поддержка"
        )
        
        if successful_payments:
            last_payment = successful_payments[0]
            amount = last_payment['amount']
            date = last_payment['completed_at'].strftime('%d.%m.%Y') if last_payment['completed_at'] else "N/A"
            message += f"\n\n<b>Последняя оплата:</b> {amount}₽ ({date})"
        
    else:
        keyboard = [[InlineKeyboardButton("💎 Купить премиум", callback_data="premium_info")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        reminders_count = db.get_user_reminders_count(user_id)
        payments = db.get_user_payments(user_id)
        
        message = (
            f"🆓 <b>У вас бесплатный тариф</b>\n\n"
            f"Использовано напоминаний: {reminders_count}/{FREE_LIMIT}\n"
            f"Попыток оплаты: {len(payments)}\n\n"
            "💎 <b>Премиум даёт:</b>\n"
            "• Неограниченные напоминания\n"
            "• Повторяющиеся платежи\n"
            "• Уведомления за 3 и 7 дней\n"
            "• Приоритетную поддержку\n\n"
            "Всего от 299₽ в месяц!"
        )
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

# ========== АДМИН КОМАНДЫ ==========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin - панель администратора"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    # Получаем статистику
    with db.get_connection() as conn:
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
            premium_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reminders WHERE is_active = TRUE")
            active_reminders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
            successful_payments = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'succeeded'")
            total_revenue = cursor.fetchone()[0] or 0
        else:
            total_users = premium_users = active_reminders = successful_payments = total_revenue = 0
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Активировать премиум", callback_data="admin_activate")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 💎 Премиум: {premium_users}\n"
        f"• 📝 Напоминаний: {active_reminders}\n"
        f"• 💰 Успешных платежей: {successful_payments}\n"
        f"• 🏦 Выручка: {total_revenue:.2f}₽\n\n"
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
                         f"Теперь вам доступны:\n"
                         f"• ♾️ Неограниченные напоминания\n"
                         f"• 🔄 Повторяющиеся платежи\n"
                         f"• 🔔 Уведомления за 3 и 7 дней\n"
                         f"• 🚀 Приоритетная поддержка\n\n"
                         f"Спасибо что пользуетесь нашим ботом! 💎",
                    parse_mode='HTML'
                )
            except:
                pass  # Пользователь мог заблокировать бота
            
            await update.message.reply_text(
                f"✅ Премиум успешно активирован для @{username} на {days} дней."
            )
        else:
            await update.message.reply_text(f"❌ Ошибка активации премиума для @{username}.")

# ========== ТЕСТОВЫЕ КОМАНДЫ ==========

async def test_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки уведомлений (/testnotify)"""
    try:
        await update.message.reply_text("🔔 Тестирую отправку уведомлений...")
        
        # Вызываем функцию уведомлений вручную
        await send_reminder_notifications(context)
        
        await update.message.reply_text("✅ Тестовые уведомления отправлены. Проверьте логи в Render.")
    except Exception as e:
        logger.error(f"Ошибка теста уведомлений: {e}")
        await update.message.reply_text(f"❌ Ошибка отправки уведомлений: {e}")

async def test_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Простая тестовая команда /test"""
    try:
        reminders = db.get_reminders_for_notification(days_before=1)
        
        await update.message.reply_text(
            f"✅ Бот работает!\n"
            f"📊 Напоминаний на завтра: {len(reminders)}\n"
            f"🕒 Время сервера: {datetime.now().strftime('%H:%M:%S')}\n"
            f"💎 ЮKassa настроена: {'✅' if yookassa.is_configured() else '❌'}"
        )
    except Exception as e:
        await update.message.reply_text(f"✅ Бот работает! (Ошибка БД: {e})")

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
            await list_command_with_query(query, context)
            
        elif query.data.startswith("delete_"):
            await delete_reminder_handler(query, context)
            
        elif query.data == "premium_info":
            await premium_command_with_query(query, context)
            
        elif query.data == "premium_status":
            await mypremium_command_with_query(query, context)
            
        elif query.data == "help_btn":
            await help_command_with_query(query)
            
        # Кнопки покупки премиума
        elif query.data.startswith("buy_"):
            await buy_premium_handler(query, context)
            
        elif query.data.startswith("check_payment_"):
            await check_payment_handler(query, context)
            
        elif query.data.startswith("manual_paid_"):
            await manual_paid_handler(query, context)
            
        # Админ кнопки
        elif query.data == "admin_panel":
            await admin_command_with_query(query, context)
            
        elif query.data == "admin_stats":
            await admin_stats_handler(query, context)
            
        elif query.data == "trial":
            await trial_handler(query, context)
            
        elif query.data == "premium_faq":
            await premium_faq_handler(query)
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте снова.")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def list_command_with_query(query, context):
    """Обработчик кнопки списка напоминаний"""
    user = query.from_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_id:
        await query.edit_message_text("❌ Ошибка базы данных.")
        return
    
    reminders = db.get_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text(
            "📭 <b>У вас пока нет напоминаний.</b>\n\n"
            "Создайте первое напоминание с помощью /new",
            parse_mode='HTML'
        )
        return
    
    # Показываем первые 5 напоминаний
    message = "📋 <b>Последние напоминания:</b>\n\n"
    for i, rem in enumerate(reminders[:5], 1):
        payment_date = rem['payment_date']
        if isinstance(payment_date, str):
            try:
                date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = payment_date
        else:
            formatted_date = payment_date.strftime('%d.%m.%Y')
        
        message += f"{i}. <b>{rem['title']}</b>\n"
        message += f"   💰 {rem['amount']}₽\n"
        message += f"   📅 {formatted_date}\n\n"
    
    message += f"<i>Всего напоминаний: {len(reminders)}</i>"
    
    await query.edit_message_text(message, parse_mode='HTML')

async def delete_reminder_handler(query, context):
    """Обработчик удаления напоминания"""
    reminder_id = int(query.data.split("_")[1])
    user = query.from_user
    
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if db.delete_reminder(user_id, reminder_id):
        await query.edit_message_text("✅ Напоминание удалено!")
    else:
        await query.edit_message_text("❌ Не удалось удалить напоминание.")

async def premium_command_with_query(query, context):
    """Обработчик кнопки премиум информации"""
    user = query.from_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    premium_status = db.get_user_premium_status(user_id)
    
    if premium_status['has_active_premium']:
        until_date = premium_status['premium_until'].strftime('%d.%m.%Y') if premium_status['premium_until'] else "бессрочно"
        message = f"💎 У вас активна премиум подписка до {until_date}!"
    else:
        message = "🆓 У вас бесплатный тариф. Хотите больше возможностей?"
    
    await query.edit_message_text(message)

async def mypremium_command_with_query(query, context):
    """Обработчик кнопки статуса премиума"""
    user = query.from_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    premium_status = db.get_user_premium_status(user_id)
    
    if premium_status['has_active_premium']:
        until_date = premium_status['premium_until'].strftime('%d.%m.%Y') if premium_status['premium_until'] else "бессрочно"
        await query.edit_message_text(f"💎 Ваш премиум действует до: {until_date}")
    else:
        await query.edit_message_text("🆓 У вас нет активной премиум подписки.")

async def help_command_with_query(query):
    """Обработчик кнопки помощи"""
    await query.edit_message_text(
        "<b>Основные команды:</b>\n"
        "/start - начать работу\n"
        "/new - создать напоминание\n"
        "/list - список напоминаний\n"
        "/premium - премиум подписка\n"
        "/help - помощь\n\n"
        "<i>По вопросам: @your_support</i>",
        parse_mode='HTML'
    )

async def buy_premium_handler(query, context):
    """Обработчик покупки премиума"""
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
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_id:
        await query.edit_message_text("❌ Ошибка базы данных.")
        return
    
    # Создаем запись о платеже
    payment_id = db.create_payment(user_id, price_info['amount'], price_info['days'])
    
    if not payment_id:
        await query.edit_message_text("❌ Ошибка создания платежа.")
        return
    
    # Если ЮKassa не настроена, показываем реквизиты для ручной оплаты
    if not yookassa.is_configured():
        keyboard = [
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{payment_id}")],
            [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💳 <b>ОПЛАТА ПРЕМИУМ ПОДПИСКИ</b>\n\n"
            f"<b>Подписка:</b> {price_info['text']}\n"
            f"<b>Сумма:</b> {price_info['amount']}₽\n"
            f"<b>ID платежа:</b> {payment_id}\n\n"
            f"<b>Для оплаты:</b>\n"
            f"1. Переведите {price_info['amount']}₽ на карту:\n"
            f"   <code>2202 2000 1234 5678</code>\n"
            f"2. В комментарии укажите: <code>{payment_id}</code>\n"
            f"3. Нажмите кнопку '✅ Я оплатил'\n\n"
            f"Премиум активируется в течение 15 минут после оплаты.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
    
    # Создаем платеж в ЮKassa
    return_url = f"https://t.me/{context.bot.username}?start=payment_success"
    metadata = {
        'user_id': user_id,
        'payment_id': payment_id,
        'period': period,
        'telegram_id': user.id
    }
    
    payment_result = yookassa.create_payment(
        user_id=user_id,
        amount=price_info['amount'],
        description=f"Премиум подписка на {price_info['text']}",
        return_url=return_url,
        metadata=metadata
    )
    
    if payment_result and 'confirmation' in payment_result:
        confirmation_url = payment_result['confirmation']['confirmation_url']
        
        # Сохраняем ID платежа ЮKassa
        db.update_payment_status(payment_id, 'pending', payment_result.get('id'))
        
        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", url=confirmation_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}")],
            [InlineKeyboardButton("↩️ Отмена", callback_data="premium_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💳 <b>ОПЛАТА ПРЕМИУМ ПОДПИСКИ</b>\n\n"
            f"<b>Подпика:</b> {price_info['text']}\n"
            f"<b>Сумма:</b> {price_info['amount']}₽\n"
            f"<b>ID платежа:</b> {payment_id}\n\n"
            f"1. Нажмите кнопку '💳 Перейти к оплате'\n"
            f"2. Оплатите картой\n"
            f"3. Вернитесь в бота\n"
            f"4. Нажмите '✅ Проверить оплату'\n\n"
            f"Премиум активируется автоматически после успешной оплаты.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ Ошибка создания платежа. Попробуйте позже.")

async def check_payment_handler(query, context):
    """Проверка статуса платежа"""
    payment_id = int(query.data.split("_")[2])
    
    # Получаем payment из БД
    payment_info = db.get_payment_info(payment_id)
    
    if not payment_info:
        await query.edit_message_text("❌ Платеж не найден.")
        return
    
    if payment_info['status'] == 'succeeded':
        await query.edit_message_text(
            "✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b>\n\n"
            "Ваша премиум подписка активирована!\n\n"
            "Теперь вам доступны:\n"
            "• ♾️ Неограниченные напоминания\n"
            "• 🔄 Повторяющиеся платежи\n"
            "• 🔔 Уведомления за 3 и 7 дней\n"
            "• 🚀 Приоритетная поддержка\n\n"
            "Спасибо за покупку! 💎",
            parse_mode='HTML'
        )
        return
    
    # Проверяем статус в ЮKassa если есть ID
    if payment_info['yookassa_payment_id'] and yookassa.is_configured():
        payment_data = yookassa.get_payment_status(payment_info['yookassa_payment_id'])
        
        if payment_data and payment_data.get('status') == 'succeeded':
            db.update_payment_status(payment_id, 'succeeded', payment_info['yookassa_payment_id'])
            
            await query.edit_message_text(
                "✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b>\n\n"
                "Ваша премиум подписка активирована!",
                parse_mode='HTML'
            )
            return
    
    keyboard = [[InlineKeyboardButton("🔄 Проверить снова", callback_data=query.data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⏳ <b>Ожидание оплаты...</b>\n\n"
        "Если вы уже оплатили, подождите 1-2 минуты и проверьте снова.\n"
        "Платеж может обрабатываться банком.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def manual_paid_handler(query, context):
    """Ручное подтверждение оплаты"""
    payment_id = int(query.data.split("_")[2])
    
    keyboard = [[InlineKeyboardButton("💎 Мой статус", callback_data="premium_status")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ <b>Спасибо за оплату!</b>\n\n"
        "Ваш платеж получен и будет проверен вручную.\n"
        "Премиум подписка будет активирована в течение 15 минут.\n\n"
        "Вы получите уведомление, когда подписка будет активирована.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def admin_command_with_query(query, context):
    """Обработчик админ панели"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    await admin_command(Update(update_id=query.id, message=query.message), context)

async def admin_stats_handler(query, context):
    """Обработчик статистики админа"""
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    # Здесь можно добавить подробную статистику
    await query.edit_message_text("📊 Подробная статистика будет здесь.")

async def trial_handler(query, context):
    """Обработчик тестового периода"""
    user = query.from_user
    user_id = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    # Активируем тестовый премиум на 7 дней
    if db.activate_premium(user_id, 7):
        await query.edit_message_text(
            "🎉 <b>Тестовый премиум активирован!</b>\n\n"
            "Вам доступны все функции премиума на 7 дней:\n\n"
            "• ♾️ Неограниченные напоминания\n"
            "• 🔄 Повторяющиеся платежи\n"
            "• 🔔 Уведомления за 3 и 7 дней\n"
            "• 🚀 Приоритетная поддержка\n\n"
            "Наслаждайтесь! Если понравится - сможете оформить полную подписку. 💎",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ Ошибка активации тестового периода.")

async def premium_faq_handler(query):
    """Обработчик FAQ премиума"""
    faq_text = (
        "<b>💎 ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ</b>\n\n"
        "<b>1. Что дает премиум подписка?</b>\n"
        "• Неограниченное количество напоминаний\n"
        "• Повторяющиеся платежи (ежемесячно/ежегодно)\n"
        "• Уведомления за 3 и 7 дней до платежа\n"
        "• Приоритетная поддержка\n\n"
        "<b>2. Как происходит оплата?</b>\n"
        "Оплата через безопасную платежную систему ЮKassa.\n"
        "Принимаются карты РФ и зарубежные карты.\n\n"
        "<b>3. Можно ли отменить подпику?</b>\n"
        "Подписка действует до конца оплаченного периода.\n"
        "Автопродление не включено.\n\n"
        "<b>4. Что если я передумаю?</b>\n"
        "Вы можете пользоваться премиумом до конца оплаченного периода.\n"
        "Возврат средств не предусмотрен.\n\n"
        "<b>5. Есть ли тестовый период?</b>\n"
        "Да, 7 дней теста доступны по кнопке '🎁 Тест 7 дней'.\n\n"
        "<i>Остались вопросы? Пишите: @your_support</i>"
    )
    
    await query.edit_message_text(faq_text, parse_mode='HTML')

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
    if not TOKEN:
        logger.error("❌ Токен не найден!")
        return
    
    logger.info("🚀 Запуск бота «НеЗабудьОплатить»...")
    
    # Инициализируем базу данных
    if db.init_db():
        logger.info("✅ База данных инициализирована")
    else:
        logger.warning("⚠️ База данных не подключена")
    
    # Проверяем настройку ЮKassa
    if yookassa.is_configured():
        logger.info("✅ ЮKassa настроена")
    else:
        logger.warning("⚠️ ЮKassa не настроена, будут доступны только ручные платежи")
    
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
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("mypremium", mypremium_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    app.add_handler(CommandHandler("testnotify", test_notify))
    # ДОБАВЛЕНО: обработчик для команды /status
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("test", test_simple))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Настраиваем планировщик уведомлений
    job_queue = app.job_queue
    if job_queue:
        # Отправляем уведомления каждый день в 10:00 по Москве
        # 10:00 MSK = 7:00 UTC
        job_queue.run_daily(
            send_reminder_notifications,
            time=time(hour=7, minute=0),  # 10:00 по Москве
            days=(0, 1, 2, 3, 4, 5, 6),  # Все дни недели
            name="daily_reminders"
        )
        logger.info("📅 Планировщик уведомлений настроен (каждый день в 10:00 МСК)")
    else:
        logger.warning("⚠️ JobQueue не доступен, уведомления отключены")
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    logger.info("✅ Бот запущен и готов к работе!")
    logger.info("📝 Доступные команды: /start, /new, /list, /premium, /buy, /mypremium, /admin, /status, /test")
    app.run_polling()

if __name__ == "__main__":
    main()
