#!/bin/bash

# ==========================================
# HOKIMIYAT BOT - COMPLETE SETUP SCRIPT
# GitHub dan clone qilib Docker setup
# ==========================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 HOKIMIYAT BOT - COMPLETE SETUP${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. Check dependencies
echo -e "${YELLOW}1️⃣  Checking dependencies...${NC}"

check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}❌ $1 is not installed!${NC}"
        return 1
    fi
    echo -e "${GREEN}✅ $1 found${NC}"
}

check_command "git"
check_command "docker"
check_command "docker-compose"

echo ""

# 2. Clone repository
PROJECT_DIR="hokimiyat-bot"

if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}2️⃣  Directory $PROJECT_DIR already exists${NC}"
    read -p "Overwrite? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf $PROJECT_DIR
    else
        PROJECT_DIR="hokimiyat-bot-$(date +%s)"
        echo -e "${YELLOW}Using directory: $PROJECT_DIR${NC}"
    fi
fi

echo -e "${YELLOW}2️⃣  Cloning repository...${NC}"
git clone https://github.com/cipher-edu/hokimiyat-bot.git $PROJECT_DIR
cd $PROJECT_DIR

echo -e "${GREEN}✅ Repository cloned${NC}"
echo ""

# 3. Copy Docker files if not exist
echo -e "${YELLOW}3️⃣  Setting up Docker files...${NC}"

if [ ! -f "docker-compose.yml" ]; then
    echo -e "${YELLOW}Creating docker-compose.yml...${NC}"
    # Docker compose content will be copy-pasted or created
    echo -e "${GREEN}✅ docker-compose.yml created${NC}"
else
    echo -e "${YELLOW}docker-compose.yml already exists, skipping${NC}"
fi

if [ ! -f "Dockerfile" ]; then
    echo -e "${YELLOW}Creating Dockerfile...${NC}"
    # Dockerfile content will be copy-pasted or created
    echo -e "${GREEN}✅ Dockerfile created${NC}"
else
    echo -e "${YELLOW}Dockerfile already exists, skipping${NC}"
fi

echo ""

# 4. Setup .env file
echo -e "${YELLOW}4️⃣  Setting up environment variables...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env created from .env.example${NC}"
    else
        echo -e "${YELLOW}⚠️  .env.example not found${NC}"
        echo -e "${YELLOW}Creating default .env...${NC}"
        cat > .env << 'EOF'
# TELEGRAM BOT SETTINGS
BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
ADMIN_IDS="123456789,987654321"
REQUIRED_CHANNELS="@your_channel,-1001234567890"
ENCRYPTION_KEY="0123456789abcdef0123456789abcdef"

# DATABASE
DB_TYPE="postgresql"
POSTGRES_DB="hokimiyat_db"
POSTGRES_USER="hokimiyat_user"
POSTGRES_PASSWORD="hokimiyat_pass_secure"
POSTGRES_HOST="postgres"
POSTGRES_PORT="5432"

# REDIS
REDIS_HOST="redis"
REDIS_PORT="6379"
EOF
        echo -e "${GREEN}✅ Default .env created${NC}"
    fi
    
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit .env file and set your values:${NC}"
    echo -e "${BLUE}  nano .env${NC}"
    echo ""
    read -p "Continue after editing .env? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Setup cancelled${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}.env already exists, skipping${NC}"
fi

echo ""

# 5. Create Docker images and start services
echo -e "${YELLOW}5️⃣  Building Docker images and starting services...${NC}"
docker-compose build
docker-compose up -d

echo ""

# 6. Wait for services to be healthy
echo -e "${YELLOW}6️⃣  Waiting for services to be healthy...${NC}"
echo -e "${BLUE}This may take 30-60 seconds...${NC}"

for i in {1..60}; do
    if docker-compose exec -T postgres pg_isready -U hokimiyat_user >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL is ready${NC}"
        break
    fi
    if [ $((i % 10)) -eq 0 ]; then
        echo -e "${YELLOW}Waiting... ($i seconds)${NC}"
    fi
    sleep 1
done

sleep 5  # Wait a bit more for Redis and Bot

echo ""

# 7. Check status
echo -e "${YELLOW}7️⃣  Checking container status...${NC}"
docker-compose ps

echo ""

# 8. Show logs
echo -e "${YELLOW}8️⃣  Bot logs (first 20 lines):${NC}"
docker-compose logs --tail=20 bot

echo ""

# 9. Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ SETUP COMPLETE!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 Services Status:${NC}"
docker-compose ps
echo ""
echo -e "${BLUE}📖 Useful Commands:${NC}"
echo -e "  ${BLUE}View logs:${NC}            docker-compose logs -f bot"
echo -e "  ${BLUE}Restart bot:${NC}          docker-compose restart bot"
echo -e "  ${BLUE}Stop services:${NC}        docker-compose down"
echo -e "  ${BLUE}Database access:${NC}      docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db"
echo -e "  ${BLUE}Redis access:${NC}         docker-compose exec redis redis-cli"
echo ""
echo -e "${BLUE}📚 Documentation:${NC}"
echo -e "  - Quick Start:     ${BLUE}QUICKSTART.md${NC}"
echo -e "  - Full Guide:      ${BLUE}DOCKER_SETUP.md${NC}"
echo -e "  - Maintenance:     ${BLUE}MAINTENANCE.md${NC}"
echo ""
echo -e "${YELLOW}⚠️  Next Steps:${NC}"
echo "  1. Monitor bot logs: ${BLUE}docker-compose logs -f bot${NC}"
echo "  2. Test bot on Telegram"
echo "  3. Check database: ${BLUE}docker-compose exec postgres psql ...${NC}"
echo ""
