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
from aiogram.fsm.storage.memory import MemoryStorage  # ✅ Добавляем `MemoryStorage`
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
        self.dp = Dispatcher(storage=MemoryStorage())
        self.mentor_id = mentor_id
        self.access_password = access_password
        self.users = {}
        self.sessions = {}
        self.history = {}
        self.register_handlers()

    def register_handlers(self):
        """
        Регистрирует обработчики команд и сообщений.
        """
        self.dp.message.register(self.send_welcome, Command("start"))
        self.dp.callback_query.register(self.enter_school, lambda c: c.data == "enter_school")
        self.dp.message.register(self.check_password,
                                 lambda msg: msg.from_user.id not in self.users and msg.from_user.id != self.mentor_id)
        self.dp.message.register(self.waiting_message, lambda
            msg: msg.from_user.id in self.users and msg.from_user.id not in self.sessions and msg.from_user.id != self.mentor_id)
        self.dp.message.register(self.forward_to_mentor,
                                 lambda msg: msg.from_user.id in self.users and msg.from_user.id in self.sessions)
        self.dp.message.register(self.join_chat, Command("join"))
        self.dp.message.register(self.forward_to_user,
                                 lambda msg: msg.from_user.id == self.mentor_id and self.mentor_id in self.sessions)
        self.dp.callback_query.register(self.call_mentor, lambda c: c.data == "call_mentor")
        self.dp.message.register(self.end_chat, Command("end"))

    async def delete_webhook(self):
        """
        Удаляет вебхук перед запуском polling.
        """
        await self.bot.delete_webhook(drop_pending_updates=True)

    async def send_welcome(self, message: types.Message):
        """
        Отправляет приветственное сообщение с кнопкой 'Войти'.
        """
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Войти", callback_data="enter_school")]
        ])
        await message.answer(
            "👋 Добро пожаловать в IT-школу MyFreeIT!\nНажмите 'Войти', чтобы продолжить.",
            reply_markup=keyboard
        )

    async def enter_school(self, callback_query: types.CallbackQuery):
        """
        Обработка нажатия кнопки 'Войти'. Просит ввести пароль для доступа.
        """
        await self.bot.send_message(callback_query.from_user.id, "🔑 Введите пароль для доступа.")
        await callback_query.answer()

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

    async def call_mentor(self, callback_query: types.CallbackQuery):
        """
        Отправляет уведомление ментору о запросе участника на подключение.
        """
        user_id = callback_query.from_user.id
        username = self.users.get(user_id, "Неизвестный")
        await self.bot.send_message(self.mentor_id, f"⚡ Участник {username} вызывает вас! Используйте /join.")
        await callback_query.answer("Запрос отправлен! Ожидайте подключения ментора.")

    async def start_polling(self):
        """
        Запуск polling после удаления вебхука.
        """
        await self.delete_webhook()
        await self.dp.start_polling(self.bot)


if __name__ == "__main__":
    bot = MentorChatBot(TOKEN, MENTOR_ID, ACCESS_PASSWORD)
    bot.start_polling()
