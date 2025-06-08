"""
Mentoring Bot

Автор: Denis Odesskiy (MyFreeIT)
Описание: Этот скрипт реализует чат-бота для IT-школы MyFreeIT. Бот предназначен для
регистрации участников, проверки пароля, установления сессии между участником и ментором, а также
пересылки сообщений между ними.

Лицензия: Продукт является личной собственностью автора (Denis Odesskiy (MyFreeIT)) – см. LICENSE.
"""

import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
# Инициализация диспетчера с MemoryStorage для хранения состояний (FSM) в оперативной памяти.
# MemoryStorage подходит для небольших ботов, но если потребуется сохранение данных между запусками,
# рекомендуется использовать постоянное хранилище (например, RedisStorage).
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MENTOR_ID = int(os.getenv("MENTOR_ID"))
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")


class MentorChatBot:
    """
    Класс MentorChatBot реализует логику чат-бота для IT-школы MyFreeIT.

    Атрибуты:
      - bot (Bot): экземпляр бота aiogram.
      - dp (Dispatcher): диспетчер для обработки входящих обновлений.
      - mentor_id (int): идентификатор менторского аккаунта.
      - access_password (str): пароль для доступа в систему.
      - users (dict): зарегистрированные участники {user_id: username}.
      - sessions (dict): сессии чата между ментором и участниками.
      - history (dict): история сообщений для участников {participant_id: [сообщения]}.
    """

    def __init__(self, token, mentor_id, access_password):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())  # Используем MemoryStorage для хранения FSM состояний
        self.mentor_id = mentor_id
        self.access_password = access_password
        self.users = {}
        self.sessions = {}
        self.history = {}
        self.register_handlers()

    def register_handlers(self):
        """
        Регистрирует обработчики команд и сообщений. Обработчики:
          - /start – приветственное сообщение с кнопкой "Войти".
          - Нажатие кнопки "Войти" (callback_data = "enter_school").
          - Проверка пароля для новых пользователей.
          - Ожидание подключения ментором.
          - Пересылка сообщений участника ментору.
          - Команда /join для подключения ментором.
          - Пересылка сообщений ментором участнику.
          - Вызов ментора (callback кнопка "Вызвать ментора").
          - Команда /end для завершения чата.
        """
        # Команда /start – отправляем приветствие IT-школы.
        self.dp.message.register(self.send_welcome, Command("start"))
        # Обработка нажатия кнопки "Войти" (callback_data = "enter_school").
        self.dp.callback_query.register(self.enter_school, lambda c: c.data == "enter_school")
        # Если пользователь ещё не зарегистрирован (и не ментор) – проверить пароль.
        self.dp.message.register(self.check_password, lambda msg: (msg.from_user.id not in self.users) and (
                    msg.from_user.id != self.mentor_id))
        # Если пользователь уже зарегистрирован, но не подключён к ментору – ждем подключения.
        self.dp.message.register(self.waiting_message, lambda msg: (msg.from_user.id in self.users) and (
                    msg.from_user.id not in self.sessions) and (msg.from_user.id != self.mentor_id))
        # Если участник зарегистрирован и уже подключён – пересылаем его сообщение ментору.
        self.dp.message.register(self.forward_to_mentor,
                                 lambda msg: (msg.from_user.id in self.users) and (msg.from_user.id in self.sessions))
        # Ментор использует команду /join для подключения к ожидающему участнику.
        self.dp.message.register(self.join_chat, Command("join"))
        # Если ментор отправляет сообщение – пересылаем его участнику (если сессия установлена).
        self.dp.message.register(self.forward_to_user,
                                 lambda msg: (msg.from_user.id == self.mentor_id) and (self.mentor_id in self.sessions))
        # При нажатии кнопки "Вызвать ментора" участник вызывает уведомление для ментора.
        self.dp.callback_query.register(self.call_mentor, lambda c: c.data == "call_mentor")
        # Команда /end позволяет ментору завершить чат.
        self.dp.message.register(self.end_chat, Command("end"))

    async def delete_webhook(self):
        """Удаляет вебхук перед запуском polling для предотвращения конфликта."""
        await self.bot.delete_webhook(drop_pending_updates=True)

    async def send_welcome(self, message: types.Message):
        """
        Отправляет приветственное сообщение с кнопкой 'Войти'.
        """
        welcome_text = (
            "👋 Добро пожаловать в IT-школу MyFreeIT!\n"
            "Мы рады приветствовать вас.\n\n"
            "Нажмите кнопку 'Войти', чтобы продолжить и ввести пароль для доступа."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Войти", callback_data="enter_school")]
        ])
        await message.answer(welcome_text, reply_markup=keyboard)

    async def enter_school(self, callback_query: types.CallbackQuery):
        """
        Обработка нажатия кнопки 'Войти'. Просит ввести пароль для доступа.
        """
        await self.bot.send_message(
            callback_query.from_user.id,
            "🔑 Пожалуйста, введите пароль для доступа в систему IT-школы."
        )
        await callback_query.answer()  # закрываем всплывающее уведомление

    async def check_password(self, message: types.Message):
        """
        Проверяет введённый пароль. При соответствии регистрирует пользователя.
        """
        if message.text == self.access_password:
            self.users[message.from_user.id] = message.from_user.username
            self.history[message.from_user.id] = []
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
            ])
            await message.answer("✅ Пароль верный! Вы зарегистрированы.", reply_markup=keyboard)
        else:
            await message.answer("❌ Неверный пароль! Доступ запрещён.")

    async def waiting_message(self, message: types.Message):
        """
        Сообщает, что пользователь уже зарегистрирован и ожидает подключения ментора.
        """
        await message.answer("✅ Вы уже зарегистрированы. Пожалуйста, ожидайте подключения ментора.")

    async def join_chat(self, message: types.Message):
        """
        Команда для ментора: подключение к первому ожидающему участнику.
        """
        if message.from_user.id != self.mentor_id:
            await message.answer("❌ У вас нет прав ментора!")
            return

        waiting = [uid for uid in self.users if uid not in self.sessions]
        if not waiting:
            await message.answer("🟢 Нет ожидающих участников. Ждите запроса.")
            return

        user_id = waiting[0]
        # Создаём взаимное подключение:
        self.sessions[self.mentor_id] = user_id
        self.sessions[user_id] = self.mentor_id

        await message.answer(f"📩 Вы подключены к участнику {self.users[user_id]}.")
        await self.bot.send_message(user_id, "👨‍🏫 Ментор присоединился к чату и готов помочь!")

    async def call_mentor(self, callback_query: types.CallbackQuery):
        """
        Отправляет уведомление ментору о запросе участника на подключение.
        """
        user_id = callback_query.from_user.id
        username = self.users.get(user_id, "Неизвестный")
        await self.bot.send_message(self.mentor_id,
                                    f"⚡ Участник {username} ({user_id}) вызывает вас! Используйте /join.")
        await callback_query.answer("Запрос отправлен! Ожидайте подключения ментора.")

    async def forward_to_mentor(self, message: types.Message):
        """
        Пересылает сообщение участника ментору.
        """
        uid = message.from_user.id
        if uid not in self.sessions:
            await message.answer("❌ Пожалуйста, ждите подключения ментора.")
            return
        mentor_id = self.sessions[uid]
        self.history[uid].append(f"👤 Участник: {message.text}")
        await self.bot.send_message(mentor_id, f"📩 Сообщение от участника:\n{message.text}")

    async def forward_to_user(self, message: types.Message):
        """
        Пересылает сообщение ментора участнику.
        """
        if self.mentor_id not in self.sessions:
            await message.answer("❌ Нет активного участника.")
            return
        user_id = self.sessions.get(self.mentor_id)
        if not user_id:
            await message.answer("❌ Нет активного участника.")
            return
        self.history.setdefault(user_id, []).append(f"👨‍🏫 Ментор: {message.text}")
        await self.bot.send_message(user_id, f"💬 Ответ от ментора:\n{message.text}")

    async def end_chat(self, message: types.Message):
        """
        Завершает чат. Доступно только ментору.
        """
        if message.from_user.id != self.mentor_id:
            await message.answer("❌ Чат завершить может только ментор!")
            return
        if self.mentor_id in self.sessions:
            user_id = self.sessions.pop(self.mentor_id, None)
            if user_id:
                await self.bot.send_message(user_id, "📌 Чат завершён ментором. Спасибо за общение!")
                self.sessions.pop(user_id, None)
                self.history.pop(user_id, None)
            await message.answer("✅ Чат завершён.")
        else:
            await message.answer("❌ Нет активного чата для завершения.")

    async def start_polling(self):
        """
        Запускает polling после удаления вебхука.
        """
        await self.delete_webhook()
        await self.dp.start_polling(self.bot)


if __name__ == "__main__":
    bot = MentorChatBot(TOKEN, MENTOR_ID, ACCESS_PASSWORD)
    import asyncio

    asyncio.run(bot.start_polling())
