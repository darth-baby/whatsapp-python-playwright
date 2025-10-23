import asyncio
from playwright.async_api import async_playwright
import os
from parse_message import parse_message

# --- Настройки ---
PROFILE_DIR = os.path.join(os.path.dirname(__file__), 'playwright_profile_py')
PARKING_CHAT_NAME = "Чат ожидания"

async def main():
    # ... (код загрузки браузера остается без изменений) ...
    # Я убрал его для краткости, ваш код здесь правильный.

    # ...
    # Полный код до цикла while
    # ...
    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = context.pages[0] if context.pages else await context.new_page()
        # ... (код с циклом retry для загрузки)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🌐 Попытка {attempt + 1}/{max_retries}: Переход на https://web.whatsapp.com/")
                await page.goto("https://web.whatsapp.com/", timeout=60000)
                print("⏳ Ожидание загрузки интерфейса WhatsApp...")
                await page.wait_for_selector('#pane-side', timeout=120000)
                print("✅ Интерфейс успешно загружен.")
                break 
            except Exception as e:
                print(f"❌ Ошибка на попытке {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10)
                else:
                    print("❌ Все попытки исчерпаны.")
                    await context.close()
                    return

        await park_in_chat(page)

        while True:
            try:
                print("\n-------------------- Новый цикл --------------------")
                print("Ищем непрочитанные чаты...")
                
                unread_chats_locator = page.locator('#pane-side div[role="row"]:has(span[aria-label*="непрочитан"])')
                
                # ===================== КЛЮЧЕВОЕ ИЗМЕНЕНИЕ =====================
                # Получаем СТАТИЧЕСКИЙ список всех локаторов в самом начале
                all_unread_chats = await unread_chats_locator.all()
                count = len(all_unread_chats)
                # =============================================================

                if count == 0:
                    print("Нет непрочитанных чатов. Ждем 10 секунд...")
                    await asyncio.sleep(10)
                    continue

                print(f"Найдено {count} непрочитанных чатов.")
                print("Начинаем обработку...")
                last_author_data = {}
                
                # Итерируемся по нашему статическому списку
                for chat_element in all_unread_chats:
                    chat_title_locator = chat_element.locator('span[title]').first
                    chat_title = await chat_title_locator.get_attribute('title') or ""

                    # ... (остальной код внутри цикла for остается АБСОЛЮТНО таким же) ...
                    if chat_title == PARKING_CHAT_NAME:
                        print(f"⚠️ Пропускаем сообщение в '{PARKING_CHAT_NAME}'.")
                        await chat_element.click()
                        continue

                    print(f"Обрабатываем чат: '{chat_title}'")
                    unread_count_in_chat = 1
                    try:
                        indicator = chat_element.locator('span[aria-label*="непрочитан"] > span').first
                        count_text = await indicator.inner_text()
                        if count_text.isdigit():
                            unread_count_in_chat = int(count_text)
                    except Exception:
                        pass
                    
                    print(f"В чате {unread_count_in_chat} непрочитанных сообщени(й/я).")
                    
                    await chat_element.click()

                    try:
                        print("Ожидаем загрузки контейнера чата #main...")
                        await page.wait_for_selector('#main header', timeout=5000)
                        print("✅ Контейнер чата #main загружен.")
                    except Exception as e:
                        print(f"⚠️ Не удалось открыть чат '{chat_title}' за 5 секунд. Пропускаем. Ошибка: {e}")
                        continue

                    all_message_blocks = page.locator('#main div[data-id]')
                    last_message_blocks = (await all_message_blocks.all())[-unread_count_in_chat:]
                    
                    print(f"Найдено {len(last_message_blocks)} блоков сообщений для анализа.")
                    
                    for message_block in last_message_blocks:
                        message_data, last_author_data = await parse_message(message_block, last_author_data)
                        if message_data.get('text'):
                            print(f"  - ✅ Распарсено: {message_data}")
                
                print("🏁 Обработка всех чатов завершена.")
                await park_in_chat(page)

            except Exception as e:
                print(f"💥 Ошибка в главном цикле: {e}")
                await asyncio.sleep(15)

            await asyncio.sleep(5)

# Функция park_in_chat остается без изменений
async def park_in_chat(page):
    try:
        is_active = await page.locator(f'#main header span[title="{PARKING_CHAT_NAME}"]').count() > 0
        if is_active:
            return

        print(f"🅿️ Переход в '{PARKING_CHAT_NAME}'...")
        parking_chat_locator = page.locator(f'#pane-side span[title="{PARKING_CHAT_NAME}"]')
        
        if await parking_chat_locator.count() > 0:
            await parking_chat_locator.click()
            print("✅ Успешно припарковались.")
        else:
            print(f"⚠️ Не удалось найти чат '{PARKING_CHAT_NAME}'. Убедитесь, что он виден/закреплен.")

    except Exception as e:
        print(f"💥 Ошибка при парковке в чате: {e}")

if __name__ == "__main__":
    asyncio.run(main())