# payments.py
import os
import json
import requests
import uuid
import logging
from database import db

logger = logging.getLogger(__name__)

# Конфигурация ЮKassa
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
YOOKASSA_WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', '') + '/yookassa_webhook'

class YooKassaPayment:
    def __init__(self):
        self.shop_id = YOOKASSA_SHOP_ID
        self.secret_key = YOOKASSA_SECRET_KEY
        self.base_url = "https://api.yookassa.ru/v3"
        
    def is_configured(self):
        """Проверка настроек ЮKassa"""
        return bool(self.shop_id and self.secret_key)
    
    def create_payment(self, user_id, amount, description, return_url, metadata=None):
        """Создать платеж в ЮKassa"""
        if not self.is_configured():
            logger.error("ЮKassa не настроена")
            return None
        
        payment_id = str(uuid.uuid4())
        
        headers = {
            "Idempotence-Key": payment_id,
            "Content-Type": "application/json"
        }
        
        auth = (self.shop_id, self.secret_key)
        
        data = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "payment_method_data": {
                "type": "bank_card"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "description": description,
            "capture": True,
            "metadata": metadata or {}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/payments",
                json=data,
                headers=headers,
                auth=auth,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Платеж создан в ЮKassa: {result.get('id')}")
                return result
            else:
                logger.error(f"❌ Ошибка создания платежа: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к ЮKassa: {e}")
            return None
    
    def get_payment_status(self, payment_id):
        """Получить статус платежа"""
        if not self.is_configured():
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/payments/{payment_id}",
                auth=(self.shop_id, self.secret_key),
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Ошибка получения статуса: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            return None
    
    def process_webhook(self, data):
        """Обработка вебхука от ЮKassa"""
        try:
            event = data.get('event')
            payment_data = data.get('object', {})
            
            logger.info(f"📨 Получен вебхук от ЮKassa: {event}")
            
            if event == 'payment.succeeded':
                payment_id = payment_data.get('id')
                metadata = payment_data.get('metadata', {})
                user_id = metadata.get('user_id')
                amount = float(payment_data.get('amount', {}).get('value', 0))
                
                logger.info(f"✅ Платеж успешен: {payment_id}, пользователь: {user_id}, сумма: {amount}")
                
                # Обновляем статус платежа в БД
                if db.update_payment_status_by_yookassa_id(payment_id, 'succeeded'):
                    logger.info(f"✅ Премиум активирован для пользователя {user_id}")
                else:
                    logger.error(f"❌ Не удалось обновить статус платежа {payment_id}")
                
                return True
                
            elif event == 'payment.canceled':
                payment_id = payment_data.get('id')
                logger.info(f"❌ Платеж отменен: {payment_id}")
                db.update_payment_status_by_yookassa_id(payment_id, 'canceled')
                return True
                
            elif event == 'payment.waiting_for_capture':
                payment_id = payment_data.get('id')
                logger.info(f"⏳ Платеж ожидает подтверждения: {payment_id}")
                return True
                
            elif event == 'refund.succeeded':
                payment_id = payment_data.get('payment_id')
                logger.info(f"↩️ Возврат средств: {payment_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки вебхука: {e}")
            logger.error(f"Данные вебхука: {data}")
        
        return False

# Функция для обработки вебхука в боте
async def handle_yookassa_webhook(request_data):
    """Обработка вебхука от ЮKassa (для использования в боте)"""
    try:
        data = json.loads(request_data)
        yookassa = YooKassaPayment()
        return yookassa.process_webhook(data)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return False

# Глобальный экземпляр
yookassa = YooKassaPayment()

# Функция для ручной активации премиума (для администратора)
def manual_activate_premium(telegram_id, days=30):
    """Ручная активация премиума (для админа)"""
    try:
        # Находим user_id по telegram_id
        with db.get_connection() as conn:
            if not conn:
                return False
            
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE telegram_id = %s', (telegram_id,))
            result = cursor.fetchone()
            
            if not result:
                logger.error(f"❌ Пользователь не найден: {telegram_id}")
                return False
            
            user_id = result[0]
            
            # Активируем премиум
            if db.activate_premium(user_id, days):
                logger.info(f"✅ Премиум активирован вручную для пользователя {telegram_id} на {days} дней")
                return True
            else:
                logger.error(f"❌ Ошибка активации премиума для {telegram_id}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка ручной активации: {e}")
        return False
