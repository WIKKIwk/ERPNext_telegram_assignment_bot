# Telegram Assignment Bot

Mustaqil Telegram bot loyihasi: guruhga qo'shilgach, admin `/assign_manager` buyrug'i orqali shaxsiy chatda `/start` bosgan foydalanuvchilardan birini sales manager sifatida tayinlaydi. Har foydalanuvchi faqat bitta guruhga, har bir guruh esa faqat bitta sales managerga biriktiriladi.

## Tuzilishi
- `assignment_bot/config.py` — `.env` dagi `ASSIGNMENT_BOT_TOKEN`, `ASSIGNMENT_ADMIN_ID(S)`, ERPNext URL va hisobot parametrlari kabi sozlamalarni o'qiydi.
- `assignment_bot/storage.py` — foydalanuvchi, guruh va tayinlash ma'lumotlarini sqlite’da saqlaydi.
- `assignment_bot/bot.py` — `python-telegram-bot` handlerlari: `/start`, `/assign_manager`, `/report`, `/new`, `/clear` va inline tugmalar orqali boshqaruv.
- `tests/test_storage.py` — asosiy constraint’lar va credential saqlash oqimini qamrab olgan unittests.

## Ishga tushirish
1. Virtual muhit tayyorlang va kerakli paketlarni o'rnating:
   ```bash
   pip install "python-telegram-bot[rate-limiter]>=20.7"
   ```
2. `.env` yoki muhit o'zgaruvchilarini belgilang:
   ```bash
   export ASSIGNMENT_BOT_TOKEN=YOUR_TOKEN
   export ASSIGNMENT_ADMIN_ID=123456789
   ```
3. Botni lokalda polling rejimida ishga tushirish (oddiy misol):
   ```bash
   python -m assignment_bot
   ```
   
## Test
```bash
cd telegram_assignment_bot
PYTHONPATH=. python -m unittest tests.test_storage
```

Kelgusida ERPNext API integratsiyasi qo'shiladi, ammo hozircha loyiha mustaqil bot sifatida ishlaydi.


## Docker orqali ishga tushirish

1. `.env.example` ni `.env` sifatida nusxalab, token va boshqa sozlamalarni kiriting:
   ```bash
   cp .env.example .env
   ```
2. Docker va Docker Compose o'rnatilganiga ishonch hosil qiling.
3. Terminalda `make` yozing — bu `docker compose up --build` ni ishga tushiradi.
4. Bot loglarini ko'rish uchun `make logs`, to'xtatish uchun `make down`.

### ERPNext bilan ishlash (ixtiyoriy)
- `.env` faylida `ERPVERIFY_BASE_URL=https://example.com` (ERPNext domeni) va kerak bo'lsa `ERPVERIFY_ENDPOINT=/api/method/frappe.auth.get_logged_user` ni qo'shing — shunda API kalit/secret tekshiriladi.
- Hisobotlar uchun resurs va maydonlarni sozlash: `REPORT_RESOURCE=Sales Order`, `REPORT_FIELDS=["name", "customer_name", "grand_total"]`, `REPORT_LIMIT=5`.
- `/report` komandasi guruhning sales manager credentiallari orqali ERPNext API’dan ma’lumot olib keladi.
- `/new` komandasi guruh ichida faqat tayinlangan sales manager uchun ishlaydi: u Item code → nom → Item Group → UOM bosqichlarini shu guruhda to'ldiradi, bot ERPNext’dagi mavjud guruh/UOM ro'yxatini inline tugmalar (sahifalash bilan) ko'rsatadi va yakunda haqiqiy `Item` yozuvini yaratadi. O'lchov birligi bosqichida bot “🔍 UOM qidirish” tugmasi orqali inline menyuni birdan ochib, tez qidirishga imkon beradi.
- Sales manager API credentiallari tasdiqlangach, bot guruh nomidagi dastlabki ikki so'zdan keyingi qismi asosida avtomatik yangi `Customer` yarata oladi. Standart `customer_group` va `customer_type` qiymatlarini `ERP_CUSTOMER_GROUP` va `ERP_CUSTOMER_TYPE` o'zgaruvchilari bilan belgilash mumkin.
- `/status` komandasi guruh yoki shaxsiy chatda joriy tayinlash holatini ko'rsatadi; `/reset_api` esa managerga API kalitlarini qaytadan kiritish imkonini beradi.
