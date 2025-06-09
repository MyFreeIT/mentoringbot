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
# Используем MemoryStorage для хранения FSM-состояний в оперативной памяти.
# Для более серьёзных проектов рекомендуется постоянное хранилище (например, RedisStorage).
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MENTOR_ID = int(os.getenv("MENTOR_ID"))
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")


class MentorChatBot:
    """
    Класс MentorChatBot реализует логику чат-бота для IT-школы MyFreeIT.

    Атрибуты:
      - bot (Bot): экземпляр бота aiogram.
      - dp (Dispatcher): диспетчер обновлений.
      - mentor_id (int): ID менторского аккаунта.
      - access_password (str): пароль для доступа в систему.
      - users (dict): зарегистрированные участники {user_id: имя}.
      - sessions (dict): активные сессии (связь mentor_id ↔ user_id).
      - waitlist (list): очередь студентов, ожидающих подключения.
      - history (dict): история сообщений для участников.
      - awaiting_name (dict): флаг ожидания ввода имени (если имя отсутствует в Telegram).
    """

    def __init__(self, token, mentor_id, access_password):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.mentor_id = mentor_id
        self.access_password = access_password
        self.users = {}
        self.sessions = {}
        self.waitlist = []
        self.history = {}
        self.awaiting_name = {}  # Для хранения флага ожидания ввода имени
        self.register_handlers()

    def register_handlers(self):
        """
        Регистрирует обработчики команд и сообщений.
        Обработчики:
         - /start: приветственное сообщение с кнопками.
         - Callback "enter_school": требует пароль для входа.
         - Проверка пароля через check_password (отличается для ментора и участников).
         - Если участник уже зарегистрирован, выводится сообщение об ожидании менторства.
         - "Вызвать ментора": запрос подключения участника.
         - /join и /end для менторских действий.
         - Дополнительные callback'и для регистрации отсутствующего имени.
        """
        self.dp.message.register(self.send_welcome, Command("start"))
        self.dp.callback_query.register(self.enter_school, lambda c: c.data == "enter_school")
        self.dp.message.register(
            self.check_password,
            lambda msg: (msg.from_user.id not in self.users) and (msg.from_user.id != self.mentor_id)
        )
        self.dp.message.register(
            self.waiting_message,
            lambda msg: (msg.from_user.id in self.users)
                        and (msg.from_user.id not in self.sessions)
                        and (msg.from_user.id != self.mentor_id)
        )
        self.dp.message.register(
            self.forward_to_mentor,
            lambda msg: (msg.from_user.id in self.users) and (msg.from_user.id in self.sessions)
        )
        self.dp.message.register(self.join_chat, Command("join"))
        # Обработчик для сообщений ментора – пропускает команды (начинающиеся со слеша)
        self.dp.message.register(
            self.forward_to_user,
            lambda msg: (msg.from_user.id == self.mentor_id)
                        and (self.mentor_id in self.sessions)
                        and (not (msg.text and msg.text.startswith('/')))
        )
        self.dp.callback_query.register(self.call_mentor, lambda c: c.data == "call_mentor")
        self.dp.message.register(self.end_chat, Command("end"))
        # Callback'и для работы с отсутствующим именем
        self.dp.callback_query.register(self.use_anonymous, lambda c: c.data == "use_anonymous")
        self.dp.callback_query.register(self.enter_custom_name, lambda c: c.data == "enter_custom_name")
        self.dp.message.register(self.set_custom_name, lambda msg: msg.from_user.id in self.awaiting_name)
        # Inline-кнопки для менторского меню
        self.dp.callback_query.register(self.mentor_join, lambda c: c.data == "mentor_join")
        self.dp.callback_query.register(self.mentor_end, lambda c: c.data == "mentor_end")

    async def delete_webhook(self):
        """Удаляет вебхук перед запуском polling для предотвращения конфликта."""
        await self.bot.delete_webhook(drop_pending_updates=True)

    async def send_welcome(self, message: types.Message):
        """
        Отправляет приветственное сообщение.
        Если пользователь – ментор, отображается меню с кнопками:
          "Присоединиться" и "Завершить чат".
        Иначе – приглашение нажать кнопку "Войти".
        """
        if message.from_user.id == self.mentor_id:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Присоединиться", callback_data="mentor_join")],
                [InlineKeyboardButton(text="Завершить чат", callback_data="mentor_end")]
            ])
            await message.answer("👋 Добро пожаловать, ментор! Выберите действие:", reply_markup=keyboard)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Войти", callback_data="enter_school")]
            ])
            await message.answer(
                "👋 Добро пожаловать в IT-школу MyFreeIT!\nНажмите кнопку 'Войти', чтобы продолжить и ввести пароль для доступа.",
                reply_markup=keyboard
            )

    async def enter_school(self, callback_query: types.CallbackQuery):
        """
        Обработка нажатия кнопки "Войти". Просит ввести пароль.
        """
        await self.bot.send_message(
            callback_query.from_user.id,
            "🔑 Пожалуйста, введите пароль для доступа в систему IT-школы."
        )
        await callback_query.answer()

    async def check_password(self, message: types.Message):
        """
        Проверяет введённый пароль.
        Если пароль корректен:
          – для ментора сразу регистрирует его;
          – для участников: если username не указан, предлагает выбор:
             "Войти как Аноним" или "Ввести имя".
          В противном случае использует username для регистрации.
        """
        if message.text == self.access_password:
            if message.from_user.id == self.mentor_id:
                # Регистрация ментора
                self.users[
                    message.from_user.id] = message.from_user.username if message.from_user.username else "Ментор"
                self.history[message.from_user.id] = []
                await message.answer("✅ Пароль верный! Добро пожаловать, ментор!")
            else:
                # Участник
                if message.from_user.username is None:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Войти как Аноним", callback_data="use_anonymous")],
                        [InlineKeyboardButton(text="Ввести имя", callback_data="enter_custom_name")]
                    ])
                    await message.answer("✅ Пароль верный! Но ваше имя не указано. Выберите способ входа:",
                                         reply_markup=keyboard)
                    return
                else:
                    self.users[message.from_user.id] = message.from_user.username
                    self.history[message.from_user.id] = []
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
                    ])
                    await message.answer("✅ Пароль верный! Вы зарегистрированы.", reply_markup=keyboard)
        else:
            await message.answer("❌ Неверный пароль! Доступ запрещён.")

    async def set_custom_name(self, message: types.Message):
        """
        Если пользователь находится в режиме ожидания ввода имени, использует
        введённый текст как имя и завершает регистрацию.
        """
        user_id = message.from_user.id
        if user_id in self.awaiting_name:
            chosen_name = message.text.strip()
            if not chosen_name:
                await message.answer("Имя не может быть пустым. Пожалуйста, введите ваше имя:")
                return
            self.users[user_id] = chosen_name
            self.history[user_id] = []
            self.awaiting_name.pop(user_id)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
            ])
            await message.answer(f"✅ Вы успешно вошли под именем {chosen_name}.", reply_markup=keyboard)

    async def waiting_message(self, message: types.Message):
        """
        Сообщает, что пользователь уже зарегистрирован и ждёт подключения ментором.
        """
        await message.answer("✅ Вы уже зарегистрированы. Пожалуйста, ожидайте подключения ментора.")

    async def call_mentor(self, callback_query: types.CallbackQuery):
        """
        Отправляет уведомление ментору о запросе участника.
        Если сессия уже активна, добавляет участника в очередь ожидания.
        """
        user_id = callback_query.from_user.id
        username = self.users.get(user_id, "Неизвестный")
        if self.mentor_id in self.sessions:
            if user_id not in self.waitlist:
                self.waitlist.append(user_id)
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Участник {username} ({user_id}) добавлен в очередь ожидания. "
                    "Используйте кнопку 'Присоединиться', чтобы подключиться к следующему студенту после завершения текущего чата."
                )
            else:
                await self.bot.send_message(user_id, "Вы уже в очереди на подключение к ментору.")
            await callback_query.answer("Вы добавлены в очередь! Ожидайте подключения ментора.")
        else:
            await self.bot.send_message(
                self.mentor_id,
                f"⚡ Участник {username} ({user_id}) вызывает вас! Используйте кнопку 'Присоединиться'."
            )
            await callback_query.answer("Запрос отправлен! Ожидайте подключения ментора.")

    async def use_anonymous(self, callback: types.CallbackQuery):
        """
        Регистрация участника под именем "Аноним".
        """
        user_id = callback.from_user.id
        self.users[user_id] = "Аноним"
        self.history[user_id] = []
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
        ])
        await self.bot.send_message(user_id, "✅ Вы успешно вошли под именем Аноним.", reply_markup=keyboard)
        await callback.answer()

    async def enter_custom_name(self, callback: types.CallbackQuery):
        """
        Переводит пользователя в режим ввода собственного имени.
        """
        user_id = callback.from_user.id
        self.awaiting_name[user_id] = True
        await self.bot.send_message(user_id, "Пожалуйста, введите ваше имя:")
        await callback.answer()

    async def join_chat(self, message: types.Message):
        """
        Команда для ментора: подключение к ожидающему участнику.
        Если сессия уже активна, просит завершить текущий чат.
        При наличии очереди выбирается первый ожидающий студент.
        """
        if message.from_user.id != self.mentor_id:
            await message.answer("❌ У вас нет прав ментора!")
            return

        if self.mentor_id in self.sessions:
            await message.answer("❌ Завершите текущий чат перед подключением нового участника.")
            return

        if self.waitlist:
            user_id = self.waitlist.pop(0)
        else:
            waiting = [uid for uid in self.users if uid not in self.sessions and uid != self.mentor_id]
            if not waiting:
                await message.answer("🟢 Нет ожидающих участников. Ждите запроса.")
                return
            user_id = waiting[0]

        self.sessions[self.mentor_id] = user_id
        self.sessions[user_id] = self.mentor_id
        await message.answer(f"📩 Вы подключены к участнику {self.users.get(user_id, 'Неизвестный')}.")
        await self.bot.send_message(user_id, "👨‍🏫 Ментор присоединился к чату и готов помочь!")

    async def mentor_join(self, callback: types.CallbackQuery):
        """
        Обработчик для inline-кнопки "Присоединиться" у ментора.
        Делегирует выполнение методу join_chat.
        """
        await self.join_chat(callback.message)
        await callback.answer()

    async def mentor_end(self, callback: types.CallbackQuery):
        """
        Обработчик для inline-кнопки "Завершить чат" у ментора.
        Делегирует выполнение методу end_chat.
        """
        await self.end_chat(callback.message)
        await callback.answer()

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
        Завершает текущий чат. Доступно только ментору.
        После завершения чата ментору уведомляется о следующем ожидающем студенте (если есть).
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
            if self.waitlist:
                next_id = self.waitlist[0]
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Следующий студент ({self.users.get(next_id, 'Неизвестный')}) ожидает подключения. Используйте кнопку 'Присоединиться' для подключения."
                )
        else:
            await message.answer("❌ Нет активного чата для завершения.")

    async def start_polling(self):
        """
        Удаляет вебхук и запускает процесс polling.
        """
        await self.delete_webhook()
        await self.dp.start_polling(self.bot)


if __name__ == "__main__":
    bot = MentorChatBot(TOKEN, MENTOR_ID, ACCESS_PASSWORD)
    import asyncio

    asyncio.run(bot.start_polling())
