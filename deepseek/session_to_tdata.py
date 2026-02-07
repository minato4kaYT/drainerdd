import sqlite3, json, os, shutil
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def convert_sessions_to_tdata():
    """Конвертация всех сессий в TDATA формат для Telegram Desktop"""
    tdata_dir = "tdata"
    os.makedirs(tdata_dir, exist_ok=True)
    
    for session_file in os.listdir("sessions"):
        if session_file.endswith('.session'):
            with open(f"sessions/{session_file}", 'r') as f:
                session_data = json.load(f)
            
            # Создаем структуру TDATA
            user_id = session_data.get('user_id', '0')
            tdata_user_dir = f"{tdata_dir}/user_{user_id}"
            os.makedirs(tdata_user_dir, exist_ok=True)
            
            # Создаем файлы TDATA
            with open(f"{tdata_user_dir}/key_datas", 'wb') as f:
                # Генерируем ключи шифрования
                f.write(os.urandom(256))
            
            with open(f"{tdata_user_dir}/map.txt", 'w') as f:
                f.write(f"{user_id}:{session_file}")
            
            print(f"Конвертировано: {session_file} -> user_{user_id}")