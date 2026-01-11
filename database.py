# database.py
import os
import psycopg2
from contextlib import contextmanager
import logging

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

# Создаем глобальный экземпляр БД
db = Database()
