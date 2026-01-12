# database.py - рабочая версия
import os
import psycopg2
from psycopg2.extras import RealDictCursor, DictCursor
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL не найден!")
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
        """Инициализация базы данных"""
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица платежей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    amount DECIMAL(10, 2) NOT NULL,
                    period_days INTEGER NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_payment_date ON reminders(payment_date)')
            
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
                # Обновляем данные если изменились
                cursor.execute('''
                    UPDATE users 
                    SET username = COALESCE(%s, username),
                        first_name = COALESCE(%s, first_name),
                        last_name = COALESCE(%s, last_name)
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
            # Если таблицы нет - создаем
            self.init_db()
            # Пробуем снова
            return self.get_or_create_user(telegram_id, username, first_name, last_name)
    
    def get_user_premium_status(self, user_id):
        """Получение статуса премиума пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return {'has_active_premium': False, 'is_premium': False, 'premium_until': None}
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute('''
                SELECT is_premium, premium_until 
                FROM users 
                WHERE id = %s
            ''', (user_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                is_premium = bool(result['is_premium'])
                premium_until = result['premium_until']
                
                # Проверяем, не истек ли премиум
                has_active_premium = False
                if is_premium and premium_until:
                    try:
                        if datetime.now() < premium_until:
                            has_active_premium = True
                        else:
                            # Премиум истек
                            self.deactivate_premium(user_id)
                            has_active_premium = False
                    except:
                        has_active_premium = is_premium
                else:
                    has_active_premium = is_premium
                
                return {
                    'is_premium': is_premium,
                    'premium_until': premium_until,
                    'has_active_premium': has_active_premium
                }
            else:
                return {'has_active_premium': False, 'is_premium': False, 'premium_until': None}
                
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_premium_status: {e}")
            return {'has_active_premium': False, 'is_premium': False, 'premium_until': None}
    
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
    
    def get_user_reminders(self, user_id, limit=50):
        """Получение списка напоминаний пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute('''
                SELECT id, title, amount, payment_date, recurrence, is_active
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
                # Преобразуем payment_date в строку если нужно
                payment_date = reminder['payment_date']
                if hasattr(payment_date, 'strftime'):
                    payment_date = payment_date.strftime('%Y-%m-%d')
                
                result.append({
                    'id': reminder['id'],
                    'title': reminder['title'] or 'Без названия',
                    'amount': float(reminder['amount']) if reminder['amount'] else 0.0,
                    'payment_date': payment_date,
                    'recurrence': reminder['recurrence'] or 'once',
                    'is_active': bool(reminder['is_active'])
                })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_user_reminders: {e}")
            return []
    
    def delete_reminder(self, user_id, reminder_id):
        """Удаление напоминания пользователя"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
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
                    premium_until = %s
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
                    premium_until = NULL
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
            
            # Преобразуем дату если нужно
            if isinstance(payment_date, str):
                try:
                    # Убедимся что дата в правильном формате
                    datetime.strptime(payment_date, '%Y-%m-%d')
                except ValueError:
                    # Если дата в другом формате, преобразуем
                    try:
                        dt = datetime.strptime(payment_date, '%d.%m.%Y')
                        payment_date = dt.strftime('%Y-%m-%d')
                    except:
                        payment_date = datetime.now().strftime('%Y-%m-%d')
            
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
                WHERE DATE(r.payment_date) = %s 
                AND r.is_active = TRUE
            ''', (target_date,))
            
            reminders = cursor.fetchall()
            cursor.close()
            
            return reminders
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_reminders_for_notification: {e}")
            return []
    
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
                        yookassa_payment_id = %s
                    WHERE id = %s
                ''', (status, yookassa_payment_id, payment_id))
                
                # Получаем информацию о платеже для активации премиума
                cursor.execute('''
                    SELECT user_id, period_days 
                    FROM payments 
                    WHERE id = %s
                ''', (payment_id,))
                
                result = cursor.fetchone()
                if result:
                    user_id, period_days = result
                    self.activate_premium(user_id, period_days)
            else:
                cursor.execute('''
                    UPDATE payments 
                    SET status = %s, 
                        yookassa_payment_id = %s
                    WHERE id = %s
                ''', (status, yookassa_payment_id, payment_id))
            
            updated = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            
            return updated
            
        except Exception as e:
            logger.error(f"❌ Ошибка update_payment_status: {e}")
            return False

# Создаем глобальный экземпляр базы данных
db = Database()
