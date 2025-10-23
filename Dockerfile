# 1. Используем официальный образ от Playwright. Он включает Python и все зависимости браузера.
# mcr.microsoft.com/playwright/python:v1.44.0-jammy
FROM mcr.microsoft.com/playwright/python:latest

# 2. Устанавливаем рабочую директорию внутри контейнера.
# Все последующие команды будут выполняться из этой папки.
WORKDIR /app

# 3. Копируем файл с зависимостями в рабочую директорию.
COPY requirements.txt .

# 4. Устанавливаем Python-библиотеки, указанные в requirements.txt.
# --no-cache-dir - хорошая практика, чтобы не раздувать размер образа.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем все остальные файлы вашего проекта (main.py, parse_message.py) в рабочую директорию.
COPY . .

# 6. Указываем команду, которая будет выполняться при запуске контейнера.
CMD ["python", "main.py"]