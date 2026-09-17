"""
Фильтр запрещённых слов. Список загружается один раз из bad_words.txt
при старте бота и хранится в памяти.
"""
import re
from typing import Optional

from config import BAD_WORDS_FILE

_bad_words: set = set()


def load_bad_words() -> None:
    """Читает bad_words.txt в память. Вызывается один раз при старте бота."""
    global _bad_words
    try:
        with open(BAD_WORDS_FILE, "r", encoding="utf-8") as f:
            _bad_words = {
                line.strip().lower()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            }
    except FileNotFoundError:
        _bad_words = set()


def contains_bad_word(text: str) -> Optional[str]:
    """Возвращает найденное запрещённое слово или None. Сравнение — по целым словам."""
    if not text or not _bad_words:
        return None

    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    for word in words:
        if word in _bad_words:
            return word
    return None
