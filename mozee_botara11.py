import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import nest_asyncio
import os
import pickle
import re
import time
from datetime import datetime

# Разрешаем запускать asyncio
nest_asyncio.apply()

# ========== ТВОИ ДАННЫЕ ==========
BOT_TOKEN = "7748547682:AAEPJyZW-GPGMqFLKssn6dpZnQZ5724RPfs"  # Твой токен от @BotFather

# Структура данных пользователя со значениями по умолчанию
DEFAULT_USER_DATA = {
    'api_id': None,
    'api_hash': None,
    'phone': None,
    'client': None,
    'chats': [],
    'is_sending': False,
    'auth_step': None,
    'awaiting': None,
    'temp_data': {},
    'last_message': None,
    'last_message_time': None,
    'flood_wait_until': {},
    'is_authenticated': False,
    'parse_results': [],
    'sending_task': None,
}

# Словарь для хранения данных пользователей
user_data = {}
sending_tasks = {}

# Файл для сохранения данных
DATA_FILE = 'bot_data.pickle'
# ===============================

# Загрузка данных при старте
def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'rb') as f:
                loaded_data = pickle.load(f)
                user_data = {}
                for user_id, data in loaded_data.items():
                    user_data[user_id] = DEFAULT_USER_DATA.copy()
                    for key, value in data.items():
                        if key in user_data[user_id] and key not in ['client', 'sending_task']:
                            user_data[user_id][key] = value
                print(f"✅ Загружены данные для {len(user_data)} пользователей")
        except Exception as e:
            print(f"❌ Ошибка загрузки данных: {e}")
            user_data = {}
    else:
        user_data = {}
        print("📁 Файл данных не найден, создан новый словарь")

# Сохранение данных
def save_data():
    try:
        data_to_save = {}
        for user_id, user_info in user_data.items():
            data_to_save[user_id] = {k: v for k, v in user_info.items() if k not in ['client', 'sending_task']}
        
        with open(DATA_FILE, 'wb') as f:
            pickle.dump(data_to_save, f)
            
        print(f"💾 Сохранены данные для {len(user_data)} пользователей")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

# Инициализация данных пользователя
def init_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = DEFAULT_USER_DATA.copy()
        save_data()
        print(f"👤 Создан новый пользователь с ID: {user_id}")
    return user_data[user_id]

# Клавиатура с кнопкой "Назад"
def get_back_keyboard(back_callback='back_to_menu'):
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=back_callback)]]
    return InlineKeyboardMarkup(keyboard)

# Функция для проверки авторизован ли пользователь
def is_user_authenticated(user):
    client = user.get('client')
    if client and client.is_connected():
        return True
    if user.get('is_authenticated') and user.get('api_id') and user.get('phone'):
        return True
    return False

# Клавиатура главного меню (динамическая)
def get_main_keyboard(user):
    authenticated = is_user_authenticated(user)
    
    if not authenticated:
        keyboard = [
            [InlineKeyboardButton("🔑 Добавить аккаунт", callback_data='add_account')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🔑 Добавить еще аккаунт(если был акаунт тогда кинь данные повторно для авторизации)", callback_data='add_account')],
            [InlineKeyboardButton("📝 Добавить чаты", callback_data='add_chat')],
            [InlineKeyboardButton("📋 Список чатов", callback_data='list_chats')],
            [InlineKeyboardButton("❌ Удалить чаты", callback_data='remove_chats_menu')],
            [InlineKeyboardButton("👥 Парсинг пользователей", callback_data='parse_menu')],
            [InlineKeyboardButton("ℹ️ Статус", callback_data='status')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')]
        ]
        
        spam_buttons = []
        spam_buttons.append(InlineKeyboardButton("🚀 Запустить рассылку", callback_data='start_spam'))
        
        if user.get('is_sending'):
            spam_buttons.append(InlineKeyboardButton("⏸ Остановить рассылку", callback_data='stop_spam'))
        
        keyboard.append(spam_buttons)
    
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для выбора сообщения
def get_message_choice_keyboard(has_last_message=False):
    keyboard = []
    if has_last_message:
        keyboard.append([InlineKeyboardButton("📋 Использовать последнее сообщение", callback_data='use_last_message')])
    keyboard.append([InlineKeyboardButton("✏️ Ввести новое сообщение", callback_data='new_message')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для меню парсинга
def get_parse_keyboard():
    keyboard = [
        [InlineKeyboardButton("👥 Все участники чата", callback_data='parse_participants')],
        [InlineKeyboardButton("💬 Из последних сообщений", callback_data='parse_messages_custom')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для выбора количества сообщений
def get_message_count_keyboard():
    keyboard = [
        [InlineKeyboardButton("500 сообщений", callback_data='parse_count_500')],
        [InlineKeyboardButton("1000 сообщений", callback_data='parse_count_1000')],
        [InlineKeyboardButton("2000 сообщений", callback_data='parse_count_2000')],
        [InlineKeyboardButton("3000 сообщений", callback_data='parse_count_3000')],
        [InlineKeyboardButton("5000 сообщений", callback_data='parse_count_5000')],
        [InlineKeyboardButton("✏️ Ввести свое количество", callback_data='parse_count_custom')],
        [InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция для парсинга чатов из текста
def parse_chats_from_text(text):
    lines = text.strip().split('\n')
    chats = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        line = re.sub(r'^[\d\-*•.]+\s*', '', line)
        
        if line:
            parts = re.split(r'[,\s]+', line)
            for part in parts:
                part = part.strip()
                if part and len(part) > 2:
                    chats.append(part)
    
    return chats

# Функция для форматирования времени ожидания
def format_wait_time(seconds):
    if seconds < 60:
        return f"{seconds} секунд"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} минут"
    else:
        hours = seconds // 3600
        return f"{hours} часов"

# Функция для парсинга участников чата
async def parse_chat_participants(client, chat_entity):
    usernames = []
    count = 0
    
    try:
        participants = await client.get_participants(chat_entity)
        
        for user in participants:
            if user.username:
                usernames.append(f"@{user.username}")
            elif user.first_name or user.last_name:
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                usernames.append(f"{name} (id: {user.id})")
            
            count += 1
            if count % 100 == 0:
                print(f"📊 Обработано {count} участников...")
    
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return []
    
    return usernames

# Функция для парсинга из последних сообщений
async def parse_from_messages(client, chat_entity, message_limit=3000):
    usernames = []
    unique_users = set()
    count = 0
    
    try:
        async for message in client.iter_messages(chat_entity, limit=message_limit):
            if message.sender and message.sender.id not in unique_users:
                unique_users.add(message.sender.id)
                
                if message.sender.username:
                    username = f"@{message.sender.username}"
                    usernames.append(username)
                elif message.sender.first_name or message.sender.last_name:
                    name = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                    usernames.append(f"{name} (id: {message.sender.id})")
                
                count += 1
                if count % 50 == 0:
                    print(f"📊 Найдено {count} уникальных пользователей...")
    
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return []
    
    return usernames

# Функция для отправки результатов в сохраненные
async def send_parse_results_to_saved(client, usernames, method_name, chat_title):
    if not usernames:
        return False
    
    chunk_size = 50
    total_chunks = (len(usernames) + chunk_size - 1) // chunk_size
    
    info_message = (
        f"📊 **РЕЗУЛЬТАТ ПАРСИНГА**\n\n"
        f"📌 **Чат:** {chat_title}\n"
        f"📋 **Метод:** {method_name}\n"
        f"👥 **Всего найдено:** {len(usernames)}\n"
        f"📦 **Частей:** {total_chunks}\n"
        f"⏰ **Время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'='*40}"
    )
    
    await client.send_message('me', info_message)
    await asyncio.sleep(1)
    
    for i in range(0, len(usernames), chunk_size):
        chunk = usernames[i:i + chunk_size]
        chunk_num = i // chunk_size + 1
        
        message = f"📋 **ЧАСТЬ {chunk_num}/{total_chunks}**\n"
        message += "=" * 40 + "\n\n"
        
        for idx, username in enumerate(chunk, 1):
            message += f"{idx}. {username}\n"
        
        message += f"\n📊 Всего в части: {len(chunk)}"
        
        await client.send_message('me', message)
        print(f"✅ Отправлена часть {chunk_num}")
        
        await asyncio.sleep(1)
    
    return True

# Функция для остановки рассылки
async def stop_sending(user_id):
    if user_id in sending_tasks and sending_tasks[user_id]:
        task = sending_tasks[user_id]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        del sending_tasks[user_id]
    
    if user_id in user_data:
        user_data[user_id]['is_sending'] = False
        save_data()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = init_user(user_id)
    
    authenticated = is_user_authenticated(user)
    
    if not authenticated:
        welcome_text = (
            "🌟 **Добро пожаловать в Mozee Bot!** 🌟\n\n"
            "Это бот для безопасной рассылки сообщений в Telegram чаты.\n\n"
            "🔰 **Для начала работы нужно:**\n"
            "1️⃣ Нажать кнопку «🔑 Добавить аккаунт»\n"
            "2️⃣ Ввести API данные с my.telegram.org\n"
            "3️⃣ Ввести номер телефона и код\n\n"
            "❓ Если нужна помощь - нажми «❓ Помощь»"
        )
    else:
        try:
            client = user.get('client')
            if client and client.is_connected():
                me = await client.get_me()
                user_info = f"@{me.username}" if me.username else f"{me.first_name}"
            else:
                user_info = "Ваш аккаунт"
        except:
            user_info = "Ваш аккаунт"
        
        chats_count = len(user.get('chats', []))
        
        welcome_text = (
            f"🌟 **Добро пожаловать, {user_info}!** 🌟\n\n"
            f"📊 **Ваша статистика:**\n"
            f"• 📋 Чатов в списке: {chats_count}\n"
            f"• 📨 Последнее сообщение: {'есть' if user.get('last_message') else 'нет'}\n\n"
            f"🔰 **Доступные действия:**\n"
            f"• Добавить новые чаты для рассылки\n"
            f"• Запустить рассылку с сохраненным сообщением\n"
            f"• Парсинг пользователей из чатов\n"
            f"• Добавить еще один аккаунт"
        )
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(user),
        parse_mode='Markdown'
    )

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = init_user(user_id)
    
    help_text = (
        "❓ **Помощь по боту** ❓\n\n"
        "🔑 **Добавить аккаунт**\n"
        "1. Получи API ID и Hash на my.telegram.org/apps\n"
        "2. Отправь их через пробел\n"
        "3. Введи номер телефона\n"
        "4. Введи код подтверждения\n\n"
        "📝 **Добавить чаты**\n"
        "Можно добавить несколько чатов одновременно!\n\n"
        "👥 **Парсинг пользователей**\n"
        "• Все участники чата\n"
        "• Из последних сообщений\n"
        "• Результат в сохраненные\n\n"
        "🚀 **Рассылка**\n"
        "• Интервал 60 секунд\n"
        "• Можно остановить кнопкой\n\n"
        "❓ Если что-то не работает - @mozee00"
    )
    
    await update.message.reply_text(
        help_text, 
        parse_mode='Markdown',
        reply_markup=get_main_keyboard(user)
    )

# Обработка нажатий кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = init_user(user_id)
    
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        await query.edit_message_text(
            "❓ **Помощь по боту**\n\n"
            "Основные функции:\n"
            "• Добавление аккаунта Telegram\n"
            "• Добавление чатов для рассылки\n"
            "• Запуск безопасной рассылки\n"
            "• Парсинг пользователей из чатов\n\n"
            "Если что-то не работает - @mozee00",
            reply_markup=get_main_keyboard(user),
            parse_mode='Markdown'
        )
    
    elif query.data == 'add_account':
        authenticated = is_user_authenticated(user)
        
        if authenticated:
            keyboard = [
                [InlineKeyboardButton("✅ Да, добавить еще один", callback_data='confirm_add_another')],
                [InlineKeyboardButton("❌ Нет, оставить текущий", callback_data='back_to_menu')]
            ]
            await query.edit_message_text(
                "🔑 **У вас уже есть подключенный аккаунт**\n\n"
                "Желаете добавить еще один аккаунт?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "🔑 **Добавление аккаунта**\n\n"
                "1️⃣ Отправь мне **API ID** и **API Hash** через пробел.\n"
                "Получить их можно здесь: https://my.telegram.org/apps\n\n"
                "📝 **Пример:**\n"
                "`1234567 a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5`\n\n"
                "⚠️ Эти данные нужны для подключения к Telegram API",
                reply_markup=get_back_keyboard('back_to_menu')
            )
            user['auth_step'] = 'waiting_api'
            save_data()
    
    elif query.data == 'confirm_add_another':
        await query.edit_message_text(
            "🔑 **Добавление еще одного аккаунта**\n\n"
            "1️⃣ Отправь мне **API ID** и **API Hash** нового аккаунта.\n\n"
            "📝 **Пример:**\n"
            "`1234567 a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5`",
            reply_markup=get_back_keyboard('back_to_menu')
        )
        user['auth_step'] = 'waiting_api_another'
        save_data()
        
    elif query.data == 'add_chat':
        authenticated = is_user_authenticated(user)
        if not authenticated:
            await query.edit_message_text(
                "❌ Сначала добавь аккаунт!",
                reply_markup=get_main_keyboard(user)
            )
            return
            
        await query.edit_message_text(
            "📝 **Добавление чатов**\n\n"
            "Отправь мне список чатов в любом формате:\n"
            "• Каждый с новой строки\n"
            "• Через запятую\n"
            "• С нумерацией\n\n"
            "📋 **Пример:**\n"
            "@channel1\n"
            "@channel2\n"
            "-1001234567890\n"
            "https://t.me/joinchat/abc123\n\n"
            "✅ Я автоматически распознаю все чаты!",
            reply_markup=get_back_keyboard('back_to_menu')
        )
        user['awaiting'] = 'chat_input'
        save_data()
        
    elif query.data == 'list_chats':
        chats = user.get('chats', [])
        if not chats:
            await query.edit_message_text("📋 Список чатов пуст.", reply_markup=get_main_keyboard(user))
        else:
            chats_text = "📋 **Список чатов:**\n\n"
            for i, chat in enumerate(chats, 1):
                chats_text += f"{i}. `{chat}`\n"
            await query.edit_message_text(chats_text, reply_markup=get_main_keyboard(user), parse_mode='Markdown')
            
    elif query.data == 'remove_chats_menu':
        chats = user.get('chats', [])
        if not chats:
            await query.edit_message_text("📋 Список чатов пуст.", reply_markup=get_main_keyboard(user))
        else:
            keyboard = []
            for i, chat in enumerate(chats):
                short_chat = chat[:20] + "..." if len(chat) > 20 else chat
                keyboard.append([InlineKeyboardButton(f"{i+1}. {short_chat}", callback_data=f'del_{i}')])
            
            keyboard.append([InlineKeyboardButton("🗑 Удалить все", callback_data='del_all')])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
            
            await query.edit_message_text(
                "🗑 **Удаление чатов**\n\nВыбери чат для удаления:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    elif query.data == 'del_all':
        user['chats'] = []
        save_data()
        await query.edit_message_text("✅ Все чаты удалены!", reply_markup=get_main_keyboard(user))
            
    elif query.data.startswith('del_') and query.data != 'del_all':
        index = int(query.data.split('_')[1])
        chats = user.get('chats', [])
        if 0 <= index < len(chats):
            removed = chats.pop(index)
            save_data()
            await query.edit_message_text(f"✅ Чат `{removed}` удален!", reply_markup=get_main_keyboard(user), parse_mode='Markdown')
    
    elif query.data == 'parse_menu':
        authenticated = is_user_authenticated(user)
        if not authenticated:
            await query.edit_message_text(
                "❌ Сначала добавь аккаунт!",
                reply_markup=get_main_keyboard(user)
            )
            return
        
        await query.edit_message_text(
            "👥 **Парсинг пользователей**\n\n"
            "Выбери метод парсинга:\n\n"
            "1️⃣ **Все участники чата** - получить список всех участников\n"
            "2️⃣ **Из последних сообщений** - получить активных пользователей (можно выбрать количество)\n\n"
            "📌 Результат будет отправлен в **Сохраненные сообщения**",
            reply_markup=get_parse_keyboard()
        )
    
    elif query.data == 'parse_participants':
        await query.edit_message_text(
            "🔗 **Отправь ссылку на чат**\n\n"
            "Например:\n"
            "• @channel_name\n"
            "• https://t.me/joinchat/abc123\n"
            "• -1001234567890\n\n"
            "⚠️ Ты должен быть участником этого чата!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
        )
        user['awaiting'] = 'parse_chat_link'
        user['temp_data'] = {'parse_method': 'participants'}
        save_data()
    
    elif query.data == 'parse_messages_custom':
        await query.edit_message_text(
            "📊 **Выбери количество сообщений** для парсинга:",
            reply_markup=get_message_count_keyboard()
        )
    
    elif query.data.startswith('parse_count_'):
        if query.data == 'parse_count_custom':
            await query.edit_message_text(
                "✏️ **Введи количество сообщений** (только цифры):\n\n"
                "Например: `5000`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
            )
            user['awaiting'] = 'parse_count_input'
            save_data()
        else:
            count = int(query.data.split('_')[2])
            await query.edit_message_text(
                f"✅ Выбрано: **{count} сообщений**\n\n"
                f"🔗 **Теперь отправь ссылку на чат**\n\n"
                f"Например:\n"
                f"• @channel_name\n"
                f"• https://t.me/joinchat/abc123\n"
                f"• -1001234567890",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
            )
            user['awaiting'] = 'parse_chat_link'
            user['temp_data'] = {'parse_method': 'messages', 'message_count': count}
            save_data()
        
    elif query.data == 'status':
        status_text = "📊 **СТАТУС СИСТЕМЫ**\n\n"
        
        authenticated = is_user_authenticated(user)
        client = user.get('client')
        
        if authenticated and client and client.is_connected():
            try:
                me = await client.get_me()
                status_text += f"✅ **Аккаунт:** {me.first_name}\n"
                if me.username:
                    status_text += f"📱 **Username:** @{me.username}\n"
                status_text += f"🆔 **ID:** `{me.id}`\n"
            except:
                status_text += "✅ **Аккаунт:** Подключен\n"
        else:
            status_text += "❌ **Аккаунт:** Не подключен\n"
        
        chats = user.get('chats', [])
        
        status_text += f"\n📋 **Чатов в списке:** {len(chats)}"
        status_text += f"\n🚦 **Рассылка:** {'🔴 Активна' if user.get('is_sending') else '⚫ Остановлена'}"
        
        last_message = user.get('last_message')
        if last_message:
            status_text += f"\n\n📨 **Последнее сообщение:**\n{last_message[:50]}{'...' if len(last_message) > 50 else ''}"
        
        flood_wait = user.get('flood_wait_until', {})
        now = time.time()
        active_floods = {chat: wait_time for chat, wait_time in flood_wait.items() if wait_time > now}
        if active_floods:
            status_text += f"\n\n⚠️ **Чатов в флуд-контроле:** {len(active_floods)}"
        
        await query.edit_message_text(status_text, reply_markup=get_main_keyboard(user), parse_mode='Markdown')
        
    elif query.data == 'start_spam':
        authenticated = is_user_authenticated(user)
        if not authenticated:
            await query.edit_message_text(
                "❌ Сначала добавь аккаунт!",
                reply_markup=get_main_keyboard(user)
            )
            return
            
        chats = user.get('chats', [])
        if not chats:
            await query.edit_message_text(
                "❌ Добавь хотя бы один чат!",
                reply_markup=get_main_keyboard(user)
            )
            return
        
        if user.get('is_sending'):
            await query.edit_message_text("⚠️ Рассылка уже запущена!", reply_markup=get_main_keyboard(user))
            return
        
        has_last_message = user.get('last_message') is not None
        await query.edit_message_text(
            "✏️ **Выбери сообщение для рассылки:**",
            reply_markup=get_message_choice_keyboard(has_last_message)
        )
        
    elif query.data == 'use_last_message':
        last_message = user.get('last_message')
        if not last_message:
            await query.edit_message_text("❌ Нет сохраненного сообщения!", reply_markup=get_main_keyboard(user))
            return
        
        await start_spam_with_message(update, context, user, last_message)
        
    elif query.data == 'new_message':
        await query.edit_message_text(
            "✏️ **Введи текст сообщения** для рассылки:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]])
        )
        user['awaiting'] = 'message_input'
        save_data()
        
    elif query.data == 'stop_spam':
        if user.get('is_sending'):
            await stop_sending(user_id)
            
            await query.edit_message_text(
                "⏸ **Рассылка остановлена!**",
                reply_markup=get_main_keyboard(user)
            )
            
            await context.bot.send_message(
                chat_id=user_id,
                text="🔙 Возврат в меню.",
                reply_markup=get_main_keyboard(user)
            )
        else:
            await query.edit_message_text(
                "ℹ️ Рассылка не запущена.",
                reply_markup=get_main_keyboard(user)
            )
            
    elif query.data in ['back_to_menu', 'cancel']:
        user['auth_step'] = None
        user['awaiting'] = None
        user['temp_data'] = {}
        save_data()
        await query.edit_message_text(
            "🔙 **Главное меню:**", 
            reply_markup=get_main_keyboard(user), 
            parse_mode='Markdown'
        )

# Обработка текстовых сообщений
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = init_user(user_id)
    
    text = update.message.text
    
    auth_step = user.get('auth_step')
    awaiting = user.get('awaiting')
    
    if auth_step in ['waiting_api', 'waiting_api_another']:
        try:
            api_parts = text.split()
            if len(api_parts) == 2:
                api_id, api_hash = api_parts
                
                if not api_id.isdigit():
                    await update.message.reply_text(
                        "❌ API ID должно быть числом. Попробуй еще раз.", 
                        reply_markup=get_back_keyboard('back_to_menu')
                    )
                    return
                
                user['api_id'] = api_id
                user['api_hash'] = api_hash
                
                user['auth_step'] = 'waiting_phone'
                save_data()
                
                await update.message.reply_text(
                    "✅ API данные сохранены!\n\n"
                    "📱 **Шаг 2:** Отправь свой **номер телефона** в международном формате.\n"
                    "Например: `+380991234567`",
                    reply_markup=get_back_keyboard('back_to_menu')
                )
            else:
                await update.message.reply_text(
                    "❌ Неверный формат. Отправь: API_ID API_HASH", 
                    reply_markup=get_back_keyboard('back_to_menu')
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)}", 
                reply_markup=get_back_keyboard('back_to_menu')
            )
            
    elif auth_step == 'waiting_phone':
        try:
            phone = text.strip()
            
            if not phone.startswith('+'):
                phone = '+' + phone
            
            user['phone'] = phone
            
            client = TelegramClient(
                f"session_{user_id}_{phone.replace('+', '')}", 
                int(user['api_id']), 
                user['api_hash']
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                
                user['client'] = client
                user['auth_step'] = 'waiting_code'
                save_data()
                
                await update.message.reply_text(
                    "✅ **Код подтверждения отправлен!**\n"
                    "Введи его сюда (только цифры):",
                    reply_markup=get_back_keyboard('back_to_menu')
                )
            else:
                user['client'] = client
                user['is_authenticated'] = True
                me = await client.get_me()
                user['auth_step'] = None
                save_data()
                
                await update.message.reply_text(
                    f"✅ **Вы уже авторизованы как {me.first_name}!**",
                    reply_markup=get_main_keyboard(user)
                )
                
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)}", 
                reply_markup=get_back_keyboard('back_to_menu')
            )
            
    elif auth_step == 'waiting_code':
        try:
            code = text.strip()
            code = re.sub(r'\D', '', code)
            
            client = user.get('client')
            if not client:
                await update.message.reply_text(
                    "❌ Ошибка: клиент не найден. Начни заново.", 
                    reply_markup=get_main_keyboard(user)
                )
                user['auth_step'] = None
                save_data()
                return
                
            phone = user.get('phone')
            
            try:
                await client.sign_in(phone, code)
                
                me = await client.get_me()
                user['is_authenticated'] = True
                user['auth_step'] = None
                save_data()
                
                await update.message.reply_text(
                    f"✅ **АВТОРИЗАЦИЯ УСПЕШНА!**\n\n"
                    f"Добро пожаловать, {me.first_name}!",
                    reply_markup=get_main_keyboard(user)
                )
                
            except SessionPasswordNeededError:
                user['auth_step'] = 'waiting_password'
                save_data()
                await update.message.reply_text(
                    "🔐 **Двухфакторная авторизация**\n\n"
                    "Введи свой пароль:",
                    reply_markup=get_back_keyboard('back_to_menu')
                )
                
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка при вводе кода: {str(e)}", 
                reply_markup=get_back_keyboard('back_to_menu')
            )
            
    elif auth_step == 'waiting_password':
        try:
            password = text.strip()
            client = user.get('client')
            
            if not client:
                await update.message.reply_text(
                    "❌ Ошибка: клиент не найден. Начни заново.", 
                    reply_markup=get_main_keyboard(user)
                )
                user['auth_step'] = None
                save_data()
                return
            
            await client.sign_in(password=password)
            
            me = await client.get_me()
            user['is_authenticated'] = True
            user['auth_step'] = None
            save_data()
            
            await update.message.reply_text(
                f"✅ **АВТОРИЗАЦИЯ УСПЕШНА!**\n\n"
                f"Добро пожаловать, {me.first_name}!",
                reply_markup=get_main_keyboard(user)
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)}", 
                reply_markup=get_back_keyboard('back_to_menu')
            )
    
    elif awaiting == 'chat_input':
        new_chats = parse_chats_from_text(text)
        
        if new_chats:
            current_chats = user.get('chats', [])
            
            unique_chats = []
            for chat in new_chats:
                if chat not in current_chats:
                    unique_chats.append(chat)
            
            if unique_chats:
                user['chats'] = current_chats + unique_chats
                save_data()
                
                await update.message.reply_text(
                    f"✅ **Добавлено чатов:** {len(unique_chats)}\n"
                    f"📋 **Всего в списке:** {len(user['chats'])}\n\n"
                    f"Новые чаты:\n" + "\n".join([f"• `{c}`" for c in unique_chats[:5]]) +
                    (f"\n...и еще {len(unique_chats)-5}" if len(unique_chats) > 5 else ""),
                    reply_markup=get_main_keyboard(user),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "⚠️ Все эти чаты уже есть в списке!",
                    reply_markup=get_main_keyboard(user)
                )
        else:
            await update.message.reply_text(
                "❌ Не удалось найти ни одного чата в тексте. Попробуй еще раз.",
                reply_markup=get_main_keyboard(user)
            )
        
        user['awaiting'] = None
        save_data()
    
    elif awaiting == 'message_input':
        await start_spam_with_message(update, context, user, text)
    
    elif awaiting == 'parse_count_input':
        try:
            count = int(text.strip())
            if count <= 0:
                await update.message.reply_text(
                    "❌ Количество сообщений должно быть больше 0!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
                )
                return
            
            await update.message.reply_text(
                f"✅ Выбрано: **{count} сообщений**\n\n"
                f"🔗 **Теперь отправь ссылку на чат**\n\n"
                f"Например:\n"
                f"• @channel_name\n"
                f"• https://t.me/joinchat/abc123\n"
                f"• -1001234567890",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
            )
            user['awaiting'] = 'parse_chat_link'
            user['temp_data'] = {'parse_method': 'messages', 'message_count': count}
            save_data()
            
        except ValueError:
            await update.message.reply_text(
                "❌ Пожалуйста, введи число!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='parse_menu')]])
            )
    
    elif awaiting == 'parse_chat_link':
        chat_link = text.strip()
        
        temp_data = user.get('temp_data', {})
        parse_method = temp_data.get('parse_method', 'participants')
        message_count = temp_data.get('message_count', 3000)
        
        status_msg = await update.message.reply_text(
            "⏳ **Начинаю парсинг...**\n"
            "Это может занять некоторое время.",
            parse_mode='Markdown'
        )
        
        client = user.get('client')
        if not client:
            await status_msg.edit_text(
                "❌ Ошибка: клиент не найден!",
                reply_markup=get_main_keyboard(user)
            )
            user['awaiting'] = None
            user['temp_data'] = {}
            save_data()
            return
        
        try:
            try:
                chat_entity = await client.get_entity(chat_link)
                chat_title = getattr(chat_entity, 'title', 'личный чат')
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Не удалось найти чат: {str(e)}\n\n"
                    f"Убедись, что ты:\n"
                    f"• В участниках чата\n"
                    f"• Правильно ввел ссылку",
                    reply_markup=get_main_keyboard(user)
                )
                user['awaiting'] = None
                user['temp_data'] = {}
                save_data()
                return
            
            await status_msg.edit_text(
                f"✅ Чат найден: **{chat_title}**\n\n"
                f"⏳ Начинаю сбор данных...",
                parse_mode='Markdown'
            )
            
            if parse_method == 'participants':
                usernames = await parse_chat_participants(client, chat_entity)
                method_name = "Все участники чата"
            else:
                usernames = await parse_from_messages(client, chat_entity, message_count)
                method_name = f"Из последних {message_count} сообщений"
            
            if usernames:
                await status_msg.edit_text(
                    f"✅ Найдено пользователей: **{len(usernames)}**\n\n"
                    f"📤 Отправляю в сохраненные сообщения...",
                    parse_mode='Markdown'
                )
                
                success = await send_parse_results_to_saved(client, usernames, method_name, chat_title)
                
                if success:
                    await status_msg.edit_text(
                        f"✅ **ПАРСИНГ ЗАВЕРШЕН!**\n\n"
                        f"📊 **Результат:**\n"
                        f"• Чат: **{chat_title}**\n"
                        f"• Метод: **{method_name}**\n"
                        f"• Найдено: **{len(usernames)}** пользователей\n"
                        f"• Отправлено в: **Сохраненные сообщения**\n\n"
                        f"📌 Проверь раздел «Сохраненные» в Telegram!",
                        reply_markup=get_main_keyboard(user),
                        parse_mode='Markdown'
                    )
                else:
                    await status_msg.edit_text(
                        "❌ Ошибка при отправке результатов!",
                        reply_markup=get_main_keyboard(user)
                    )
            else:
                await status_msg.edit_text(
                    "❌ Не найдено ни одного пользователя в этом чате!",
                    reply_markup=get_main_keyboard(user)
                )
            
        except Exception as e:
            await status_msg.edit_text(
                f"❌ Ошибка парсинга: {str(e)}",
                reply_markup=get_main_keyboard(user)
            )
        
        user['awaiting'] = None
        user['temp_data'] = {}
        save_data()

# Функция для запуска рассылки с сообщением
async def start_spam_with_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user, message_text):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    message = update.message if hasattr(update, 'message') else None
    user_id = update.effective_user.id
    
    if user.get('is_sending'):
        if query:
            await query.edit_message_text("⚠️ Рассылка уже запущена!")
        elif message:
            await message.reply_text("⚠️ Рассылка уже запущена!")
        return
    
    user['last_message'] = message_text
    user['last_message_time'] = time.time()
    user['is_sending'] = True
    user['awaiting'] = None
    save_data()
    
    chats = user.get('chats', [])
    client = user.get('client')
    
    if not client:
        if query:
            await query.edit_message_text(
                "❌ Ошибка: клиент не найден!", 
                reply_markup=get_main_keyboard(user)
            )
        elif message:
            await message.reply_text(
                "❌ Ошибка: клиент не найден!", 
                reply_markup=get_main_keyboard(user)
            )
        user['is_sending'] = False
        save_data()
        return
    
    if query:
        await query.edit_message_text(
            f"🚀 **ЗАПУСК РАССЫЛКИ**\n\n"
            f"📨 **Сообщение:**\n{message_text[:100]}{'...' if len(message_text) > 100 else ''}\n\n"
            f"📊 **Чатов:** {len(chats)}\n"
            f"⏱ **Интервал:** 60 секунд\n"
            f"⏳ **Время:** ~{len(chats) * 60 // 60} мин",
            parse_mode='Markdown'
        )
    
    await context.bot.send_message(
        chat_id=user_id,
        text="🔄 **Меню обновлено** - кнопка остановки активна!",
        reply_markup=get_main_keyboard(user)
    )
    
    task = asyncio.create_task(send_spam_task(user_id, context, message_text))
    sending_tasks[user_id] = task

# Отдельная функция для выполнения рассылки
async def send_spam_task(user_id, context, message_text):
    user = user_data.get(user_id)
    if not user:
        return
    
    client = user.get('client')
    chats = user.get('chats', [])
    flood_wait = user.get('flood_wait_until', {})
    
    status_msg = await context.bot.send_message(
        chat_id=user_id,
        text="⏳ Подготовка..."
    )
    
    successful = 0
    failed = 0
    skipped = 0
    failed_chats = []
    
    try:
        for i, chat in enumerate(chats):
            if not user.get('is_sending'):
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏸ Остановлено. Отправлено: {successful}"
                )
                break
            
            now = time.time()
            if chat in flood_wait and flood_wait[chat] > now:
                wait_seconds = int(flood_wait[chat] - now)
                wait_time_str = format_wait_time(wait_seconds)
                skipped += 1
                failed_chats.append(f"{chat}: ⏳ флуд-контроль еще {wait_time_str}")
                
                await status_msg.edit_text(
                    f"⏳ **Пропущен чат {i+1}/{len(chats)}**\n"
                    f"⚠ Чат `{chat}` в флуд-контроле\n"
                    f"⏱ Ждем {wait_time_str}\n\n"
                    f"✅ Успешно: {successful}\n"
                    f"❌ Ошибок: {failed}\n"
                    f"⏸ Пропущено: {skipped}",
                    parse_mode='Markdown'
                )
                
                if i < len(chats) - 1 and user.get('is_sending'):
                    for s in range(60, 0, -1):
                        if not user.get('is_sending'):
                            break
                        if s % 10 == 0 or s <= 5:
                            await status_msg.edit_text(
                                f"⏳ **Следующее сообщение через {s}с**\n"
                                f"📊 Прогресс: {i+1}/{len(chats)}\n"
                                f"✅ Успешно: {successful}\n"
                                f"❌ Ошибок: {failed}\n"
                                f"⏸ Пропущено: {skipped}"
                            )
                        await asyncio.sleep(1)
                continue
                    
            try:
                await client.send_message(chat, message_text)
                successful += 1
                
                percent = int((i + 1) / len(chats) * 100)
                await status_msg.edit_text(
                    f"⏳ **Прогресс:** {percent}% ({i+1}/{len(chats)})\n"
                    f"✅ **Успешно:** {successful}\n"
                    f"❌ **Ошибок:** {failed}\n"
                    f"⏸ **Пропущено:** {skipped}"
                )
                        
            except FloodWaitError as e:
                wait_seconds = e.seconds
                flood_wait[chat] = time.time() + wait_seconds
                user['flood_wait_until'] = flood_wait
                save_data()
                
                wait_time_str = format_wait_time(wait_seconds)
                failed += 1
                failed_chats.append(f"{chat}: ⚠ флуд-контроль на {wait_time_str}")
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠ **Флуд-контроль в чате** `{chat}`\n"
                         f"⏱ Нужно подождать **{wait_time_str}**",
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                failed += 1
                error_text = str(e)[:100]
                failed_chats.append(f"{chat}: {error_text}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Ошибка с `{chat}`: {error_text}",
                    parse_mode='Markdown'
                )
            
            if i < len(chats) - 1 and user.get('is_sending'):
                for s in range(60, 0, -1):
                    if not user.get('is_sending'):
                        break
                    if s % 10 == 0 or s <= 5:
                        await status_msg.edit_text(
                            f"⏳ **Следующее сообщение через {s}с**\n"
                            f"📊 Прогресс: {i+1}/{len(chats)}\n"
                            f"✅ Успешно: {successful}\n"
                            f"❌ Ошибок: {failed}\n"
                            f"⏸ Пропущено: {skipped}"
                        )
                    await asyncio.sleep(1)
        
        user['is_sending'] = False
        save_data()
        
        result_text = (
            f"✅ **РАССЫЛКА ЗАВЕРШЕНА!**\n\n"
            f"📨 **Отправлено:** {successful}\n"
            f"❌ **Ошибок:** {failed}\n"
            f"⏸ **Пропущено:** {skipped}\n"
            f"📊 **Всего чатов:** {len(chats)}"
        )
        
        if failed_chats:
            result_text += "\n\n📝 **Детали:**\n" + "\n".join([f"• {c}" for c in failed_chats[:5]])
            if len(failed_chats) > 5:
                result_text += f"\n...и еще {len(failed_chats)-5}"
        
        await status_msg.edit_text(result_text, parse_mode='Markdown')
        
    except asyncio.CancelledError:
        user['is_sending'] = False
        save_data()
        await status_msg.edit_text(
            f"⏸ **РАССЫЛКА ОСТАНОВЛЕНА!**\n\n"
            f"📨 **Отправлено:** {successful}\n"
            f"❌ **Ошибок:** {failed}\n"
            f"⏸ **Пропущено:** {skipped}",
            parse_mode='Markdown'
        )
    
    if user_id in sending_tasks:
        del sending_tasks[user_id]
    
    await context.bot.send_message(
        chat_id=user_id,
        text="🔙 Возврат в меню.",
        reply_markup=get_main_keyboard(user)
    )

# Главная функция
async def main():
    load_data()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Бот запущен с русским интерфейсом!")
    
    # Запускаем бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Держим бота запущенным
    try:
        while True:
            await asyncio.sleep(3600)  # Спим час
    except KeyboardInterrupt:
        print("🛑 Бот остановлен пользователем")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
