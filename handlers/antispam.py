"""
Проверки антиспама: повторяющиеся сообщения, избыток эмодзи, флуд.

Состояние хранится в памяти процесса (для лёгкого бота на одну группу
этого достаточно; при перезапуске счётчики просто обнуляются).
"""
import re
import time
from collections import defaultdict, deque

from config import (
    DUPLICATE_THRESHOLD,
    DUPLICATE_WINDOW_SECONDS,
    EMOJI_LIMIT,
    FLOOD_MESSAGES,
    FLOOD_WINDOW_SECONDS,
)

# user_id -> deque[(timestamp, text)] — последние сообщения пользователя.
# maxlen ограничивает память на пользователя вне зависимости от активности.
_recent_messages: dict[int, deque] = defaultdict(lambda: deque(maxlen=30))

# Приблизительные unicode-диапазоны эмодзи (без внешних зависимостей —
# для лёгкого бота этого достаточно, идеальной точности не требуется)
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "]"
)


def register_message(user_id: int, text: str) -> None:
    """Запоминает сообщение пользователя — вызывается один раз в начале обработки."""
    _recent_messages[user_id].append((time.time(), text or ""))


def is_duplicate_spam(user_id: int, text: str) -> bool:
    """True, если это же сообщение отправлено DUPLICATE_THRESHOLD и более раз за окно."""
    if not text:
        return False

    now = time.time()
    dq = _recent_messages[user_id]
    same_count = sum(
        1 for ts, msg in dq if msg == text and now - ts <= DUPLICATE_WINDOW_SECONDS
    )
    return same_count >= DUPLICATE_THRESHOLD


def has_too_many_emoji(text: str) -> bool:
    """True, если в сообщении больше EMOJI_LIMIT эмодзи."""
    return len(_EMOJI_PATTERN.findall(text)) > EMOJI_LIMIT


def is_flooding(user_id: int) -> bool:
    """True, если пользователь отправил больше FLOOD_MESSAGES сообщений за FLOOD_WINDOW_SECONDS."""
    now = time.time()
    dq = _recent_messages[user_id]
    recent_count = sum(1 for ts, _ in dq if now - ts <= FLOOD_WINDOW_SECONDS)
    return recent_count > FLOOD_MESSAGES
