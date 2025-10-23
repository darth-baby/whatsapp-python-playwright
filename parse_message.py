import re
from playwright.async_api import Locator
from typing import Dict, Tuple

# --- Настройки отладки ---
DEBUG_MODE = False  # Установите True для вывода подробной информации


async def parse_message(
    message_row: Locator, last_author_data: Dict
) -> Tuple[Dict, Dict]:
    """
    Принимает локатор строки сообщения (role="row") и кэш данных о последнем авторе.
    Возвращает словарь с данными сообщения и обновленный кэш.
    """
    parsed_data = {
        "time": None,
        "date": None,
        "author": None,
        "text": None,
    }

    if DEBUG_MODE:
        # Печатаем HTML элемента, который пришел на обработку
        html = await message_row.evaluate("element => element.outerHTML")
        print(
            "\n--- DEBUG: Входящий HTML для парсинга ---\n"
            + html[:500]
            + "...\n------------------------------------"
        )

    try:
        # ШАГ 0: Проверяем, является ли эта строка вообще сообщением
        # Настоящие сообщения находятся внутри div.message-in (входящие) или div.message-out (исходящие)
        is_message = (
            await message_row.locator("div.message-in, div.message-out").count() > 0
        )
        if not is_message:
            if DEBUG_MODE:
                print(
                    "  - DEBUG: Это не сообщение (возможно, разделитель даты). Пропускаем."
                )
            return (
                parsed_data,
                last_author_data,
            )  # Возвращаем пустые данные и старый кэш

        # ШАГ 1: Поиск метаданных (автор, время)
        meta_div = message_row.locator("div[data-pre-plain-text]")
        if await meta_div.count() > 0:
            if DEBUG_MODE:
                print(
                    "  - DEBUG: Найден div с метаданными. Это первое сообщение в группе."
                )
            meta_string = await meta_div.get_attribute("data-pre-plain-text") or ""
            match = re.search(
                r"\[(\d{2}:\d{2}), (\d{2}\.\d{2}\.\d{4})\] (.*?):", meta_string
            )
            if match:
                time, date, author = (
                    match.group(1),
                    match.group(2),
                    match.group(3).strip(),
                )
                parsed_data.update({"time": time, "date": date, "author": author})
                # Обновляем кэш для следующих сгруппированных сообщений
                last_author_data = parsed_data.copy()
        else:
            if DEBUG_MODE:
                print(
                    "  - DEBUG: Метаданные не найдены. Это сгруппированное сообщение. Используем кэш."
                )
            # Используем данные из кэша
            parsed_data.update(last_author_data)

        # ШАГ 2: Поиск текста сообщения
        # Ищем span с текстом внутри элемента .copyable-text
        text_span_locator = message_row.locator(
            "div.copyable-text .selectable-text > span"
        )

        if await text_span_locator.count() > 0:
            all_text_parts = await text_span_locator.all_inner_texts()
            text = "".join(all_text_parts)
            parsed_data["text"] = text
            if DEBUG_MODE:
                print(f"  - DEBUG: Текст найден: '{text}'")
        else:
            if DEBUG_MODE:
                print("  - DEBUG: Текстовый span не найден в этом сообщении.")

    except Exception as e:
        print(f"  - 💥 Ошибка при парсинге элемента сообщения: {e}")

    return parsed_data, last_author_data
