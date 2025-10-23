import asyncio
import os
import time
import aiohttp  # Импортируем aiohttp
from dotenv import load_dotenv  # Импортируем dotenv

from playwright.async_api import async_playwright
import qrcode
from parse_message import parse_message  # Ваш модуль parse_message.py

# --- Загрузка настроек из .env файла ---
load_dotenv()
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "playwright_profile_py")
PARKING_CHAT_NAME = "Чат ожидания"
QUIET_MODE = False

# Настройки для отправки на бэкенд
BACKEND_URL = os.getenv("BACKEND_URL")  # Например, http://127.0.0.1:8000/incoming
SECRET_TOKEN = os.getenv("INCOMING_WEBHOOK_TOKEN")  # Тот же токен, что и в TG-боте


# --- Новая функция для отправки данных ---
async def send_to_backend(session, message_data, chat_title):
    """Асинхронно отправляет данные сообщения на бэкенд Telegram-бота."""
    if not BACKEND_URL:
        print("  - ⚠️ BACKEND_URL не задан. Пропуск отправки.")
        return

    # Собираем payload в формате, который ожидает TG-бот
    payload = {
        "wa_chat_id": chat_title,  # Используем название чата как ID
        "wa_author": message_data.get("author"),
        "wa_body": message_data.get("text"),
        "is_group": 1,  # Предполагаем, что все чаты - группы
        "timestamp": int(time.time()),  # Используем текущее время
        "wa_name": message_data.get(
            "author"
        ),  # В парсере нет отдельного pushname, используем автора
        "wa_number": "Неизвестно",  # Playwright не дает доступа к номеру телефона
    }

    headers = {}
    if SECRET_TOKEN:
        headers["Authorization"] = f"Bearer {SECRET_TOKEN}"

    try:
        # Используем переданную сессию aiohttp для отправки
        async with session.post(
            BACKEND_URL, json=payload, headers=headers, timeout=10
        ) as response:
            if response.status == 200:
                print(f"  - 📤 Успешно отправлено на бэкенд (статус {response.status})")
            else:
                response_text = await response.text()
                print(
                    f"  - ❌ Ошибка отправки на бэкенд (статус {response.status}): {response_text}"
                )
    except Exception as e:
        print(f"  - 💥 Критическая ошибка при отправке на бэкенд: {e}")


async def handle_login(page):
    """
    Проверяет, что загрузилось первым: список чатов или страница входа,
    и в зависимости от этого либо продолжает работу, либо выводит QR-код.
    """
    print("⏳ Определение статуса сессии (ожидание QR-кода или списка чатов)...")
    task_wait_for_qr = asyncio.create_task(
        page.wait_for_selector("div[data-ref]", state="visible")
    )
    task_wait_for_chat_list = asyncio.create_task(
        page.wait_for_selector("#pane-side", state="visible")
    )
    done, pending = await asyncio.wait(
        [task_wait_for_qr, task_wait_for_chat_list], return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    if task_wait_for_chat_list in done:
        if not QUIET_MODE:
            print("✅ Сессия активна, список чатов найден.")
        return
    elif task_wait_for_qr in done:
        print("⚠️ Сессия не найдена. Попытка входа по QR-коду...")
        try:
            await page.screenshot(
                path="login_page_debug.png"
            )  # Скриншот для отладки, если что-то пойдет не так
            qr_code_locator = page.locator("div[data-ref]")
            qr_data = await qr_code_locator.get_attribute("data-ref")
            if not qr_data:
                print("❌ Элемент QR-кода есть, но он пустой.")
                return
            print("📱 Отсканируйте QR-код ниже в приложении WhatsApp:")
            qr = qrcode.QRCode()
            qr.add_data(qr_data)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            print("⏳ Ожидание сканирования QR-кода...")
            await page.wait_for_selector("#pane-side", timeout=120000)
            print("✅ Вход выполнен успешно!")
        except Exception as e:
            print(f"❌ Критическая ошибка во время обработки QR-кода: {e}")
            raise
    else:
        print("❌ Неизвестная ошибка во время ожидания статуса сессии.")
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
        raise Exception("Could not determine page state")


async def main():
    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)
    async with aiohttp.ClientSession() as http_session:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=True,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            print("🌐 Переход на https://web.whatsapp.com/")
            await page.goto("https://web.whatsapp.com/", timeout=60000)
            try:
                await handle_login(page)
            except Exception as e:
                print(f"❌ Завершение работы из-за ошибки при входе: {e}")
                await context.close()
                return
            await park_in_chat(page)

            while True:
                try:
                    pause_duration = 10
                    if not QUIET_MODE:
                        print(
                            f"\n[{time.strftime('%H:%M:%S')}] Пауза {pause_duration} сек перед новым циклом..."
                        )
                    await asyncio.sleep(pause_duration)

                    print(f"[{time.strftime('%H:%M:%S')}] Ищем непрочитанные чаты...")
                    unread_chats_locator = page.locator(
                        '#pane-side div[role="row"]:has(span[aria-label*="непрочитан"])'
                    )

                    # ===================== НАДЕЖНАЯ ЛОГИКА ЗДЕСЬ =====================
                    # ШАГ 1: Собираем не локаторы, а СТАБИЛЬНЫЕ НАЗВАНИЯ чатов
                    unread_chat_titles = []
                    all_unread_locators = await unread_chats_locator.all()
                    for locator in all_unread_locators:
                        try:
                            title = await locator.locator(
                                "span[title]"
                            ).first.get_attribute("title")
                            if title and title != PARKING_CHAT_NAME:
                                unread_chat_titles.append(title)
                        except Exception:
                            pass  # Игнорируем, если не удалось получить название

                    if not unread_chat_titles:
                        if not QUIET_MODE:
                            print("Нет новых непрочитанных чатов.")
                        continue
                    # =================================================================

                    print(
                        f"Найдено {len(unread_chat_titles)} непрочитанных чатов для обработки: {unread_chat_titles}"
                    )
                    last_author_data = {}

                    # ШАГ 2: Итерируемся по списку НАЗВАНИЙ
                    for chat_title in unread_chat_titles:
                        try:
                            print(f"Обрабатываем чат: '{chat_title}'")

                            # ШАГ 3: Выполняем СВЕЖИЙ поиск элемента по названию ПЕРЕД КАЖДЫМ КЛИКОМ
                            # Сначала находим общий блок чата, чтобы получить кол-во сообщений
                            chat_element = page.locator(
                                f'#pane-side div[role="row"]:has(span[title="{chat_title}"]):has(span[aria-label*="непрочитан"])'
                            ).first

                            unread_count_in_chat = 1
                            try:
                                indicator = chat_element.locator(
                                    'span[aria-label*="непрочитан"] > span'
                                ).first
                                count_text = await indicator.inner_text()
                                if count_text.isdigit():
                                    unread_count_in_chat = int(count_text)
                            except Exception:
                                pass

                            if not QUIET_MODE:
                                print(
                                    f"В чате {unread_count_in_chat} непрочитанных сообщени(й/я)."
                                )

                            # Кликаем по самому элементу с названием, это надежнее
                            await chat_element.locator(
                                f'span[title="{chat_title}"]'
                            ).click()

                            await page.wait_for_selector("#main header", timeout=5000)

                            all_message_blocks = page.locator("#main div[data-id]")
                            last_message_blocks = (await all_message_blocks.all())[
                                -unread_count_in_chat:
                            ]

                            for message_block in last_message_blocks:
                                message_data, last_author_data = await parse_message(
                                    message_block, last_author_data
                                )
                                if message_data.get("text"):
                                    print(f"  - ✅ Распарсено: {message_data}")
                                    await send_to_backend(
                                        http_session, message_data, chat_title
                                    )

                        except Exception as e:
                            print(
                                f"❌ Ошибка при обработке чата '{chat_title}': {e}. Пропускаем."
                            )
                            continue  # Переходим к следующему чату в списке

                    print("🏁 Обработка всех чатов завершена.")
                    await park_in_chat(page)

                except Exception as e:
                    print(f"💥 Ошибка в главном цикле: {e}")
                    await asyncio.sleep(15)


# Функция park_in_chat остается почти без изменений
async def park_in_chat(page):
    try:
        is_active = (
            await page.locator(
                f'#main header span[title="{PARKING_CHAT_NAME}"]'
            ).count()
            > 0
        )
        if is_active:
            return

        if not QUIET_MODE:
            print(f"🅿️ Переход в '{PARKING_CHAT_NAME}'...")
        parking_chat_locator = page.locator(
            f'#pane-side span[title="{PARKING_CHAT_NAME}"]'
        )

        if await parking_chat_locator.count() > 0:
            await parking_chat_locator.click()
            if not QUIET_MODE:
                print("✅ Успешно припарковались.")
        else:
            print(
                f"⚠️ Не удалось найти чат '{PARKING_CHAT_NAME}'. Убедитесь, что он виден/закреплен."
            )

    except Exception as e:
        print(f"💥 Ошибка при парковке в чате: {e}")


if __name__ == "__main__":
    if not BACKEND_URL:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ВНИМАНИЕ: Переменная BACKEND_URL не задана в .env файле !!!")
        print("!!! Данные не будут отправляться на сервер Telegram-бота.   !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    asyncio.run(main())
