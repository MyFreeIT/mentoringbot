"""
Mentoring Bot

Автор: Denis Odesskiy (MyFreeIT)
Описание: Этот скрипт реализует Telegram-бота для IT-школы MyFreeIT.
Он осуществляет регистрацию участников, проверку пароля, установление сессии между
участником и ментором, а также пересылку сообщений между ними.

Лицензия: Продукт является личной собственностью автора (Denis Odesskiy (MyFreeIT)) – см. LICENSE.
"""

import os
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MENTOR_ID = int(os.getenv("MENTOR_ID"))
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")


class MentorChatBot:
    """
    Реализует логику чат-бота для IT-школы MyFreeIT:
    регистрация участников, проверка пароля, установление сессии между участником и ментором,
    а также пересылка сообщений между ними.
    """

    def __init__(self, token, mentor_id, access_password):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.mentor_id = mentor_id
        self.access_password = access_password
        self.users = {}         # {user_id: имя}
        self.sessions = {}      # Активные сессии: ментор <-> участник
        self.waitlist = []      # Очередь ожидающих подключения участников
        self.history = {}       # История сообщений для каждого пользователя
        self.awaiting_name = {}  # Пользователи, ожидающие ввода имени
        self.register_handlers()

    def register_handlers(self):
        # Команда /start
        self.dp.message.register(self.send_welcome, Command("start"))
        self.dp.callback_query.register(self.enter_school, lambda c: c.data == "enter_school")

        # Проверка пароля для незарегистрированных участников (и не ожидающих ввода имени)
        self.dp.message.register(
            self.check_password,
            lambda msg: (msg.from_user.id not in self.users)
                        and (msg.from_user.id != self.mentor_id)
                        and (msg.from_user.id not in self.awaiting_name)
        )

        # Для зарегистрированных участников – кнопка "Вызвать ментора"
        self.dp.message.register(
            self.waiting_message,
            lambda msg: (msg.from_user.id in self.users)
                        and (msg.from_user.id not in self.sessions)
                        and (msg.from_user.id != self.mentor_id)
        )

        # Пересылка сообщений участника ментору (только если сессия активна)
        self.dp.message.register(
            self.forward_to_mentor,
            lambda msg: (msg.from_user.id in self.users) and (msg.from_user.id in self.sessions)
        )

        # Менторские команды через слэш: /join и /end (проверка прав внутри функции)
        self.dp.message.register(self.join_chat, Command("join"))
        self.dp.message.register(self.end_chat, Command("end"))

        # Пересылка сообщений ментора участнику (inline сообщения, пропуская команды)
        self.dp.message.register(
            self.forward_to_user,
            lambda msg: (msg.from_user.id == self.mentor_id)
                        and (self.mentor_id in self.sessions)
                        and (not (msg.text and msg.text.startswith('/')))
        )

        # Кнопка "Вызвать ментора" для участников
        self.dp.callback_query.register(self.call_mentor, lambda c: c.data == "call_mentor")

        # Обработка отсутствия имени в профиле: выбор "Войти как Аноним" или "Ввести имя"
        self.dp.callback_query.register(self.use_anonymous, lambda c: c.data == "use_anonymous")
        self.dp.callback_query.register(self.enter_custom_name, lambda c: c.data == "enter_custom_name")
        self.dp.message.register(self.set_custom_name, lambda msg: msg.from_user.id in self.awaiting_name)

        # Callback для менторского inline‑меню (доступно только ментору)
        self.dp.callback_query.register(self.mentor_join, lambda c: c.data == "mentor_join")
        self.dp.callback_query.register(self.mentor_end, lambda c: c.data == "mentor_end")

    async def delete_webhook(self):
        """Удаляет существующий webhook перед запуском polling, чтобы избежать конфликтов."""
        await self.bot.delete_webhook(drop_pending_updates=True)

    async def send_welcome(self, message: types.Message):
        """
        Отправляет приветственное сообщение:
          - Если пользователь – ментор, отображается меню с кнопками "Присоединиться" и "Завершить чат".
          - Если пользователь уже зарегистрирован (студент), отображается кнопка "Вызвать ментора".
          - Для нового пользователя – кнопка "Войти".
        """
        if message.from_user.id == self.mentor_id:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Присоединиться", callback_data="mentor_join")],
                [InlineKeyboardButton(text="Завершить чат", callback_data="mentor_end")]
            ])
            await message.answer("👋 Добро пожаловать, ментор! Выберите действие (также доступны команды /join и /end):",
                                 reply_markup=keyboard)
        else:
            if message.from_user.id in self.users:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
                ])
                await message.answer("👋 Вы уже зарегистрированы. Если хотите вызвать ментора, нажмите кнопку ниже.",
                                     reply_markup=keyboard)
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Войти", callback_data="enter_school")]
                ])
                await message.answer("👋 Добро пожаловать в IT-школу MyFreeIT!\nНажмите кнопку 'Войти', чтобы продолжить и ввести пароль для доступа.",
                                     reply_markup=keyboard)

    async def enter_school(self, callback_query: types.CallbackQuery):
        """Запрашивает ввод пароля для доступа в систему IT-школы."""
        await self.bot.send_message(callback_query.from_user.id,
                                    "🔑 Пожалуйста, введите пароль для доступа в систему IT-школы.")
        await callback_query.answer()

    async def check_password(self, message: types.Message):
        """
        Проверяет введённый пароль:
          - Для ментора используется имя из профиля (если отсутствует, подставляется "Ментор").
          - Для участников, если имя отсутствует, предлагается выбор регистрации как "Войти как Аноним" или "Ввести имя".
        """
        if message.text == self.access_password:
            if message.from_user.id == self.mentor_id:
                name = message.from_user.username if message.from_user.username else "Ментор"
                self.users[message.from_user.id] = name
                self.history[message.from_user.id] = []
                await message.answer("✅ Пароль верный! Добро пожаловать, ментор!")
            else:
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
        Использует введённый текст как имя пользователя при регистрации.
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
        Уведомляет зарегистрированных участников и предоставляет кнопку "Вызвать ментора".
        """
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
        ])
        await message.answer("✅ Вы уже зарегистрированы. Если хотите вызвать ментора, нажмите кнопку ниже.",
                             reply_markup=keyboard)

    async def call_mentor(self, callback_query: types.CallbackQuery):
        """
        Отправляет запрос на подключение к ментору.
        Если сессия активна, участник добавляется в очередь ожидания.
        """
        user_id = callback_query.from_user.id
        username = self.users.get(user_id)
        if not username:
            await self.bot.send_message(user_id, "Пожалуйста, зарегистрируйтесь перед вызовом ментора.")
            await callback_query.answer()
            return

        if self.mentor_id in self.sessions:
            if user_id not in self.waitlist:
                self.waitlist.append(user_id)
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Участник {username} ({user_id}) добавлен в очередь ожидания. Используйте кнопку 'Присоединиться' или команду /join после завершения текущего чата."
                )
            else:
                await self.bot.send_message(user_id, "Вы уже в очереди на подключение к ментору.")
            await callback_query.answer("Вы добавлены в очередь! Ожидайте подключения ментора.")
        else:
            await self.bot.send_message(
                self.mentor_id,
                f"⚡ Участник {username} ({user_id}) вызывает вас! Используйте кнопку 'Присоединиться' или команду /join."
            )
            await callback_query.answer("Запрос отправлен! Ожидайте подключения ментора.")

    async def use_anonymous(self, callback: types.CallbackQuery):
        """
        Регистрирует участника как "Аноним".
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
        Переводит участника в режим ввода собственного имени.
        """
        user_id = callback.from_user.id
        self.awaiting_name[user_id] = True
        await self.bot.send_message(user_id, "Пожалуйста, введите ваше имя:")
        await callback.answer()

    async def join_chat(self, message: types.Message):
        """
        Команда для подключения ментора к ожидающему участнику.
        Только ментор имеет право выполнять данную команду.
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
        await message.answer(f"📩 Вы подключены к участнику {self.users.get(user_id)}.")
        await self.bot.send_message(user_id, "👨‍🏫 Ментор присоединился к чату и готов помочь!")

    async def mentor_join(self, callback: types.CallbackQuery):
        """
        Callback для кнопки "Присоединиться" ментору (доступно только ментору).
        """
        if callback.from_user.id != self.mentor_id:
            await callback.answer("❌ У вас нет прав ментора!", show_alert=True)
            return

        # Создаем фиктивное сообщение для вызова join_chat
        class FakeMessage:
            pass

        fake_msg = FakeMessage()
        fake_msg.from_user = callback.from_user
        fake_msg.answer = lambda text, **kwargs: self.bot.send_message(callback.from_user.id, text)
        await self.join_chat(fake_msg)
        await callback.answer()

    async def mentor_end(self, callback: types.CallbackQuery):
        """
        Callback для кнопки "Завершить чат" ментору (доступно только ментору).
        """
        if callback.from_user.id != self.mentor_id:
            await callback.answer("❌ У вас нет прав ментора!", show_alert=True)
            return

        class FakeMessage:
            pass

        fake_msg = FakeMessage()
        fake_msg.from_user = callback.from_user
        fake_msg.answer = lambda text, **kwargs: self.bot.send_message(callback.from_user.id, text)
        await self.end_chat(fake_msg)
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
        await self.bot.send_message(mentor_id,
                                    f"📩 Сообщение от участника:\n{message.text}")

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
        Завершает текущую сессию чата.
        Только ментор может завершать чат.
        После завершения участнику отправляется уведомление с кнопкой для вызова ментора вновь.
        """
        if message.from_user.id != self.mentor_id:
            await message.answer("❌ Чат завершить может только ментор!")
            return

        if self.mentor_id in self.sessions:
            user_id = self.sessions.pop(self.mentor_id, None)
            if user_id:
                self.sessions.pop(user_id, None)
                self.history.pop(user_id, None)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
                ])
                await self.bot.send_message(user_id,
                                            "📌 Чат завершён ментором. Если хотите вызвать ментора, нажмите кнопку ниже.",
                                            reply_markup=keyboard)
            await message.answer("✅ Чат завершён.")
            if self.waitlist:
                next_id = self.waitlist[0]
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Следующий участник ({self.users.get(next_id)}) ожидает подключения. Используйте кнопку 'Присоединиться' или команду /join."
                )
        else:
            await message.answer("❌ Нет активного чата для завершения.")

    async def start_polling(self):
        """Удаляет существующий webhook и запускает polling."""
        await self.delete_webhook()
        await self.dp.start_polling(self.bot)


async def keep_alive():
    """
    Периодически отправляет GET-запрос на собственный сервер,
    чтобы предотвратить засыпание контейнера на Render.
    """
    url = "https://yourapp.onrender.com"  # Замените на URL вашего приложения
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    print(f"Keep-Alive ping status: {response.status}")
        except Exception as e:
            print(f"Keep-Alive error: {e}")
        await asyncio.sleep(840)  # 14 минут


async def run_web_server():
    """
    Запускает минимальный HTTP-сервер (с использованием aiohttp), который слушает порт,
    указанный в переменной окружения PORT. Это предотвращает таймаут Render из-за отсутствия открытого порта.
    """
    from aiohttp import web

    async def handle(request):
        return web.Response(text="Менторский бот работает!")

    app = web.Application()
    app.add_routes([web.get("/", handle)])
    port = int(os.environ.get("PORT", 8000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP-сервер запущен на порту {port}")
    # Держим сервер запущенным
    while True:
        await asyncio.sleep(3600)


async def main():
    """
    Запускает параллельно:
      - Polling Telegram-бота,
      - HTTP-сервер для Bind PORT,
      - Keep-Alive пинг самоподдержки.
    """
    bot_instance = MentorChatBot(TOKEN, MENTOR_ID, ACCESS_PASSWORD)
    await asyncio.gather(
        bot_instance.start_polling(),
        run_web_server(),
        keep_alive()
    )


if __name__ == "__main__":
    asyncio.run(main())
