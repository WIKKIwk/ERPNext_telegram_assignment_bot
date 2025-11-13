# Telegram Assignment Bot Bench

Bu repodan foydalanib, Telegram Assignment Bot’ni bir buyruq bilan ishga tushirishingiz mumkin. Bot ERPNext bilan bog‘lanib, sales manager tayinlash, `/new` orqali item yaratish va guruhga mos mijozlarni avtomatik hosil qilishni qo‘llab-quvvatlaydi.

## Tez start

1. Reponi klon qiling:
   ```bash
   git clone <repo-url>
   cd <repo-folder>
   ```
2. `.env.example` faylini nusxa oling va ma’lumotlarni to‘ldiring:
   ```bash
   cp apps/telegram_assignment_bot/.env.example apps/telegram_assignment_bot/.env
   # keyin token, admin ID, ERP URL va h.k. ni kiriting
   ```
3. Docker va docker compose o‘rnatilgan bo‘lishi kerak. Keyin botni qurib, ishga tushiring:
   ```bash
   make
   ```
   Bu buyruq `apps/telegram_assignment_bot` ichidagi `docker compose up --build` ni chaqiradi.

## Foydali buyruqlar

- `make logs` – konteyner loglarini kuzatish.
- `make down` – bot konteynerini to‘xtatish.

Botga oid batafsil sozlamalar va foydalanish yo‘riqlari `apps/telegram_assignment_bot/README.md` ichida berilgan.
