#!/bin/bash

# ==========================================
# HOKIMIYAT BOT - DOCKER STARTUP SCRIPT
# ==========================================

set -e

echo "🚀 Hokimiyat Bot Docker Setup"
echo "=============================="

# 1. .env faylini tekshir
if [ ! -f .env ]; then
    echo "⚠️  .env fayli topilmadi!"
    echo "📋 .env.example dan nusxa yaratilmoqda..."
    cp .env.example .env
    echo "✅ .env yaratildi. Iltimos, .env faylini o'zingizning ma'lumotlaringiz bilan to'ldiring."
    echo ""
    echo "Qo'llash: nano .env"
    exit 1
fi

# 2. .env faylida asosiy sozlamalarni tekshir
if ! grep -q "BOT_TOKEN=" .env; then
    echo "❌ BOT_TOKEN ko'rsatilmagan!"
    exit 1
fi

if ! grep -q "ADMIN_IDS=" .env; then
    echo "❌ ADMIN_IDS ko'rsatilmagan!"
    exit 1
fi

echo "✅ Konfiguratsiya tekshirildi"
echo ""

# 3. Docker compose start
echo "🔧 Docker containers ishga tushurilmoqda..."
docker-compose up -d

echo ""
echo "✅ Bot muvaffaqiyatli ishga tushdi!"
echo ""
echo "📊 Status:"
docker-compose ps

echo ""
echo "📖 Foydali buyruqlar:"
echo "  - Loglarni ko'rish:        docker-compose logs -f bot"
echo "  - DB ni tekshirish:        docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db"
echo "  - Redis ni tekshirish:     docker-compose exec redis redis-cli"
echo "  - Stop qilish:             docker-compose down"
echo "  - Complete restart:        docker-compose down -v && docker-compose up -d"
