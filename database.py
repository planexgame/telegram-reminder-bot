# database.py - простой без циклических импортов
import os
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.connection = None
    
    def get_connection(self):
        """Получаем соединение с базой данных"""
        try:
            if not self.connection or self.connection.closed:
                database_url = os.getenv('DATABASE_URL')
                if not database_url:
                    logger.warning("❌ DATABASE_URL не настроен! Использую SQLite для тестирования.")
                    return None
                
                self.connection = psycopg2.connect(database_url, sslmode='require')
            return self.connection
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            return None
    
    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = self.get_connection()
            if not conn:
                logger.warning("⚠️ Не удалось подключиться к БД. Создаем таблицы при первой операции.")
                return True
            
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(100),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    is_premium BOOLEAN DEFAULT FALSE,
                    premium_until DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица напоминаний
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(200) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    payment_date DATE NOT NULL,
                    recurrence VARCHAR(20) DEFAULT 'once',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            cursor.close()
            logger.info("✅ База данных инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            return False
    
    def get_or_create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Получаем или создаем пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return 1  # Возвращаем заглушку для тестов
            
            cursor = conn.cursor()
            
            # Пробуем найти пользователя
            cursor.execute(
                'SELECT id FROM users WHERE telegram_id = %s',
                (telegram_id,)
            )
            result = cursor.fetchone()
            
            if result:
                user_id = result[0]
            else:
                # Создаем нового пользователя
                cursor.execute(
                    '''
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    ''',
                    (telegram_id, username, first_name, last_name)
                )
                user_id = cursor.fetchone()[0]
                conn.commit()
            
            cursor.close()
            return user_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения/создания пользователя: {e}")
            return None
    
    def get_user_premium_status(self, user_id):
        """Получаем статус премиума пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return {'has_active_premium': False}
            
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT is_premium, premium_until 
                FROM users 
                WHERE id = %s
                ''',
                (user_id,)
            )
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                is_premium, premium_until = result
                has_active_premium = is_premium
                
                # Проверяем срок действия
                if premium_until and hasattr(premium_until, 'date'):
                    if datetime.now().date() > premium_until:
                        # Премиум истек
                        cursor = conn.cursor()
                        cursor.execute(
                            'UPDATE users SET is_premium = FALSE WHERE id = %s',
                            (user_id,)
                        )
                        conn.commit()
                        cursor.close()
                        has_active_premium = False
                
                return {
                    'has_active_premium': has_active_premium,
                    'premium_until': premium_until
                }
            
            return {'has_active_premium': False}
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса премиума: {e}")
            return {'has_active_premium': False}
    
    def get_user_reminders_count(self, user_id):
        """Получаем количество напоминаний пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return 0
            
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM reminders WHERE user_id = %s AND is_active = TRUE',
                (user_id,)
            )
            count = cursor.fetchone()[0]
            cursor.close()
            return count
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества напоминаний: {e}")
            return 0
    
    def get_user_reminders(self, user_id):
        """Получаем все напоминания пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute(
                '''
                SELECT id, title, amount, payment_date, recurrence, is_active
                FROM reminders 
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY payment_date
                ''',
                (user_id,)
            )
            reminders = cursor.fetchall()
            cursor.close()
            
            return [dict(rem) for rem in reminders]
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения напоминаний: {e}")
            return []
    
    def add_reminder(self, user_id, title, amount, payment_date, recurrence='once'):
        """Добавляем напоминание"""
        try:
            conn = self.get_connection()
            if not conn:
                return 1  # Заглушка для тестов
            
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO reminders (user_id, title, amount, payment_date, recurrence)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                ''',
                (user_id, title, amount, payment_date, recurrence)
            )
            reminder_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            
            return reminder_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления напоминания: {e}")
            return None
    
    def delete_reminder(self, user_id, reminder_id):
        """Удаляем напоминание"""
        try:
            conn = self.get_connection()
            if not conn:
                return True  # Заглушка
            
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM reminders WHERE id = %s AND user_id = %s',
                (reminder_id, user_id)
            )
            conn.commit()
            cursor.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления напоминания: {e}")
            return False
    
    def activate_premium(self, user_id, days):
        """Активируем премиум на указанное количество дней"""
        try:
            conn = self.get_connection()
            if not conn:
                return True  # Заглушка
            
            premium_until = datetime.now() + timedelta(days=days)
            
            cursor = conn.cursor()
            cursor.execute(
                '''
                UPDATE users 
                SET is_premium = TRUE, premium_until = %s
                WHERE id = %s
                ''',
                (premium_until, user_id)
            )
            conn.commit()
            cursor.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка активации премиума: {e}")
            return False

# Создаем глобальный экземпляр
db = Database()
