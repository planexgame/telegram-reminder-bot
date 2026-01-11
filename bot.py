# bot.py
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

# Импортируем нашу базу данных
from database import db

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

# Состояния для ConversationHandler (создание напоминания)
TITLE, AMOUNT, DATE = range(3)

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
    
    # Получаем количество напоминаний пользователя
    reminders_count = db.get_user_reminders_count(user_id) if user_id else 0
    
    keyboard = [
        [
            InlineKeyboardButton("➕ Создать напоминание", callback_data="create"),
            InlineKeyboardButton("📋 Мои напоминания", callback_data="list")
        ],
        [
            InlineKeyboardButton("💎 Премиум", callback_data="premium"),
            InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔔 <b>НеЗабудьОплатить</b>\n\n"
        f"Привет, {user.first_name}!\n\n"
        f"<b>Ваша статистика:</b>\n"
        f"📊 Напоминаний: {reminders_count}/{FREE_LIMIT}\n\n"
        f"<b>🎯 Бесплатные функции:</b>\n"
        f"• До {FREE_LIMIT} напоминаний\n"
        f"• Уведомления за день\n\n"
        f"<b>💎 Премиум (299₽/мес):</b>\n"
        f"• Неограниченные напоминания\n"
        f"• Повторяющиеся платежи\n\n"
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
        "• /delete — удалить напоминание\n"
        "• /premium — премиум подписка\n"
        "• /help — эта справка\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Создаете напоминание (/new)\n"
        "2. Указываете сумму и дату\n"
        "3. Получаете уведомление\n"
        "4. Не забываете оплатить!\n\n"
        f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний\n\n"
        "<i>По вопросам: @your_support</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# ========== КОМАНДА /NEW ==========
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
    
    # Проверяем лимит напоминаний
    reminders_count = db.get_user_reminders_count(user_id)
    
    if reminders_count >= FREE_LIMIT:
        keyboard = [
            [InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")],
            [InlineKeyboardButton("📋 Удалить старые", callback_data="delete_old")]
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
            date_parts = payment_date.split('-')
            formatted_date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
        else:
            formatted_date = str(payment_date)
        
        message += f"{i}. <b>{rem['title']}</b>\n"
        message += f"   💰 {rem['amount']}₽\n"
        message += f"   📅 {formatted_date}\n"
        message += f"   🔄 {rem['recurrence']}\n\n"
        
        total_amount += float(rem['amount'] or 0)
    
    message += f"<b>Итого:</b> {len(reminders)} напоминаний на сумму {total_amount:.2f}₽\n"
    message += f"<b>Лимит:</b> {len(reminders)}/{FREE_LIMIT}"
    
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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "create":
            # Просто отправляем команду /new
            await query.edit_message_text(
                "Нажмите /new для создания напоминания",
                parse_mode='HTML'
            )
            
        elif query.data == "list":
            # Получаем список напоминаний
            user = query.from_user
            user_id = db.get_or_create_user(
                user.id, user.username, user.first_name, user.last_name
            )
            
            if not user_id:
                await query.edit_message_text(
                    "❌ Ошибка базы данных.",
                    parse_mode='HTML'
                )
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
                message += f"{i}. <b>{rem['title']}</b>\n"
                message += f"   💰 {rem['amount']}₽\n"
                message += f"   📅 {rem['payment_date']}\n\n"
            
            await query.edit_message_text(
                message,
                parse_mode='HTML'
            )
            
        elif query.data.startswith("delete_"):
            # Удаление напоминания
            reminder_id = int(query.data.split("_")[1])
            user = query.from_user
            
            user_id = db.get_or_create_user(
                user.id, user.username, user.first_name, user.last_name
            )
            
            if db.delete_reminder(user_id, reminder_id):
                await query.edit_message_text(
                    "✅ Напоминание удалено!",
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text(
                    "❌ Не удалось удалить напоминание.",
                    parse_mode='HTML'
                )
                
        elif query.data == "premium":
            await query.edit_message_text(
                "💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n\n"
                "<b>299₽ в месяц</b>\n\n"
                "✅ <b>Включено:</b>\n"
                "• Неограниченные напоминания\n"
                "• Повторяющиеся платежи\n"
                "• Уведомления за 3 и 7 дней\n"
                "• Категории и теги\n"
                "• Приоритетная поддержка\n\n"
                "Скоро будет доступно для покупки!",
                parse_mode='HTML'
            )
            
        elif query.data == "help_btn":
            await query.edit_message_text(
                "<b>🔔 НеЗабудьОплатить — помощь</b>\n\n"
                "<b>Основные команды:</b>\n"
                "• /start — начать работу\n"
                "• /new — создать напоминание\n"
                "• /list — список напоминаний\n"
                "• /help — эта справка\n\n"
                f"<b>Бесплатный лимит:</b> {FREE_LIMIT} напоминаний",
                parse_mode='HTML'
            )
            
        elif query.data == "buy_premium":
            await query.edit_message_text(
                "💳 <b>Премиум подписка — 299₽/мес</b>\n\n"
                "Оплата будет доступна в ближайшее время.\n\n"
                "Следите за обновлениями!",
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте снова.")

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
    
    logger.info("🚀 Запуск бота...")
    
    # Инициализируем базу данных
    db.init_db()
    
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
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    logger.info("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
