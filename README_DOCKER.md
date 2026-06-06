# 🐳 Hokimiyat Bot - Docker Setup

Bu papkada **hokimiyat-bot** Telegram botini Docker orqali ishga tushirish uchun kerakli barcha fayllar mavjud.

## 📁 Fayllar Tuzilishi

```
├── docker-compose.yml          # Docker Compose konfiguratsiya (PostgreSQL + Redis + Bot)
├── Dockerfile                  # Bot uchun Docker image
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Git ignore rules
│
├── setup.sh                   # Linux/MacOS uchun complete setup script
├── setup.bat                  # Windows uchun complete setup script
├── start.sh                   # Linux/MacOS uchun quick start
├── start.bat                  # Windows uchun quick start
│
├── QUICKSTART.md             # 30 soniyada tezkor boshlash
├── DOCKER_SETUP.md           # To'liq o'rnatish va boshqarish qo'llanmasi
├── MAINTENANCE.md            # Production maintenance guide
└── README.md                 # Bu fayl
```

## 🚀 Tezkor Boshlash (30 soniya)

### Linux/MacOS
```bash
chmod +x setup.sh
./setup.sh
```

### Windows
```cmd
setup.bat
```

## 📋 Manual Setup (bosqichma-bosqich)

### 1️⃣ Loyihani yuklab olish
```bash
git clone https://github.com/cipher-edu/hokimiyat-bot.git
cd hokimiyat-bot

# Docker setup fayllarini ko'chiring (agar yo'q bo'lsa):
# docker-compose.yml, Dockerfile, requirements.txt
```

### 2️⃣ Environment sozlash
```bash
cp .env.example .env
# .env faylini tahrir qilip ma'lumotlarni kiriting
```

### 3️⃣ Docker container'larni ishga tushirish
```bash
docker-compose up -d
```

### 4️⃣ Status tekshirish
```bash
docker-compose ps
docker-compose logs -f bot
```

## 🔧 Asosiy Buyruqlar

| Buyruq | Tavsifi |
|--------|---------|
| `docker-compose up -d` | Services ishga tushirish |
| `docker-compose down` | Services to'xtatish |
| `docker-compose logs -f bot` | Bot loglarini real-time ko'rish |
| `docker-compose ps` | Container statuslarini ko'rish |
| `docker-compose restart bot` | Botni qayta ishga tushirish |

## 🔐 Environment Variables (.env)

```env
# Required
BOT_TOKEN="bot_tokeningiz"           # @BotFather orqali
ADMIN_IDS="123456789,987654321"      # Admin ID'lari
REQUIRED_CHANNELS="@kanal1,-1001234567890"  # Majburiy kanallar

# Database
DB_TYPE="postgresql"                 # "postgresql" yoki "sqlite"
POSTGRES_PASSWORD="strong_password"  # PostgreSQL paroli

# Optional
ENCRYPTION_KEY="hex_string_32_chars" # Shifrlash kalit
REDIS_PASSWORD="redis_password"      # Redis paroli (optional)
```

## 📊 Kontejnerlar

Bot 3 ta Docker container dan iborat:

1. **postgres** - Ma'lumotlar bazasi (PostgreSQL 16)
2. **redis** - Cache va FSM (Redis 7)
3. **bot** - Telegram bot (Python 3.11)

Barcha service'lar bridge network'da ishlaydi va avtomatik sog'lanadi.

## 🛠️ Troubleshooting

### Bot ishlamaydi
```bash
docker-compose logs bot
# Log'larni tekshirib xatolarni ko'rish
```

### PostgreSQL ulanmaydi
```bash
docker-compose restart postgres
# Wait 30 seconds va qayta ishga tushiring
```

### Port conflict
`docker-compose.yml` da port raqamlarini o'zgartiring:
```yaml
postgres:
  ports:
    - "5433:5432"  # 5433 externasal, 5432 internal
```

## 📚 Qo'shimcha Qo'llanmalar

- **QUICKSTART.md** - Tezkor boshlash
- **DOCKER_SETUP.md** - To'liq setup va management
- **MAINTENANCE.md** - Production va debugging

## 🔐 Security Tips (Production)

1. Kuchli parollar o'rnatish
2. `.env` faylini `.gitignore` ga qo'shish
3. PostgreSQL bind address'ini localhost'ga chegaralash
4. Regular backups olish
5. Log monitoring va alerting

## 📞 Bot Commands

- `/admin` - So'rovnoma boshqarish paneli
- `/rek` - Reklama post generatori
- `/send_ad` - Ommaviy xabarnoma

## 🔗 Links

- [GitHub Repository](https://github.com/cipher-edu/hokimiyat-bot)
- [Docker Documentation](https://docs.docker.com/)
- [Aiogram Framework](https://docs.aiogram.dev/)
- [PostgreSQL Docs](https://www.postgresql.org/docs/)
- [Redis Docs](https://redis.io/documentation)

## 💡 Tips

- Bot loglarini always monitorla: `docker-compose logs -f bot`
- Regular backup: `docker-compose exec postgres pg_dump ...`
- Performance check: `docker stats`
- Network debugging: `docker network inspect hokimiyat_network`

---

**Version:** 1.0  
**Last Updated:** 2026-06-06  
**Created for:** Hokimiyat Bot Docker Setup
