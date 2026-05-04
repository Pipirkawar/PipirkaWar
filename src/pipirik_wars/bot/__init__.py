"""Bot-слой: тонкий слой aiogram.

Содержит:
- handlers/ — точки входа команд (/start, /profile, /forest, ...).
- middlewares/ — auth, locale, throttle, dau_gate, error_handler.
- filters/ — фильтры по уровню/длине/клану.
- presenters/ — рендер сообщений.

Хэндлеры ТОЛЬКО парсят апдейт и вызывают use-case из application/.
Никакой бизнес-логики здесь быть не должно.

Может импортировать:
- domain/, application/, infrastructure/, shared/.
"""
