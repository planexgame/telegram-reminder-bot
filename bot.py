# bot.py - минимальный рабочий код
import os
import logging
from datetime import datetime
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

# Почта администратора
ADMIN_EMAIL = "support@nezabudioplatit.ru"

# Константы
FREE_LIMIT = 5

# Состояния для ConversationHandler
TITLE, AMOUNT, DATE = range(3)

# ========== БАЗА ДАННЫХ В ПАМЯТИ ==========
# Простая замена базы данных для тестирования

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
                'premium_until': None
            }
            self.next_user_id += 1
        return self.users[telegram_id]['id']
    
    def get_user_premium_status(self, user_id):
        for user in self.users.values():
            if user['id'] == user_id:
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
        return user_reminders
    
    def add_reminder(self, user_id, title, amount, payment_date, recurrence='once'):
        reminder = {
            'id': self.next_reminder_id,
            'user_id': user_id,
            'title': title,
            'amount': amount,
            'payment_date': payment_date,
            'recurrence': recurrence,
            'is_active': True
        }
        self.reminders.append(reminder)
        self.next_reminder_id += 1
        return reminder['id']
    
    def activate_premium(self, user_id, days):
        for user in self.users.values():
            if user['id'] == user_id:
                user['is_premium'] = True
                if days > 0:
                    from datetime import timedelta
                    user['premium_until'] = datetime.now() + timedelta(days=days)
                return True
        return False

# Создаем экземпляр базы данных
db = SimpleDB()

# ========== КОМАНДА /START ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
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
        amount = rem.get('amount', 0)
        total += float(amount)
        
        message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
        message += f"   💰 {amount}₽ | 📅 {date_str}\n\n"
    
    message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на {total:.2f}₽\n\n"
    message += f"📧 По вопросам: {ADMIN_EMAIL}"
    
    await update.message.reply_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать еще", callback_data="create_reminder")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")],
            [InlineKeyboardButton("🏠 В начало", callback_data="start")]
        ])
    )

# ========== ОБРАБОТЧИК КНОПОК ==========

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
            await premium_info_callback(update, context)
        elif query.data == "list_reminders":
            await list_reminders_callback(update, context)
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
    
    for i, rem in enumerate(reminders[:15], 1):
        date_str = rem.get('payment_date', '')
        amount = rem.get('amount', 0)
        total += float(amount)
        
        message += f"{i}. <b>{rem.get('title', 'Без названия')}</b>\n"
        message += f"   💰 {amount}₽ | 📅 {date_str}\n\n"
    
    message += f"<b>📊 Итого:</b> {len(reminders)} напоминаний на {total:.2f}₽\n\n"
    message += f"📧 По вопросам: {ADMIN_EMAIL}"
    
    await query.edit_message_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать еще", callback_data="create_reminder")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="list_reminders")],
            [InlineKeyboardButton("🏠 В начало", callback_data="start")]
        ])
    )

async def premium_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о премиуме"""
    query = update.callback_query
    
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
        [InlineKeyboardButton("📋 Мои напоминания", callback_data="list_reminders")],
        [InlineKeyboardButton("🏠 В начало", callback_data="start")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

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

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания"""
    await update.message.reply_text("❌ Создание отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# ========== КОМАНДА /STATUS ==========

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    message = (
        f"<b>📊 СТАТУС БОТА</b>\n\n"
        f"<b>🤖 Бот:</b> ✅ работает\n"
        f"<b>💳 Оплата:</b> через почту\n"
        f"<b>📧 Почта админа:</b> {ADMIN_EMAIL}\n"
        f"<b>📅 Лимит бесплатных:</b> {FREE_LIMIT}\n"
        f"<b>🕒 Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"<b>Команды:</b>\n"
        f"✅ /start — главное меню\n"
        f"✅ /new — создать\n"
        f"✅ /list — список\n"
        f"✅ /premium — премиум\n"
        f"✅ /help — помощь\n\n"
        f"<i>Все работает! 🎉</i>"
    )
    
    await update.message.reply_text(message, parse_mode='HTML')

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота"""
    print("=" * 60)
    print("🚀 ЗАПУСК БОТА «НеЗабудьОплатить»")
    print(f"📧 Почта админа: {ADMIN_EMAIL}")
    print("=" * 60)
    
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
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("status", status_command))
    
    app.add_handler(conv_handler)
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(?!create_reminder).*$'))
    
    print("✅ Бот запущен")
    print("=" * 60)
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
