# MyFreeIT Mentoring Bot

![License](https://img.shields.io/badge/license-Proprietary-red)

---

## English Version

**MyFreeIT Mentoring Bot** – is a personal chat bot for MyFreeIT IT School, designed for efficient interaction between
participants and a mentor. The bot provides the following features:

- User registration via the `/start` command.
- Password verification for new users.
- Connecting the mentor with waiting participants.
- Forwarding messages between the mentor and participants.
- Ending chat sessions with the `/end` command.

**Author:** Denis Odesskiy  
**Organization:** MyFreeIT

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mentoring-bot.git
2. Change to the project directory and create a virtual environment:
   ```bash
    cd mentoring-bot
    python -m venv venv
    source venv/bin/activate  # for Windows: venv\Scripts\activate
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
4. Create a .env file with the variables:
   ```bash
   BOT_TOKEN=your_telegram_bot_token
   MENTOR_ID=your_mentor_id
   ACCESS_PASSWORD=your_access_password
5. Run the bot:
   ```bash
   python mentoringbot.py

---

## Русская версия

**MyFreeIT Mentoring Bot** – это персональный чат-бот для IT-школы MyFreeIT, разработанный для удобного взаимодействия
между участниками и ментором.  
Бот позволяет:

- Регистрировать пользователей по команде `/start`
- Проверять пароль доступа для новых участников
- Подключать ментора к ожиданию пользователей
- Пересылать сообщения между ментором и участниками
- Завершать чат командой `/end`

**Автор:** Denis Odesskiy  
**Организация:** MyFreeIT

### Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/mentoring-bot.git
2. Перейдите в каталог проекта и создайте виртуальное окружение:
   ```bash
    cd mentoring-bot
    python -m venv venv
    source venv/bin/activate  # для Windows: venv\Scripts\activate
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
4. Создайте файл .env с переменными:
   ```bash
   BOT_TOKEN=your_telegram_bot_token
   MENTOR_ID=your_mentor_id
   ACCESS_PASSWORD=your_access_password
5. Запустите бота:
   ```bash
   python mentoringbot.py
