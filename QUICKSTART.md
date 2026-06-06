# 🚀 HOKIMIYAT BOT - TEZKOR BOSHLASH

## ✅ 30 Soniyada Docker orqali ishga tushirish

### Qadam 1: Repository clone qiling
```bash
git clone https://github.com/cipher-edu/hokimiyat-bot.git
cd hokimiyat-bot
```

### Qadam 2: .env faylini sozlang
```bash
cp .env.example .env

# .env faylini tahrir qiling va qo'ygan qiymatlarni kiriting:
# BOT_TOKEN, ADMIN_IDS, REQUIRED_CHANNELS, ENCRYPTION_KEY
```

### Qadam 3: Docker containers ishga tushurinng
```bash
# Linux/MacOS
chmod +x start.sh && ./start.sh

# Windows
start.bat

# Yoki to'g'ridan-to'g'ri
docker-compose up -d
```

### Qadam 4: Status tekshiring
```bash
docker-compose ps
docker-compose logs -f bot
```

**🎉 Bot ishga tushdi!** 

---

## 🛠️ Talab qiladigan Ma'lumotlar

Bot ko'rsatmalarini to'liq ko'rish uchun:
- **BOT_TOKEN**: @BotFather orqali olingan Telegram bot token
- **ADMIN_IDS**: Admin Telegram ID (raqam formatida)
- **REQUIRED_CHANNELS**: Majburiy a'zolik kanalları (@name yoki -1001234567890 formatida)
- **ENCRYPTION_KEY**: Shifrlash kalit (32 xonali heksadetsimal)

---

## 📊 Kontejner Management

```bash
# Loglarni ko'rish
docker-compose logs -f bot

# Restart
docker-compose restart bot

# Stop
docker-compose down

# Complete reset (barcha data o'chib ketadi!)
docker-compose down -v
docker-compose up -d
```

---

## 🔗 PostgreSQL Database

```bash
# DB ga ulaning
docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db

# Asosiy SQL
SELECT * FROM users;
SELECT * FROM polls;
SELECT * FROM votes;
```

---

## 🔴 Muammolar

**"Connection refused"**
→ `docker-compose restart` qiling va 30 soniya kutib oling

**"Port already in use"**
→ `docker-compose.yml` da port raqamini o'zgartiring

**Bot loglarida xata**
→ `.env` sozlamalarni tekshiring va `ENCRYPTION_KEY` qayta yarating

---

## 📖 To'liq qo'llanma

Batafsilroq ma'lumot uchun `DOCKER_SETUP.md` faylni o'qing.
