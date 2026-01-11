# run_bot.py
import os
import sys
import time
import subprocess
import atexit

def cleanup():
    """Функция очистки при завершении"""
    print("\n🛑 Завершение бота...")
    # Здесь можно добавить дополнительную очистку

def main():
    """Основная функция запуска"""
    print("=" * 50)
    print("🛡️  ЗАЩИЩЕННЫЙ ЗАПУСК БОТА")
    print("=" * 50)
    
    # Проверяем, не запущен ли уже бот
    try:
        # Ищем процессы python bot.py
        result = subprocess.run(
            ['pgrep', '-f', 'python.*bot\.py'],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            pids = result.stdout.strip().split('\n')
            print(f"⚠️ Найдено {len(pids)} запущенных ботов:")
            for pid in pids:
                if pid and pid != str(os.getpid()):
                    print(f"   • Останавливаем процесс {pid}")
                    subprocess.run(['kill', '-9', pid])
                    time.sleep(1)
    except Exception as e:
        print(f"⚠️ Не удалось проверить процессы: {e}")
    
    # Регистрируем функцию очистки
    atexit.register(cleanup)
    
    # Запускаем основной бот
    print("🚀 Запускаем основной бот...")
    os.execvp('python', ['python', 'bot.py'])

if __name__ == "__main__":
    main()
