# 🐳 HOKIMIYAT BOT - DOCKER SETUP GUIDE

## 📋 Talablar

- **Docker** (v20.10+)
- **Docker Compose** (v2.0+)
- **Git**

## 🔧 O'rnatish

### 1️⃣ Loyihani yuklab olish

```bash
git clone https://github.com/cipher-edu/hokimiyat-bot.git
cd hokimiyat-bot
```

### 2️⃣ .env faylini sozlash

```bash
cp .env.example .env
```

`.env` faylini oching va quyidagi qiymatlarni to'ldiring:

```env
BOT_TOKEN="sizning_bot_tokeningiz"           # @BotFather orqali olingan
ADMIN_IDS="123456789,987654321"              # Admin ID raqamlari
REQUIRED_CHANNELS="@kanal1,-1001234567890"   # Majburiy kanallar
ENCRYPTION_KEY="0123456789abcdef0123456789abcdef"  # 32 bayt kalit
```

**Yangi encryption key generatsiya qilish:**
```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

### 3️⃣ Docker Compose orqali ishga tushirish

#### Linux/MacOS:
```bash
chmod +x start.sh
./start.sh
```

#### Windows:
```cmd
start.bat
```

#### Yoki to'g'ridan-to'g'ri:
```bash
docker-compose up -d
```

**Kontejnerlar ishga tushish kutishi (40-60 soniya):**
```bash
docker-compose logs -f bot
```

## 📊 Kontejnerlarni boshqarish

### Status ko'rish
```bash
docker-compose ps
```

### Loglarni ko'rish
```bash
# Barcha loglar
docker-compose logs

# Faqat bot
docker-compose logs -f bot

# Faqat PostgreSQL
docker-compose logs -f postgres

# Faqat Redis
docker-compose logs -f redis
```

### Database'ga ulaning

#### PostgreSQL:
```bash
docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db
```

**Asosiy SQL buyruqlar:**
```sql
-- Foydalanuvchilar
SELECT * FROM users;

-- So'rovnomalar
SELECT * FROM polls;

-- Votlar
SELECT * FROM votes;

-- \q - chiqish
```

#### Redis:
```bash
docker-compose exec redis redis-cli

# Asosiy comandlar:
KEYS *
DBSIZE
FLUSHDB (Barcha datani o'chirish)
QUIT
```

## 🔄 Restart va Cleanup

### Soft restart (kod o'zgarishlari uchun):
```bash
docker-compose restart bot
```

### Hard restart (barcha kontejnerlar):
```bash
docker-compose restart
```

### Kompleks restart (volumes o'chib, yangi data bilan):
```bash
docker-compose down -v
docker-compose up -d
```

## 🚨 Muammo hal qilish

### Kontejner ishlamaydi
```bash
# Loglarni tekshir
docker-compose logs bot

# Kontejner ID'sini ko'r
docker ps -a

# Kontejnerni o'chir va qayta yaratı
docker-compose down
docker-compose up -d
```

### PostgreSQL ulanmaydi
```bash
# PostgreSQL health check
docker-compose exec postgres pg_isready

# PostgreSQL loglarni ko'r
docker-compose logs postgres

# Database restart
docker-compose restart postgres
```

### Redis ulanmaydi
```bash
# Redis test
docker-compose exec redis redis-cli ping

# Redis loglarni ko'r
docker-compose logs redis
```

### Port conflict
Agar port allaqachon ishlatilgan bo'lsa, `docker-compose.yml` da port raqamini o'zgartiring:

```yaml
postgres:
  ports:
    - "5433:5432"  # 5432 o'rniga 5433

redis:
  ports:
    - "6380:6379"  # 6379 o'rniga 6380
```

## 📁 Volume ma'lumotlari

- **postgres_data:** PostgreSQL database fayllar
- **redis_data:** Redis persistence data

**Volumelarni tekshirish:**
```bash
docker volume ls
docker volume inspect hokimiyat-postgres_postgres_data
```

## 🌐 Network

Barcha service'lar `hokimiyat_network` bridgeda ishlaydi. Bot -> PostgreSQL va Redis ga `hostname` orqali muloqot qiladi.

## 🔐 Security

### Production uchun:
1. `.env` faylini `.gitignore` ga qo'shing:
```bash
echo ".env" >> .gitignore
```

2. Kuchli parol o'rnating:
```env
POSTGRES_PASSWORD="very-strong-random-password"
REDIS_PASSWORD="another-strong-password"
```

3. PostgreSQL bind address-ni o'zgartiring:
```yaml
# docker-compose.yml
postgres:
  ports:
    - "127.0.0.1:5432:5432"  # Faqat localhost
```

## 📞 Admin Komandalari

Bot ishga tushmagan holda, admin uchun mavjud buyruqlar:

```
/admin yoki /polls  - So'rovnoma paneli
/rek                - Reklama post generatori
/send_ad            - Ommaviy xabarnoma
```

## 📚 Qo'shimcha Resurslar

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Redis Docker](https://hub.docker.com/_/redis)
- [Aiogram Framework](https://docs.aiogram.dev/)
