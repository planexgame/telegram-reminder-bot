# database.py
import os
import psycopg2
from contextlib import contextmanager
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')

class Database:
    def __init__(self):
        self.conn = None
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        if not DATABASE_URL:
            logger.warning("DATABASE_URL не найден")
            yield None
            return
            
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка БД: {e}")
            raise
        finally:
            conn.close()
    
    def init_db(self):
        """Инициализация таблиц в базе данных"""
        if not DATABASE_URL:
            logger.warning("⚠️ База данных отключена (нет DATABASE_URL)")
            return False
            
        try:
            with self.get_connection() as conn:
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
                        premium_until DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица напоминаний
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        title VARCHAR(255) NOT NULL,
                        amount DECIMAL(10, 2),
                        payment_date DATE NOT NULL,
                        recurrence VARCHAR(20) DEFAULT 'once',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ТАБЛИЦА ПЛАТЕЖЕЙ (НОВАЯ ДЛЯ ПРЕМИУМА)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        amount DECIMAL(10, 2) NOT NULL,
                        currency VARCHAR(3) DEFAULT 'RUB',
                        status VARCHAR(20) DEFAULT 'pending',
                        payment_method VARCHAR(50),
                        subscription_days INTEGER DEFAULT 30,
                        yookassa_payment_id VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        metadata TEXT
                    )
                ''')
                
                # Индексы для скорости
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_date ON reminders(payment_date, is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium, premium_until)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status, user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_yookassa ON payments(yookassa_payment_id)')
                
                logger.info("✅ Таблицы созданы/проверены")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            return False
    
    def get_or_create_user(self, telegram_id, username, first_name, last_name):
        """Получить или создать пользователя"""
        with self.get_connection() as conn:
            if not conn:
                return None
                
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name
                RETURNING id
            ''', (telegram_id, username, first_name, last_name))
            
            user_id = cursor.fetchone()[0]
            return user_id
    
    def get_user_reminders_count(self, user_id):
        """Получить количество активных напоминаний пользователя"""
        with self.get_connection() as conn:
            if not conn:
                return 0
                
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM reminders 
                WHERE user_id = %s AND is_active = TRUE
            ''', (user_id,))
            
            return cursor.fetchone()[0]
    
    def add_reminder(self, user_id, title, amount, payment_date):
        """Добавить новое напоминание"""
        with self.get_connection() as conn:
            if not conn:
                return None
                
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reminders (user_id, title, amount, payment_date)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (user_id, title, amount, payment_date))
            
            reminder_id = cursor.fetchone()[0]
            return reminder_id
    
    def get_user_reminders(self, user_id):
        """Получить все напоминания пользователя"""
        with self.get_connection() as conn:
            if not conn:
                return []
                
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, amount, payment_date, recurrence, created_at
                FROM reminders 
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY payment_date ASC
            ''', (user_id,))
            
            columns = ['id', 'title', 'amount', 'payment_date', 'recurrence', 'created_at']
            reminders = []
            for row in cursor.fetchall():
                reminders.append(dict(zip(columns, row)))
            
            return reminders
    
    def delete_reminder(self, user_id, reminder_id):
        """Удалить напоминание (деактивировать)"""
        with self.get_connection() as conn:
            if not conn:
                return False
                
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE reminders 
                SET is_active = FALSE 
                WHERE id = %s AND user_id = %s
                RETURNING id
            ''', (reminder_id, user_id))
            
            return cursor.fetchone() is not None

    # ========== ФУНКЦИЯ ДЛЯ УВЕДОМЛЕНИЙ ==========
    def get_reminders_for_notification(self, days_before=1):
        """Получить напоминания для уведомления (за N дней до платежа)"""
        with self.get_connection() as conn:
            if not conn:
                return []
                
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.telegram_id, 
                    r.title, 
                    r.amount, 
                    r.payment_date,
                    DATE(r.payment_date) - CURRENT_DATE as days_left
                FROM reminders r
                JOIN users u ON r.user_id = u.id
                WHERE 
                    r.is_active = TRUE
                    AND DATE(r.payment_date) > CURRENT_DATE
                    AND DATE(r.payment_date) - CURRENT_DATE = %s
                ORDER BY r.payment_date
            ''', (days_before,))
            
            columns = ['telegram_id', 'title', 'amount', 'payment_date', 'days_left']
            reminders = []
            for row in cursor.fetchall():
                reminders.append(dict(zip(columns, row)))
            
            return reminders

    # ========== МЕТОДЫ ДЛЯ ПРЕМИУМ СИСТЕМЫ ==========
    
    def get_user_premium_status(self, user_id):
        """Получить статус премиум подписки пользователя"""
        with self.get_connection() as conn:
            if not conn:
                return {'is_premium': False, 'premium_until': None, 'has_active_premium': False}
            
            cursor = conn.cursor()
            cursor.execute('''
                SELECT is_premium, premium_until 
                FROM users 
                WHERE id = %s
            ''', (user_id,))
            
            result = cursor.fetchone()
            if result:
                is_premium, premium_until = result
                has_active = is_premium and (premium_until is None or premium_until >= datetime.now().date())
                return {
                    'is_premium': is_premium,
                    'premium_until': premium_until,
                    'has_active_premium': has_active
                }
            
            return {'is_premium': False, 'premium_until': None, 'has_active_premium': False}
    
    def activate_premium(self, user_id, days=30):
        """Активировать премиум подписку"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET is_premium = TRUE,
                    premium_until = CURRENT_DATE + INTERVAL '%s days'
                WHERE id = %s
                RETURNING id
            ''', (days, user_id))
            
            return cursor.fetchone() is not None
    
    def create_payment(self, user_id, amount, subscription_days, yookassa_payment_id=None):
        """Создать запись о платеже"""
        with self.get_connection() as conn:
            if not conn:
                return None
            
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments 
                (user_id, amount, subscription_days, yookassa_payment_id, status)
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING id
            ''', (user_id, amount, subscription_days, yookassa_payment_id))
            
            return cursor.fetchone()[0]
    
    def update_payment_status(self, payment_id, status, yookassa_payment_id=None):
        """Обновить статус платежа"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            cursor = conn.cursor()
            if status == 'succeeded':
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s, 
                        completed_at = CURRENT_TIMESTAMP,
                        yookassa_payment_id = COALESCE(%s, yookassa_payment_id)
                    WHERE id = %s
                    RETURNING user_id, subscription_days
                ''', (status, yookassa_payment_id, payment_id))
                
                result = cursor.fetchone()
                if result:
                    user_id, subscription_days = result
                    # Активируем премиум
                    self.activate_premium(user_id, subscription_days)
                    return True
            else:
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s,
                        yookassa_payment_id = COALESCE(%s, yookassa_payment_id)
                    WHERE id = %s
                ''', (status, yookassa_payment_id, payment_id))
            
            return True
    
    def update_payment_status_by_yookassa_id(self, yookassa_payment_id, status):
        """Обновить статус платежа по ID ЮKassa"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            cursor = conn.cursor()
            if status == 'succeeded':
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE yookassa_payment_id = %s
                    RETURNING user_id, subscription_days
                ''', (status, yookassa_payment_id))
                
                result = cursor.fetchone()
                if result:
                    user_id, subscription_days = result
                    # Активируем премиум
                    self.activate_premium(user_id, subscription_days)
                    return True
            else:
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s
                    WHERE yookassa_payment_id = %s
                ''', (status, yookassa_payment_id))
            
            return result is not None
    
    def get_payment_info(self, payment_id):
        """Получить информацию о платеже"""
        with self.get_connection() as conn:
            if not conn:
                return None
            
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, amount, status, subscription_days, 
                       yookassa_payment_id, created_at, completed_at
                FROM payments 
                WHERE id = %s
            ''', (payment_id,))
            
            result = cursor.fetchone()
            if result:
                columns = ['id', 'user_id', 'amount', 'status', 'subscription_days', 
                          'yookassa_payment_id', 'created_at', 'completed_at']
                return dict(zip(columns, result))
            
            return None
    
    def get_user_payments(self, user_id):
        """Получить все платежи пользователя"""
        with self.get_connection() as conn:
            if not conn:
                return []
            
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, amount, status, subscription_days, created_at, completed_at
                FROM payments 
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
            
            columns = ['id', 'amount', 'status', 'subscription_days', 'created_at', 'completed_at']
            payments = []
            for row in cursor.fetchall():
                payments.append(dict(zip(columns, row)))
            
            return payments

# Создаем глобальный экземпляр БД
db = Database()
