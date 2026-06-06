@echo off
REM ==========================================
REM HOKIMIYAT BOT - DOCKER STARTUP SCRIPT (Windows)
REM ==========================================

echo.
echo 🚀 Hokimiyat Bot Docker Setup
echo ==============================

REM 1. .env faylini tekshir
if not exist .env (
    echo ⚠️  .env fayli topilmadi!
    echo 📋 .env.example dan nusxa yaratilmoqda...
    copy .env.example .env
    echo ✅ .env yaratildi. Iltimos, .env faylini o'zingizning ma'lumotlaringiz bilan to'ldiring.
    echo.
    echo Qo'llash: notepad .env
    exit /b 1
)

echo ✅ Konfiguratsiya tekshirildi
echo.

REM 2. Docker compose start
echo 🔧 Docker containers ishga tushurilmoqda...
docker-compose up -d

if errorlevel 1 (
    echo ❌ Xato! Docker compose sozlamasi tekshiring.
    pause
    exit /b 1
)

echo.
echo ✅ Bot muvaffaqiyatli ishga tushdi!
echo.
echo 📊 Status:
docker-compose ps

echo.
echo 📖 Foydali buyruqlar:
echo   - Loglarni ko'rish:        docker-compose logs -f bot
echo   - DB ni tekshirish:        docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db
echo   - Redis ni tekshirish:     docker-compose exec redis redis-cli
echo   - Stop qilish:             docker-compose down
echo   - Complete restart:        docker-compose down -v && docker-compose up -d
echo.
pause
