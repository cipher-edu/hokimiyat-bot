# 🤖 Telegram Ovoz Berish Boti

Bu Telegram boti ovoz berish jarayonlarini avtomatlashtirish, foydalanuvchilarni ro'yxatga olish, majburiy a'zolikni tekshirish va adminlar uchun qulay boshqaruv panelini ta'minlash uchun ishlab chiqilgan. Loyiha turli ehtiyojlarga mos keladigan bir nechta versiyalarni o'z ichiga oladi.

## ✨ Asosiy Funksiyalar

*   **So'rovnomalarni Boshqarish:** Adminlar uchun so'rovnomalarni yaratish, tahrirlash, aktiv/noaktiv qilish va natijalarni ko'rish.
*   **Foydalanuvchi Jarayoni:**
    *   Majburiy kanallarga a'zolikni qat'iy tekshirish.
    *   Telefon raqami orqali ro'yxatdan o'tish (raqamlar shifrlanadi).
    *   Botlardan himoyalanish uchun CAPTCHA tizimi.
*   **Reklama Vositalari:**
    *   `/rek`: So'rovnoma asosida reklama postini (rasm + matn + deep link tugmalar) tayyorlash.
    *   `/send_ad`: Barcha foydalanuvchilarga ommaviy xabarnoma (reklama) yuborish.
*   **Dinamik Ma'lumotlar Bazasi:** `.env` faylidagi sozlamaga qarab **SQLite** yoki **PostgreSQL** bilan ishlash imkoniyati.
*   **Ishonchlilik:** Foydalanuvchi holatlari (FSM) va vaqtinchalik ma'lumotlar **Redis**'da saqlanadi.

## 🛠️ Texnologiyalar Steki

*   **Asosiy freymvork:** [aiogram 3.x](https://docs.aiogram.dev/en/latest/)
*   **Ma'lumotlar bazasi:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async)
    *   [SQLite](https://www.sqlite.org/index.html) (soddaroq sozlamalar uchun)
    *   [PostgreSQL](https://www.postgresql.org/) (kuchli va masshtablanuvchi)
*   **Kesh/FSM:** [Redis](https://redis.io/)
*   **Sozlamalar:** [pydantic-settings](https://docs.pydantic.dev/latest/usage/pydantic_settings/) (`.env` fayli uchun)
*   **Shifrlash:** [cryptography](https://cryptography.io/en/latest/)

---

## 🚀 Ishga Tushirish Yo'riqnomasi

Loyiha uch xil konfiguratsiyaga ega fayllarni o'z ichiga oladi. O'zingizga mos keladigan variantni tanlang.

| Variant | Fayl Nomi | Ma'lumotlar Bazasi | FSM/Kesh | Sozlamalar | Tavsiya |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1-variant (Professional)** | `bot_postgres_sql.py` | `PostgreSQL` yoki `SQLite` | `Redis` | `.env` fayli | **Eng yaxshi va ishonchli variant** ✅ |
| **2-variant (Soddalashtirilgan)**| `bot_redis_sqlite.py` | Faqat `SQLite` | `Redis` | `.env` fayli | Redis kerak, lekin PostgreSQL shart bo'lmasa |
| **3-variant (Eng Oddiy)** | `main.py` | Faqat `SQLite` | `Xotira (RAM)` | Kod ichida | **Faqat test qilish uchun** ⚠️ |

---

### ⚙️ 1-variant: Professional (PostgreSQL/SQLite + Redis)

Bu versiya eng to'liq, moslashuvchan va production (haqiqiy server) uchun tavsiya etiladi.

**Fayl:** `bot_postgres_sql.py`

#### 1. Dastlabki talablar:
Kompyuteringiz yoki serveringizda **Python**, **Git**, **Redis Server** va **PostgreSQL Server** o'rnatilgan bo'lishi kerak.

#### 2. Loyihani yuklab olish:
```bash
git clone <sizning_repozitoriy_havolangiz>
cd <loyiha_papkasi>
```

#### 3. Virtual muhit yaratish va aktivlashtirish:
```bash
python -m venv venv
# Windows uchun:
venv\Scripts\activate
# Linux/MacOS uchun:
source venv/bin/activate
```

#### 4. Kerakli kutubxonalarni o'rnatish:
```bash
pip install aiogram sqlalchemy aiosqlite redis pydantic-settings cryptography asyncpg
```

#### 5. `.env` faylini sozlash:
Loyiha papkasida `.env` nomli fayl yarating va quyidagi namunani ichiga ko'chiring. So'ng kerakli ma'lumotlarni to'ldiring.

```ini
# .env

# --- ASOSIY SOZLAMALAR ---
BOT_TOKEN="sizning_bot_tokeningiz"
ADMIN_IDS="sizning_admin_id_raqamingiz"
REQUIRED_CHANNELS="@kanal_nomi1,-1001234567890"
ENCRYPTION_KEY="generatsiya_qilingan_maxfiy_kalit"

# --- MA'LUMOTLAR BAZASI SOZLAMALARI ---
# Qaysi ma'lumotlar bazasini ishlatishni tanlang: "sqlite" yoki "postgresql"
DB_TYPE="postgresql"

# --- SQLite sozlamalari (DB_TYPE="sqlite" bo'lsa ishlatiladi) ---
SQLITE_DB_NAME="vote_bot.db"

# --- PostgreSQL sozlamalari (DB_TYPE="postgresql" bo'lsa ishlatiladi) ---
POSTGRES_DB="your_db_name"
POSTGRES_USER="your_db_user"
POSTGRES_PASSWORD="your_db_password"
POSTGRES_HOST="localhost"
POSTGRES_PORT=5432

# --- REDIS SOZLAMALARI ---
REDIS_HOST="localhost"
REDIS_PORT=6379
# REDIS_PASSWORD="sizning_redis_parolingiz"
```

#### 6. Botni ishga tushirish:
```bash
python bot_postgres_sql.py
```

---

### ⚙️ 2-variant: Soddalashtirilgan (SQLite + Redis)

Bu versiya `PostgreSQL`'siz, faqat `SQLite` bilan ishlaydi. Sozlash osonroq.

**Fayl:** `bot_redis_sqlite.py`

#### 1. Kerakli kutubxonalarni o'rnatish:
```bash
pip install aiogram sqlalchemy aiosqlite redis pydantic-settings cryptography
```

#### 2. `.env` faylini sozlash:
Ushbu versiya uchun `.env` fayli soddaroq bo'ladi:

```ini
# .env

BOT_TOKEN="sizning_bot_tokeningiz"
ADMIN_IDS="sizning_admin_id_raqamingiz"
REQUIRED_CHANNELS="@kanal_nomi1,-1001234567890"
ENCRYPTION_KEY="generatsiya_qilingan_maxfiy_kalit"

# MA'LUMOTLAR BAZASI
DB_NAME="vote_bot_redis.db"

# REDIS SOZLAMALARI
REDIS_HOST="localhost"
REDIS_PORT=6379
# REDIS_PASSWORD="sizning_redis_parolingiz"
```

#### 3. Botni ishga tushirish:
```bash
python bot_redis_sqlite.py
```

---

### ⚙️ 3-variant: Eng Oddiy (SQLite, Redis'siz, Sozlamalar kod ichida)

Bu versiya **faqat test qilish** va bot logikasini tezda tekshirish uchun mo'ljallangan. U `.env` faylini va `Redis` serverini talab qilmaydi.

**DIQQAT:** Bot qayta ishga tushganda barcha vaqtinchalik ma'lumotlar (FSM, CAPTCHA) o'chib ketadi.

**Fayl:** `main.py`

#### 1. Kerakli kutubxonalarni o'rnatish:
```bash
pip install aiogram sqlalchemy aiosqlite cryptography
```

#### 2. Kodni tahrirlash:
`main.py` faylini oching va `AppSettings` klassi ichidagi quyidagi maydonlarni o'zingizning ma'lumotlaringiz bilan to'ldiring:
*   `BOT_TOKEN`
*   `ADMIN_IDS`
*   `REQUIRED_CHANNELS`
*   `ENCRYPTION_KEY`

#### 3. Botni ishga tushirish:
```bash
python main.py
```

## 👨‍💻 Admin Buyruqlari

*   `/admin` yoki `/polls` - So'rovnomalarni boshqarish panelini ochadi.
*   `/rek` - So'rovnoma asosida reklama postini (rasm + matn + deep link tugmalar) tayyorlash jarayonini boshlaydi.
*   `/send_ad` - Barcha foydalanuvchilarga ommaviy xabarnoma (reklama) yuborish jarayonini boshlaydi.

## ☁️ Serverga Yuklash (Deployment)

Botni doimiy ishlab turishi uchun **VPS/VDS** (masalan, DigitalOcean, Hetzner) yoki **PaaS** (masalan, Render.com) platformalariga yuklash tavsiya etiladi.

*   **Render.com:** Eng oson va qulay variant. Bepul rejalari doirasida `PostgreSQL`, `Redis` va `Web Service`'ni birgalikda ishga tushirish mumkin.
*   **VPS:** To'liq nazoratni beradi. `PostgreSQL` va `Redis`'ni o'zingiz o'rnatib, botni `systemd` servisi orqali doimiy ishga tushirishingiz kerak bo'ladi.