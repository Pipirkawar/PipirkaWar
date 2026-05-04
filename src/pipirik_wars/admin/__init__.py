"""Admin-слой: FastAPI веб-панель.

Содержит:
- api/ — REST-эндпоинты.
- web/ — Jinja2/HTMX UI.
- auth/ — Telegram Login Widget + 2FA (TOTP).
- rbac/ — роли super_admin, economist, support, read_only.

Тонкий слой: эндпоинты только парсят запрос и вызывают use-case из application/.
Все админские действия пишутся в admin_audit_log.

Может импортировать:
- domain/, application/, infrastructure/, shared/.
"""
