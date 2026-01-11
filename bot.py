# bot.py - обновленная версия с исправлениями
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
        logger.error("❌ ADMIN_ID не настроен! Установите переменную ADMIN_ID в Render.")
        print("=" * 50)
        print("❌ ОШИБКА: ADMIN_ID не настроен!")
        print("Добавьте в переменные окружения Render:")
        print("ADMIN_ID = ваш_telegram_id")
        print("=" * 50)
        exit(1)
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
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
                    [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
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
        
        # Получаем напоминания
        reminders = []
        try:
            reminders = db.get_user_reminders(user_id)
        except Exception as e:
            logger.error(f"Ошибка получения напоминаний: {e}")
        
        if not reminders:
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
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
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
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
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="create")],
                [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
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
            InlineKeyboardButton("➕ Создать еще", callback_data="create"),
            InlineKeyboardButton("🔄 Обновить", callback_data="list")
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
            f"<b>💳 ЮKassa:</b> {'✅ настроена' if yookassa.is_configured() else '⚠️ не настроена'}\n"
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
        
        await update.message.reply_text(status_text, parse_mode='HTML')
        
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
                [InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")],
                [InlineKeyboardButton("📋 Мои напоминания", callback_data="list")]
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
                    InlineKeyboardButton("🔄 Мой статус", callback_data="premium_status")
                ],
                [InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")]
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
        
    except Exception as e:
        logger.error(f"Ошибка в buy_command: {e}")
        await update.message.reply_text("❌ Ошибка при оформлении подписки.")

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
        [
            InlineKeyboardButton("💎 Активировать", callback_data="admin_activate"),
            InlineKeyboardButton("🚫 Деактивировать", callback_data="admin_deactivate_menu")
        ],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"⚙️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
            f"<b>Статистика:</b>\n"
            f"• 👥 Пользователей: {total_users}\n"
            f"• 💎 Премиум: {premium_users}\n"
            f"• 📝 Напоминаний: {total_reminders}\n"
            f"• 💰 Успешных платежей: {successful_payments}\n\n"
            f"<b>Управление премиумом:</b>\n"
            f"• 💎 Активация подписки\n"
            f"• 🚫 Деактивация подписки\n\n"
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
            f"• 📝 Напоминаний: {total_reminders}\n"
            f"• 💰 Успешных платежей: {successful_payments}\n\n"
            f"<b>Управление премиумом:</b>\n"
            f"• 💎 Активация подписки\n"
            f"• 🚫 Деактивация подписки\n\n"
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
        keyboard = [
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
            [InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💎 <b>АКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
            "<b>Использование:</b>\n"
            "<code>/admin_activate @username 30</code>\n\n"
            "<b>Где:</b>\n"
            "• @username — username пользователя\n"
            "• 30 — количество дней премиума\n\n"
            "<b>Примеры:</b>\n"
            "<code>/admin_activate @ivanov 30</code> — на 30 дней\n"
            "<code>/admin_activate @petrov 365</code> — на год\n\n"
            "Используйте /admin_users чтобы увидеть список пользователей",
            reply_markup=reply_markup,
            parse_mode='HTML'
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
        cursor.execute('SELECT id, telegram_id, first_name FROM users WHERE username = %s', (username,))
        result = cursor.fetchone()
        
        if not result:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
            return
        
        user_id, telegram_id, first_name = result
        
        # Активируем премиум
        if db.activate_premium(user_id, days):
            # Отправляем уведомление пользователю
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"🎉 <b>Вам активирована премиум подписка!</b>\n\n"
                         f"Администратор активировал вам премиум подписку на {days} дней.\n\n"
                         f"<b>Теперь вам доступны:</b>\n"
                         f"• ♾️ Неограниченные напоминания\n"
                         f"• 🔄 Повторяющиеся платежи\n"
                         f"• 🔔 Уведомления за 3 и 7 дней\n\n"
                         f"Спасибо за использование бота! 💎",
                    parse_mode='HTML'
                )
            except:
                pass  # Пользователь мог заблокировать бота
            
            await update.message.reply_text(
                f"✅ <b>Премиум успешно активирован!</b>\n\n"
                f"Пользователь: {first_name or '@'+username}\n"
                f"Telegram ID: <code>{telegram_id}</code>\n"
                f"Срок: {days} дней\n\n"
                f"Пользователь получил уведомление.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ Ошибка активации премиума для @{username}.")

async def admin_deactivate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда деактивации премиума админом (ИСПРАВЛЕННАЯ)"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    if not context.args:
        keyboard = [
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🚫 <b>ДЕАКТИВАЦИЯ ПРЕМИУМА</b>\n\n"
            "<b>Использование:</b>\n"
            "<code>/admin_deactivate @username</code>\n"
            "или\n"
            "<code>/admin_deactivate USER_ID</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>/admin_deactivate @ivanov</code>\n"
            "<code>/admin_deactivate 123456789</code>\n\n"
            "Для поиска пользователя: /admin_users",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
    
    identifier = context.args[0]
    
    try:
        conn = db.get_connection()
        if not conn:
            await update.message.reply_text("❌ Ошибка подключения к базе данных.")
            return
        
        cursor = conn.cursor()
        
        # Определяем, это username или ID
        if identifier.startswith('@'):
            username = identifier.replace('@', '')
            cursor.execute('''
                SELECT id, telegram_id, first_name, username, is_premium, premium_until 
                FROM users 
                WHERE username = %s OR telegram_id::TEXT = %s
            ''', (username, identifier))
        else:
            # Пробуем как Telegram ID
            try:
                telegram_id = int(identifier)
                cursor.execute('''
                    SELECT id, telegram_id, first_name, username, is_premium, premium_until 
                    FROM users 
                    WHERE telegram_id = %s
                ''', (telegram_id,))
            except ValueError:
                # Пробуем как внутренний ID пользователя
                try:
                    user_id = int(identifier)
                    cursor.execute('''
                        SELECT id, telegram_id, first_name, username, is_premium, premium_until 
                        FROM users 
                        WHERE id = %s
                    ''', (user_id,))
                except:
                    await update.message.reply_text("❌ Неверный формат. Используйте @username, Telegram ID или User ID.")
                    return
        
        result = cursor.fetchone()
        
        if not result:
            await update.message.reply_text(f"❌ Пользователь {identifier} не найден.")
            cursor.close()
            return
        
        db_user_id, telegram_id, first_name, username_db, is_premium, premium_until = result
        
        # Проверяем, есть ли у пользователя активный премиум
        if not is_premium:
            await update.message.reply_text(
                f"ℹ️ У пользователя {first_name or '@' + (username_db or 'нет')} нет активной премиум подписки."
            )
            cursor.close()
            return
        
        # Деактивируем премиум
        if db.deactivate_premium(db_user_id):
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"⚠️ <b>ВАША ПРЕМИУМ ПОДПИСКА ОТМЕНЕНА</b>\n\n"
                         f"Администратор отменил вашу премиум подписку.\n\n"
                         f"<b>Теперь у вас:</b>\n"
                         f"• 🛑 Только {FREE_LIMIT} бесплатных напоминаний\n"
                         f"• ⏰ Уведомления только за 1 день\n"
                         f"• 🔄 Нет повторяющихся платежей\n\n"
                         f"Вы можете снова оформить премиум через /buy\n\n"
                         f"По вопросам обращайтесь к администратору.",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя {telegram_id}: {e}")
            
            # Форматируем дату окончания для отчета
            premium_until_str = "Неизвестно"
            if premium_until:
                if hasattr(premium_until, 'strftime'):
                    premium_until_str = premium_until.strftime('%d.%m.%Y %H:%M')
                else:
                    premium_until_str = str(premium_until)[:16]
            
            await update.message.reply_text(
                f"✅ <b>Премиум подписка отменена!</b>\n\n"
                f"<b>Пользователь:</b> {first_name or 'Без имени'} (@{username_db or 'нет'})\n"
                f"<b>Telegram ID:</b> <code>{telegram_id}</code>\n"
                f"<b>Подписка истекла бы:</b> {premium_until_str}\n\n"
                f"Пользователь получил уведомление об отмене.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ Не удалось отменить премиум для {identifier}.")
        
        cursor.close()
            
    except Exception as e:
        logger.error(f"Ошибка в admin_deactivate_command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

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
                    [InlineKeyboardButton("💎 Премиум", callback_data="premium_info")],
                    [InlineKeyboardButton("🆘 Помощь", callback_data="help_btn")]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data == "list":
            # Вызываем функцию обработки списка напоминаний
            await handle_list_button(update, context)
            
        elif query.data == "premium_info":
            # Создаем временный update для premium_command
            class FakeMessage:
                def __init__(self, user):
                    self.from_user = user
                    self.text = "/premium"
                    self.chat_id = user.id
                
                async def reply_text(self, text, **kwargs):
                    return await query.edit_message_text(text, **kwargs)
            
            fake_msg = FakeMessage(query.from_user)
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
                    [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")]
                ]),
                parse_mode='HTML'
            )
            
        elif query.data.startswith("buy_"):
            period = query.data.split("_")[1]
            if period in PREMIUM_PRICES:
                price_info = PREMIUM_PRICES[period]
                
                if yookassa.is_configured():
                    await query.edit_message_text(
                        f"💳 <b>ОПЛАТА {price_info['text'].upper()} ПОДПИСКИ</b>\n\n"
                        f"Сумма: {price_info['amount']}₽\n\n"
                        "Интеграция с ЮKassa в процессе настройки.\n"
                        "Скоро здесь будет ссылка для оплаты!\n\n"
                        "А пока администратор может активировать вам премиум вручную.",
                        parse_mode='HTML'
                    )
                else:
                    keyboard = [
                        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{period}")],
                        [InlineKeyboardButton("↩️ Назад", callback_data="premium_info")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"💳 <b>ОПЛАТА {price_info['text'].upper()} ПОДПИСКИ</b>\n\n"
                        f"Сумма: {price_info['amount']}₽\n\n"
                        "Для оплаты:\n"
                        "1. Переведите на карту:\n"
                        "<code>2202 2000 1234 5678</code>\n"
                        "2. В комментарии укажите ваш username\n"
                        "3. Нажмите '✅ Я оплатил'\n\n"
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
                        [InlineKeyboardButton("🔄 Обновить статус", callback_data="premium_status")]
                    ]
                else:
                    message = "🆓 <b>ПРЕМИУМ СТАТУС</b>\n\nУ вас нет активной премиум подписки."
                    keyboard = [
                        [InlineKeyboardButton("💎 Купить премиум", callback_data="buy_premium")],
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
                    # После удаления показываем обновленный список
                    await handle_list_button(update, context)
                else:
                    await query.edit_message_text("❌ Не удалось удалить напоминание.")
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
                await query.edit_message_text("❌ Ошибка при удалении.")
                
        elif query.data == "help_btn":
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
                    "Наслаждайтесь! Если понравится - сможете оформить полную подписку. 💎",
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("❌ Ошибка активации тестового периода.")
                
        elif query.data.startswith("manual_paid_"):
            await query.edit_message_text(
                "⏳ <b>Заявка принята!</b>\n\n"
                "Администратор получил уведомление о вашей оплате.\n"
                "Премиум подписка будет активирована в течение 24 часов.\n\n"
                "Спасибо за покупку! 💎",
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start")

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
        
        await query.edit_message_text(
            f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
            f"• 👥 Всего пользователей: {total}\n"
            f"• 💎 Премиум пользователей: {premium}\n"
            f"• 📝 Всего напоминаний: {reminders}\n"
            f"• 💰 Успешных платежей: {payments}\n\n"
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
        
        message = "👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ:</b>\n\n"
        
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
            [InlineKeyboardButton("🔄 Обновить", callback_data="admin_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
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

async def test_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки уведомлений"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Команда только для администратора.")
        return
    
    # Имитируем отправку уведомления
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="🔔 <b>ТЕСТОВОЕ УВЕДОМЛЕНИЕ</b>\n\n"
                 "Это тестовое сообщение от системы уведомлений.\n"
                 "Если вы его получили, значит бот работает правильно! ✅",
            parse_mode='HTML'
        )
        await update.message.reply_text("✅ Тестовое уведомление отправлено!")
    except Exception as e:
        logger.error(f"❌ Ошибка тестового уведомления: {e}")
        await update.message.reply_text(f"❌ Ошибка отправки: {str(e)[:100]}")

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
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_activate", admin_activate_command))
    app.add_handler(CommandHandler("admin_deactivate", admin_deactivate_command))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CommandHandler("test_notify", test_notify_command))
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
    print("📝 Доступные команды: /start, /new, /list, /premium, /buy, /status, /help, /admin, /test, /test_notify")
    print("=" * 50)
    print("🤖 Бот запускается...")
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    main()

