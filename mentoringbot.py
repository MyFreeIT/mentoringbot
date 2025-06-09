"""
Mentoring Bot

Author: Denis Odesskiy (MyFreeIT)
Description: This script implements a Telegram chat-bot for the IT-school MyFreeIT.
It handles participant registration, password verification, session management between
the participant and a mentor, and message forwarding.

License: The product is the personal property of the author (Denis Odesskiy (MyFreeIT)) – see LICENSE.
"""

import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MENTOR_ID = int(os.getenv("MENTOR_ID"))
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")


class MentorChatBot:
    """
    Implements the chat-bot logic for the IT-school MyFreeIT.
    Handles registration, password verification, establishing session between a participant and a mentor,
    and message forwarding between them.
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
        self.awaiting_name = {}  # Flag to keep track of users waiting for custom name input
        self.register_handlers()

    def register_handlers(self):
        # /start command
        self.dp.message.register(self.send_welcome, Command("start"))
        self.dp.callback_query.register(self.enter_school, lambda c: c.data == "enter_school")

        # Handle password verification for unregistered participants
        self.dp.message.register(
            self.check_password,
            lambda msg: (msg.from_user.id not in self.users)
                        and (msg.from_user.id != self.mentor_id)
                        and (msg.from_user.id not in self.awaiting_name)
        )

        # If participant already registered, show the "Call mentor" button
        self.dp.message.register(
            self.waiting_message,
            lambda msg: (msg.from_user.id in self.users)
                        and (msg.from_user.id not in self.sessions)
                        and (msg.from_user.id != self.mentor_id)
        )

        # Forward messages from participant to mentor
        self.dp.message.register(
            self.forward_to_mentor,
            lambda msg: (msg.from_user.id in self.users) and (msg.from_user.id in self.sessions)
        )

        # Mentor commands via slash commands /join and /end
        self.dp.message.register(self.join_chat, Command("join"))
        self.dp.message.register(self.end_chat, Command("end"))

        # Inline menu for mentor message forwarding (skipping texts starting with '/')
        self.dp.message.register(
            self.forward_to_user,
            lambda msg: (msg.from_user.id == self.mentor_id)
                        and (self.mentor_id in self.sessions)
                        and (not (msg.text and msg.text.startswith('/')))
        )

        # Callback for participant button "Call mentor"
        self.dp.callback_query.register(self.call_mentor, lambda c: c.data == "call_mentor")

        # Callbacks for handling missing username
        self.dp.callback_query.register(self.use_anonymous, lambda c: c.data == "use_anonymous")
        self.dp.callback_query.register(self.enter_custom_name, lambda c: c.data == "enter_custom_name")
        self.dp.message.register(self.set_custom_name, lambda msg: msg.from_user.id in self.awaiting_name)

        # Callback for mentor inline‑menu buttons
        self.dp.callback_query.register(self.mentor_join, lambda c: c.data == "mentor_join")
        self.dp.callback_query.register(self.mentor_end, lambda c: c.data == "mentor_end")

    async def delete_webhook(self):
        """Deletes the webhook before starting polling to avoid conflicts."""
        await self.bot.delete_webhook(drop_pending_updates=True)

    async def send_welcome(self, message: types.Message):
        """
        Sends a welcome message.
          - If user is the mentor, a menu with "Join" and "End chat" buttons is shown.
          - If the participant is registered, shows the "Call mentor" button.
          - Otherwise, presents the "Enter" button.
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
                await message.answer(
                    "👋 Вы уже зарегистрированы. Если хотите снова вызвать ментора, нажмите кнопку ниже.",
                    reply_markup=keyboard
                )
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Войти", callback_data="enter_school")]
                ])
                await message.answer(
                    "👋 Добро пожаловать в IT-школу MyFreeIT!\nНажмите кнопку 'Войти', чтобы продолжить и ввести пароль для доступа.",
                    reply_markup=keyboard
                )

    async def enter_school(self, callback_query: types.CallbackQuery):
        """Handles the 'Enter' button click, prompting the user to input the access password."""
        await self.bot.send_message(
            callback_query.from_user.id,
            "🔑 Пожалуйста, введите пароль для доступа в систему IT-школы."
        )
        await callback_query.answer()

    async def check_password(self, message: types.Message):
        """
        Checks the entered password.
          - For mentor: registration is performed via /start.
          - For participants: if username is missing, offers options for registration.
        """
        if message.text == self.access_password:
            if message.from_user.id == self.mentor_id:
                self.users[
                    message.from_user.id] = message.from_user.username if message.from_user.username else "Ментор"
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
        Uses the entered text as the user's name if waiting for custom name input.
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
        Notifies the participant that they are already registered and provides the "Call mentor" button.
        """
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вызвать ментора", callback_data="call_mentor")]
        ])
        await message.answer("✅ Вы уже зарегистрированы. Если хотите вызвать ментора, нажмите кнопку ниже.",
                             reply_markup=keyboard)

    async def call_mentor(self, callback_query: types.CallbackQuery):
        """
        Notifies the mentor about a participant's request.
        If a session is active, the participant is added to the waiting list.
        """
        user_id = callback_query.from_user.id
        username = self.users.get(user_id, "Неизвестный")
        if self.mentor_id in self.sessions:
            if user_id not in self.waitlist:
                self.waitlist.append(user_id)
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Участник {username} ({user_id}) добавлен в очередь ожидания. "
                    "Используйте кнопку 'Присоединиться' или команду /join после завершения текущего чата."
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
        Registers the participant under the name "Аноним".
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
        Switches the user to custom name input mode.
        """
        user_id = callback.from_user.id
        self.awaiting_name[user_id] = True
        await self.bot.send_message(user_id, "Пожалуйста, введите ваше имя:")
        await callback.answer()

    async def join_chat(self, message: types.Message):
        """
        Mentor command to join a waiting participant.
        If a session is already active or no participant is waiting, it notifies accordingly.
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
        Handler for the mentor inline button "Присоединиться".
        """
        if callback.from_user.id != self.mentor_id:
            await callback.answer("❌ У вас нет прав ментора!", show_alert=True)
            return

        class FakeMessage:
            pass

        fake_msg = FakeMessage()
        fake_msg.from_user = callback.from_user
        fake_msg.answer = lambda text, **kwargs: self.bot.send_message(callback.from_user.id, text)
        await self.join_chat(fake_msg)
        await callback.answer()

    async def mentor_end(self, callback: types.CallbackQuery):
        """
        Handler for the mentor inline button "Завершить чат".
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
        Forwards a participant's message to the mentor.
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
        Forwards the mentor's message to the participant.
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
        Ends the current chat session. Only the mentor can end a session.
        After ending, the participant is notified with an option to call the mentor again.
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
                await self.bot.send_message(
                    user_id,
                    "📌 Чат завершён ментором. Если хотите снова вызвать ментора, нажмите кнопку ниже.",
                    reply_markup=keyboard
                )
            await message.answer("✅ Чат завершён.")
            if self.waitlist:
                next_id = self.waitlist[0]
                await self.bot.send_message(
                    self.mentor_id,
                    f"⚡ Следующий студент ({self.users.get(next_id, 'Неизвестный')}) ожидает подключения. Используйте кнопку 'Присоединиться' или команду /join."
                )
        else:
            await message.answer("❌ Нет активного чата для завершения.")

    async def start_polling(self):
        """
        Deletes any existing webhook and starts long polling.
        """
        await self.delete_webhook()
        await self.dp.start_polling(self.bot)


if __name__ == "__main__":
    bot = MentorChatBot(TOKEN, MENTOR_ID, ACCESS_PASSWORD)


    async def run_web_server():
        """
        Starts a minimal HTTP server that listens on the port specified by the environment variable.
        This prevents Render from timing out due to the absence of any open ports.
        """
        from aiohttp import web

        async def handle(request):
            return web.Response(text="Mentoring Bot is running!")

        app = web.Application()
        app.add_routes([web.get("/", handle)])
        port = int(os.environ.get("PORT", 8000))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"HTTP server is running on port {port}")
        # Keep the HTTP server running indefinitely.
        while True:
            await asyncio.sleep(3600)


    async def main():
        # Run both the Telegram bot (via polling) and the HTTP server concurrently.
        await asyncio.gather(
            bot.start_polling(),
            run_web_server()
        )


    asyncio.run(main())
