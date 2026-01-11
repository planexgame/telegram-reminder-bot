# database.py - обновленная версия
import os
import psycopg2
from psycopg2.extras import RealDictCursor, DictCursor
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL не найден! Установите в Render.")
    DATABASE_URL = "postgresql://user:pass@localhost/dbname"

class Database:
    def __init__(self):
        self.connection = None
    
    def get_connection(self):
        """Получение соединения с базой данных"""
        try:
            if not self.connection or self.connection.closed:
                self.connection = psycopg2.connect(
                    DATABASE_URL,
                    sslmode='require' if 'render.com' in DATABASE_URL else 'prefer'
                )
            return self.connection
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            return None
    
    def init_db(self):
        """Инициализация базы данных (создание таблиц если их нет)"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    is_premium BOOLEAN DEFAULT FALSE,
                    premium_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица напоминаний
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(255) NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    payment_date DATE NOT NULL,
                    recurrence VARCHAR(50) DEFAULT 'once',
                    is_active BOOLEAN DEFAULT TRUE,
                    notified_3_days BOOLEAN DEFAULT FALSE,
                    notified_1_day BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица платежей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    amount DECIMAL(10, 2) NOT NULL,
                    period_days INTEGER NOT NULL,
                    yookassa_payment_id VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'pending',
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для ускорения поиска
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_reminders_payment_date ON reminders(payment_date)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_reminders_is_active ON reminders(is_active)
            ''')
            
            conn.commit()
            cursor.close()
            logger.info("✅ База данных инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            return False
    
    def get_or_create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Получение или создание пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            
            cursor = conn.cursor()
            
            # Пробуем найти пользователя
            cursor.execute(
                'SELECT id FROM users WHERE telegram_id = %s',
                (telegram_id,)
            )
            result = cursor.fetchone()
            
            if result:
                user_id = result[0]
                # Обновляем данные пользователя
                cursor.execute('''
                    UPDATE users 
                    SET username = %s, 
                        first_name = %s, 
                        last_name = %s,
                        updated_at = NOW()
                    WHERE id = %s
                ''', (username, first_name, last_name, user_id))
            else:
                # Создаем нового пользователя
                cursor.execute('''
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (telegram_id, username, first_name, last_name))
                user_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            return user_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_or_create_user: {e}")
            return None
    
    def get_user_premium_status(self, user_id):
        """Получение статуса премиума пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return {'has_active_premium': False}
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute('''
                SELECT is_premium, premium_until 
                FROM users 
                WHERE id = %s
            ''', (user_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                is_premium = result['is_premium']
                premium_until = result['premium_until']
                
                # Проверяем, не истек ли премиум
                has_active_premium = False
                if is_premium and premium_until:
                    if datetime.now() < premium_until:
                        has_active_premium = True
                    else:
                        # Премиум истек - обновляем статус
                        self.deactivate_premium(user_id)
                
                return {
                    'is_premium': is_premium,
                    'premium_until': premium_until,
                    'has_active_premium': has_active_premium
                }
            else:
                return {'has_active_premium': False}
                
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_premium_status: {e}")
            return {'has_active_premium': False}
    
    def get_user_reminders_count(self, user_id):
        """Получение количества напоминаний пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return 0
            
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) 
                FROM reminders 
                WHERE user_id = %s AND is_active = TRUE
            ''', (user_id,))
            
            count = cursor.fetchone()[0]
            cursor.close()
            return count
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_reminders_count: {e}")
            return 0
    
    # ========== НОВАЯ ФУНКЦИЯ: get_user_reminders ==========
    def get_user_reminders(self, user_id, limit=50):
        """Получение списка напоминаний пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute('''
                SELECT id, title, amount, payment_date, recurrence, is_active, created_at
                FROM reminders 
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY payment_date ASC
                LIMIT %s
            ''', (user_id, limit))
            
            reminders = cursor.fetchall()
            cursor.close()
            
            # Конвертируем в список словарей
            result = []
            for reminder in reminders:
                result.append({
                    'id': reminder['id'],
                    'title': reminder['title'],
                    'amount': float(reminder['amount']) if reminder['amount'] else 0,
                    'payment_date': reminder['payment_date'],
                    'recurrence': reminder['recurrence'],
                    'is_active': reminder['is_active'],
                    'created_at': reminder['created_at']
                })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_reminders: {e}")
            return []
    
    # ========== НОВАЯ ФУНКЦИЯ: delete_reminder ==========
    def delete_reminder(self, user_id, reminder_id):
        """Удаление напоминания пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            # Проверяем, что напоминание принадлежит пользователю
            cursor.execute('''
                DELETE FROM reminders 
                WHERE id = %s AND user_id = %s
            ''', (reminder_id, user_id))
            
            deleted = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            
            return deleted
            
        except Exception as e:
            logger.error(f"❌ Ошибка delete_reminder: {e}")
            return False
    
    # ========== НОВАЯ ФУНКЦИЯ: activate_premium ==========
    def activate_premium(self, user_id, days):
        """Активация премиум подписки пользователю"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            # Рассчитываем дату окончания
            premium_until = datetime.now() + timedelta(days=days)
            
            cursor.execute('''
                UPDATE users 
                SET is_premium = TRUE, 
                    premium_until = %s,
                    updated_at = NOW()
                WHERE id = %s
            ''', (premium_until, user_id))
            
            updated = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            
            if updated:
                logger.info(f"✅ Премиум активирован для пользователя {user_id} на {days} дней")
            
            return updated
            
        except Exception as e:
            logger.error(f"❌ Ошибка activate_premium: {e}")
            return False
    
    # ========== ДОПОЛНИТЕЛЬНАЯ ФУНКЦИЯ: deactivate_premium ==========
    def deactivate_premium(self, user_id):
        """Деактивация премиум подписки"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET is_premium = FALSE, 
                    premium_until = NULL,
                    updated_at = NOW()
                WHERE id = %s
            ''', (user_id,))
            
            updated = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            
            if updated:
                logger.info(f"✅ Премиум деактивирован для пользователя {user_id}")
            
            return updated
            
        except Exception as e:
            logger.error(f"❌ Ошибка deactivate_premium: {e}")
            return False
    
    def add_reminder(self, user_id, title, amount, payment_date, recurrence='once'):
        """Добавление нового напоминания"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO reminders (user_id, title, amount, payment_date, recurrence)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (user_id, title, amount, payment_date, recurrence))
            
            reminder_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            
            logger.info(f"✅ Напоминание создано: {reminder_id} для пользователя {user_id}")
            return reminder_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка add_reminder: {e}")
            return None
    
    def get_reminders_for_notification(self, days_before=1):
        """Получение напоминаний для уведомления"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            
            # Рассчитываем дату
            target_date = (datetime.now() + timedelta(days=days_before)).date()
            
            cursor.execute('''
                SELECT r.*, u.telegram_id, u.first_name, u.is_premium
                FROM reminders r
                JOIN users u ON r.user_id = u.id
                WHERE r.payment_date = %s 
                AND r.is_active = TRUE
                AND (
                    (days_before = 1 AND r.notified_1_day = FALSE) OR
                    (days_before = 3 AND r.notified_3_days = FALSE AND u.is_premium = TRUE)
                )
            ''', (target_date,))
            
            reminders = cursor.fetchall()
            cursor.close()
            
            return reminders
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_reminders_for_notification: {e}")
            return []
    
    def mark_reminder_notified(self, reminder_id, days_before):
        """Пометить напоминание как уведомленное"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            if days_before == 1:
                cursor.execute('''
                    UPDATE reminders 
                    SET notified_1_day = TRUE,
                        updated_at = NOW()
                    WHERE id = %s
                ''', (reminder_id,))
            elif days_before == 3:
                cursor.execute('''
                    UPDATE reminders 
                    SET notified_3_days = TRUE,
                        updated_at = NOW()
                    WHERE id = %s
                ''', (reminder_id,))
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка mark_reminder_notified: {e}")
            return False
    
    def create_payment(self, user_id, amount, period_days):
        """Создание записи о платеже"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO payments (user_id, amount, period_days)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (user_id, amount, period_days))
            
            payment_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            
            return payment_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка create_payment: {e}")
            return None
    
    def update_payment_status(self, payment_id, status, yookassa_payment_id=None):
        """Обновление статуса платежа"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            if status == 'succeeded':
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s, 
                        yookassa_payment_id = %s,
                        completed_at = NOW()
                    WHERE id = %s
                ''', (status, yookassa_payment_id, payment_id))
            else:
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s, 
                        yookassa_payment_id = %s
                    WHERE id = %s
                ''', (status, yookassa_payment_id, payment_id))
            
            updated = cursor.rowcount > 0
            
            # Если платеж успешный - активируем премиум
            if status == 'succeeded':
                cursor.execute('''
                    SELECT user_id, period_days 
                    FROM payments 
                    WHERE id = %s
                ''', (payment_id,))
                
                result = cursor.fetchone()
                if result:
                    user_id, period_days = result
                    self.activate_premium(user_id, period_days)
            
            conn.commit()
            cursor.close()
            return updated
            
        except Exception as e:
            logger.error(f"❌ Ошибка update_payment_status: {e}")
            return False
    
    def get_payment_info(self, payment_id):
        """Получение информации о платеже"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            
            cursor.execute('''
                SELECT * FROM payments WHERE id = %s
            ''', (payment_id,))
            
            payment = cursor.fetchone()
            cursor.close()
            
            return payment
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_payment_info: {e}")
            return None
    
    def get_user_payments(self, user_id):
        """Получение платежей пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            
            cursor.execute('''
                SELECT * FROM payments 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            ''', (user_id,))
            
            payments = cursor.fetchall()
            cursor.close()
            
            return payments
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_payments: {e}")
            return []
    
    def update_payment_status_by_yookassa_id(self, yookassa_payment_id, status):
        """Обновление статуса платежа по ID ЮKassa"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, user_id, period_days 
                FROM payments 
                WHERE yookassa_payment_id = %s
            ''', (yookassa_payment_id,))
            
            result = cursor.fetchone()
            if not result:
                return False
            
            payment_id, user_id, period_days = result
            
            # Обновляем статус
            cursor.execute('''
                UPDATE payments 
                SET status = %s,
                    completed_at = CASE WHEN %s = 'succeeded' THEN NOW() ELSE completed_at END
                WHERE id = %s
            ''', (status, status, payment_id))
            
            # Если платеж успешный - активируем премиум
            if status == 'succeeded':
                self.activate_premium(user_id, period_days)
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка update_payment_status_by_yookassa_id: {e}")
            return False

# Создаем глобальный экземпляр базы данных
db = Database()
