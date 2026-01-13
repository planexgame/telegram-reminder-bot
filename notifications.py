# notifications.py
import logging
from datetime import datetime, timedelta
from database import db

logger = logging.getLogger(__name__)

async def send_reminder_notifications(context):
    """Отправка уведомлений о предстоящих платежах"""
    try:
        # Получаем напоминания на завтра
        tomorrow_reminders = db.get_upcoming_reminders(days_before=1)
        
        for reminder in tomorrow_reminders:
            try:
                telegram_id = reminder['telegram_id']
                title = reminder['title']
                amount = reminder['amount']
                
                # Проверяем, является ли пользователь премиум
                is_premium = reminder.get('is_premium', False)
                
                message = (
                    f"🔔 <b>НАПОМИНАНИЕ О ПЛАТЕЖЕ!</b>\n\n"
                    f"<b>Название:</b> {title}\n"
                    f"<b>Сумма:</b> {amount}₽\n"
                    f"<b>Дата оплаты:</b> ЗАВТРА!\n\n"
                )
                
                if is_premium:
                    message += f"💎 <i>Спасибо за использование премиума!</i>"
                else:
                    message += f"🆓 <i>Для получения напоминаний за 3 и 7 дней оформите премиум</i>"
                
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode='HTML'
                )
                
                logger.info(f"Отправлено уведомление пользователю {telegram_id}")
                
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")
                continue
        
        # Для премиум пользователей также отправляем за 3 и 7 дней
        premium_reminders_3 = []
        premium_reminders_7 = []
        
        # Находим премиум пользователей
        premium_users = db.get_premium_users()
        
        for user in premium_users:
            try:
                # Здесь должна быть логика для получения напоминаний каждого пользователя
                # за 3 и 7 дней. В реальной реализации нужно доработать этот метод
                pass
            except Exception as e:
                logger.error(f"Ошибка обработки премиум пользователя: {e}")
                continue
                
        logger.info(f"Уведомления отправлены: {len(tomorrow_reminders)} напоминаний")
        
    except Exception as e:
        logger.error(f"Ошибка в планировщике уведомлений: {e}")
