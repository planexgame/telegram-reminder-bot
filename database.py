# database.py
import sqlite3
import os
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_path='reminders.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Создает подключение к базе данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None
    
    def init_db(self):
        """Инициализация базы данных"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                    
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_premium BOOLEAN DEFAULT FALSE,
                        premium_until DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица напоминаний
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        amount REAL NOT NULL,
                        payment_date DATE NOT NULL,
                        is_paid BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                ''')
                
                # Индексы для оптимизации
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON reminders(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payment_date ON reminders(payment_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_telegram_id ON users(telegram_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_premium_until ON users(premium_until)')
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"Ошибка инициализации БД: {e}")
            return False
    
    def get_or_create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Получить или создать пользователя"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return None
                    
                cursor = conn.cursor()
                
                # Пытаемся найти пользователя
                cursor.execute(
                    'SELECT id FROM users WHERE telegram_id = ?',
                    (telegram_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    return result[0]
                else:
                    # Создаем нового пользователя
                    cursor.execute('''
                        INSERT INTO users (telegram_id, username, first_name, last_name)
                        VALUES (?, ?, ?, ?)
                    ''', (telegram_id, username, first_name, last_name))
                    conn.commit()
                    return cursor.lastrowid
                    
        except Exception as e:
            print(f"Ошибка создания пользователя: {e}")
            return None
    
    def get_user_premium_status(self, user_id):
        """Получить статус премиума пользователя"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return {'has_active_premium': False}
                    
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT is_premium, premium_until 
                    FROM users 
                    WHERE id = ?
                ''', (user_id,))
                
                result = cursor.fetchone()
                if result:
                    is_premium = bool(result[0])
                    premium_until = result[1]
                    
                    # Проверяем, не истек ли премиум
                    if is_premium and premium_until:
                        try:
                            until_date = datetime.strptime(premium_until, '%Y-%m-%d').date()
                            if until_date < datetime.now().date():
                                # Премиум истек - обновляем статус
                                cursor.execute(
                                    'UPDATE users SET is_premium = FALSE WHERE id = ?',
                                    (user_id,)
                                )
                                conn.commit()
                                return {'has_active_premium': False}
                        except:
                            pass
                    
                    return {
                        'has_active_premium': is_premium,
                        'premium_until': premium_until
                    }
                    
        except Exception as e:
            print(f"Ошибка получения статуса премиума: {e}")
            
        return {'has_active_premium': False}
    
    def get_user_reminders_count(self, user_id):
        """Получить количество напоминаний пользователя"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return 0
                    
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT COUNT(*) FROM reminders WHERE user_id = ?',
                    (user_id,)
                )
                return cursor.fetchone()[0] or 0
                
        except Exception as e:
            print(f"Ошибка подсчета напоминаний: {e}")
            return 0
    
    def get_user_reminders(self, user_id):
        """Получить все напоминания пользователя"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return []
                    
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, title, amount, payment_date, is_paid
                    FROM reminders 
                    WHERE user_id = ?
                    ORDER BY payment_date ASC
                ''', (user_id,))
                
                reminders = []
                for row in cursor.fetchall():
                    reminders.append(dict(row))
                    
                return reminders
                
        except Exception as e:
            print(f"Ошибка получения напоминаний: {e}")
            return []
    
    def add_reminder(self, user_id, title, amount, payment_date):
        """Добавить новое напоминание"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return None
                    
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO reminders (user_id, title, amount, payment_date)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, title, amount, payment_date))
                
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            print(f"Ошибка добавления напоминания: {e}")
            return None
    
    def delete_reminder(self, user_id, reminder_id):
        """Удалить напоминание"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                    
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM reminders WHERE id = ? AND user_id = ?',
                    (reminder_id, user_id)
                )
                
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            print(f"Ошибка удаления напоминания: {e}")
            return False
    
    def activate_premium(self, user_id, days):
        """Активировать премиум на указанное количество дней"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                    
                cursor = conn.cursor()
                
                # Рассчитываем дату окончания
                premium_until = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = TRUE, premium_until = ?
                    WHERE id = ?
                ''', (premium_until, user_id))
                
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            print(f"Ошибка активации премиума: {e}")
            return False
    
    def deactivate_premium(self, user_id):
        """Деактивировать премиум для пользователя"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                    
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = FALSE, premium_until = NULL 
                    WHERE id = ?
                ''', (user_id,))
                
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            print(f"Ошибка деактивации премиума: {e}")
            return False
    
    def get_upcoming_reminders(self, days_before=1):
        """Получить напоминания, до которых осталось указанное количество дней"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return []
                    
                cursor = conn.cursor()
                
                # Рассчитываем дату
                target_date = (datetime.now() + timedelta(days=days_before)).date()
                target_date_str = target_date.strftime('%Y-%m-%d')
                
                cursor.execute('''
                    SELECT r.id, r.title, r.amount, r.payment_date,
                           u.telegram_id, u.username, u.first_name,
                           u.is_premium, u.premium_until
                    FROM reminders r
                    JOIN users u ON r.user_id = u.id
                    WHERE r.payment_date = ?
                    AND r.is_paid = FALSE
                    ORDER BY u.telegram_id
                ''', (target_date_str,))
                
                reminders = []
                for row in cursor.fetchall():
                    reminders.append(dict(row))
                    
                return reminders
                
        except Exception as e:
            print(f"Ошибка получения предстоящих напоминаний: {e}")
            return []
    
    def get_all_users(self):
        """Получить всех пользователей"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return []
                    
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT telegram_id, username, first_name, is_premium, created_at
                    FROM users
                    ORDER BY created_at DESC
                ''')
                
                users = []
                for row in cursor.fetchall():
                    users.append(dict(row))
                    
                return users
                
        except Exception as e:
            print(f"Ошибка получения всех пользователей: {e}")
            return []
    
    def get_premium_users(self):
        """Получить только премиум пользователей"""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return []
                    
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT telegram_id, username, first_name, premium_until
                    FROM users
                    WHERE is_premium = TRUE
                    ORDER BY premium_until DESC
                ''')
                
                users = []
                for row in cursor.fetchall():
                    users.append(dict(row))
                    
                return users
                
        except Exception as e:
            print(f"Ошибка получения премиум пользователей: {e}")
            return []

# Создаем глобальный экземпляр базы данных
db = Database()
