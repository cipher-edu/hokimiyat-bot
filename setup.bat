@echo off
REM ==========================================
REM HOKIMIYAT BOT - COMPLETE SETUP SCRIPT
REM GitHub dan clone qilib Docker setup
REM ==========================================

setlocal enabledelayedexpansion

cls
echo.
echo ========================================
echo 🚀 HOKIMIYAT BOT - COMPLETE SETUP
echo ========================================
echo.

REM 1. Check dependencies
echo.
echo 1️⃣  Checking dependencies...
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo ❌ Git is not installed!
    pause
    exit /b 1
)
echo ✅ Git found

where docker >nul 2>nul
if errorlevel 1 (
    echo ❌ Docker is not installed!
    pause
    exit /b 1
)
echo ✅ Docker found

where docker-compose >nul 2>nul
if errorlevel 1 (
    echo ❌ Docker Compose is not installed!
    pause
    exit /b 1
)
echo ✅ Docker Compose found

echo.

REM 2. Clone repository
set "PROJECT_DIR=hokimiyat-bot"

if exist "%PROJECT_DIR%" (
    echo.
    echo 2️⃣  Directory %PROJECT_DIR% already exists
    echo.
    set /p response="Overwrite? (y/n): "
    if /i "!response!"=="y" (
        rmdir /s /q "%PROJECT_DIR%"
    ) else (
        for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c%%a%%b)
        for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)
        set "PROJECT_DIR=hokimiyat-bot-!mydate!!mytime!"
        echo Using directory: !PROJECT_DIR!
    )
)

echo.
echo 2️⃣  Cloning repository...
git clone https://github.com/cipher-edu/hokimiyat-bot.git "%PROJECT_DIR%"
if errorlevel 1 (
    echo ❌ Git clone failed!
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"
echo ✅ Repository cloned

echo.

REM 3. Setup .env file
echo 3️⃣  Setting up environment variables...

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env"
        echo ✅ .env created from .env.example
    ) else (
        echo Creating default .env...
        (
            echo # TELEGRAM BOT SETTINGS
            echo BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
            echo ADMIN_IDS="123456789,987654321"
            echo REQUIRED_CHANNELS="@your_channel,-1001234567890"
            echo ENCRYPTION_KEY="0123456789abcdef0123456789abcdef"
            echo.
            echo # DATABASE
            echo DB_TYPE="postgresql"
            echo POSTGRES_DB="hokimiyat_db"
            echo POSTGRES_USER="hokimiyat_user"
            echo POSTGRES_PASSWORD="hokimiyat_pass_secure"
            echo POSTGRES_HOST="postgres"
            echo POSTGRES_PORT="5432"
            echo.
            echo # REDIS
            echo REDIS_HOST="redis"
            echo REDIS_PORT="6379"
        ) > .env
        echo ✅ Default .env created
    )
    
    echo.
    echo ⚠️  IMPORTANT: Edit .env file and set your values:
    echo.
    echo  notepad .env
    echo.
    pause
) else (
    echo .env already exists, skipping
)

echo.

REM 4. Create Docker images and start services
echo 4️⃣  Building Docker images and starting services...
echo This may take a few minutes...
echo.

docker-compose build
if errorlevel 1 (
    echo ❌ Docker build failed!
    pause
    exit /b 1
)

docker-compose up -d
if errorlevel 1 (
    echo ❌ Docker compose up failed!
    pause
    exit /b 1
)

echo.

REM 5. Wait for services
echo 5️⃣  Waiting for services to be healthy...
echo This may take 30-60 seconds...
echo.

for /l %%i in (1,1,60) do (
    docker-compose exec -T postgres pg_isready -U hokimiyat_user >nul 2>nul
    if errorlevel 0 (
        echo ✅ PostgreSQL is ready
        goto done_waiting
    )
    if %%i equ 10 (
        echo Waiting... (10 seconds elapsed^)
    )
    if %%i equ 30 (
        echo Waiting... (30 seconds elapsed^)
    )
    if %%i equ 50 (
        echo Waiting... (50 seconds elapsed^)
    )
    timeout /t 1 /nobreak >nul
)

:done_waiting
timeout /t 5 /nobreak >nul

echo.

REM 6. Check status
echo 6️⃣  Checking container status...
echo.
docker-compose ps

echo.

REM 7. Show logs
echo 7️⃣  Bot logs (first 20 lines):
echo.
docker-compose logs --tail=20 bot

echo.

REM 8. Summary
echo.
echo ========================================
echo ✅ SETUP COMPLETE!
echo ========================================
echo.
echo 📊 Services Status:
docker-compose ps
echo.
echo 📖 Useful Commands:
echo   View logs:           docker-compose logs -f bot
echo   Restart bot:         docker-compose restart bot
echo   Stop services:       docker-compose down
echo   Database access:     docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db
echo   Redis access:        docker-compose exec redis redis-cli
echo.
echo 📚 Documentation:
echo   - Quick Start:       QUICKSTART.md
echo   - Full Guide:        DOCKER_SETUP.md
echo   - Maintenance:       MAINTENANCE.md
echo.
echo ⚠️  Next Steps:
echo   1. Monitor bot logs
echo   2. Test bot on Telegram
echo   3. Check database
echo.
pause
