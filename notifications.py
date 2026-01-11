# notifications.py
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

async def send_reminder_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Отправка уведомлений о предстоящих платежах"""
    try:
        logger.info("🔔 Начинаю отправку уведомлений...")
        
        # Получаем напоминания за 1 день до платежа
        reminders = db.get_reminders_for_notification(days_before=1)
        
        if not reminders:
            logger.info("📭 Нет напоминаний для уведомлений сегодня")
            return
        
        logger.info(f"📨 Найдено {len(reminders)} напоминаний для уведомлений")
        
        sent_count = 0
        error_count = 0
        
        for reminder in reminders:
            try:
                # Форматируем дату платежа
                payment_date = reminder['payment_date']
                if isinstance(payment_date, str):
                    # Преобразуем строку в дату
                    date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                else:
                    formatted_date = payment_date.strftime('%d.%m.%Y')
                
                # Формируем сообщение
                message = (
                    f"🔔 <b>НАПОМИНАНИЕ О ПЛАТЕЖЕ</b>\n\n"
                    f"<b>{reminder['title']}</b>\n"
                    f"💰 Сумма: {reminder['amount']}₽\n"
                    f"📅 Дата оплаты: <b>{formatted_date}</b>\n"
                    f"⏰ Осталось дней: <b>{reminder['days_left']}</b>\n\n"
                    f"Не забудьте оплатить вовремя!"
                )
                
                # Отправляем сообщение
                await context.bot.send_message(
                    chat_id=reminder['telegram_id'],
                    text=message,
                    parse_mode='HTML'
                )
                
                sent_count += 1
                logger.info(f"✅ Отправлено пользователю {reminder['telegram_id']}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка отправки {reminder['telegram_id']}: {e}")
        
        logger.info(f"📊 Итог: отправлено {sent_count}, ошибок {error_count}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в уведомлениях: {e}")
