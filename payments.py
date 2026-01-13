# payments.py - ручная оплата (без ЮKassa)
import logging

logger = logging.getLogger(__name__)

class ManualPayment:
    """Класс для ручной обработки платежей"""
    
    def __init__(self):
        self.payment_method = "Ручная оплата"
        logger.info("✅ Инициализирована ручная система оплаты")
    
    def is_configured(self):
        """Всегда True для ручной оплаты"""
        return True
    
    def create_payment_link(self, amount, description, user_id):
        """Создание инструкции для ручной оплаты"""
        logger.info(f"Создана заявка на ручную оплату: user={user_id}, amount={amount}")
        
        return {
            "success": True,
            "payment_method": "manual",
            "instructions": "Переведите средства по реквизитам и нажмите '✅ Я оплатил'",
            "amount": amount,
            "description": description
        }
    
    def verify_payment(self, payment_id):
        """Вернуть статус ожидания для ручной оплаты"""
        return {
            "status": "pending",
            "message": "Ожидание ручной активации администратором"
        }

# Создаем экземпляр для ручной оплаты
manual_payment = ManualPayment()
