# 🔧 HOKIMIYAT BOT - MAINTENANCE GUIDE

## 📊 Monitoring

### Kontejner Performance
```bash
# Real-time stats
docker stats hokimiyat-bot hokimiyat-postgres hokimiyat-redis

# Memory/CPU usage
docker-compose ps
```

### Disk Usage
```bash
# Volume size'ini ko'rish
docker system df

# Unused images/containers/volumes cleanup
docker system prune -a --volumes
```

## 🔄 Backup va Restore

### PostgreSQL Backup

```bash
# Full backup
docker-compose exec postgres pg_dump -U hokimiyat_user -d hokimiyat_db > backup.sql

# Database size
docker-compose exec postgres psql -U hokimiyat_user -d hokimiyat_db -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

### PostgreSQL Restore

```bash
# Backup dan qayta o'klamosh
docker-compose exec -T postgres psql -U hokimiyat_user -d hokimiyat_db < backup.sql
```

### Redis Backup

```bash
# Redis dump.rdb yuklab olish
docker cp hokimiyat-redis:/data/dump.rdb ./redis_backup.rdb

# Qayta o'klash
docker cp ./redis_backup.rdb hokimiyat-redis:/data/dump.rdb
docker-compose restart redis
```

## 🔐 Security Updates

### Image updates
```bash
# Yangi image pull qiling
docker-compose pull

# Kontejnerlarni qayta build qiling
docker-compose up -d --build
```

### PostgreSQL upgrade
```bash
# Backup olish (MUHIM!)
docker-compose exec postgres pg_dump -U hokimiyat_user -d hokimiyat_db > backup_before_upgrade.sql

# docker-compose.yml da image version o'zgartiring
# image: postgres:17-alpine

# Upgrade
docker-compose down
docker volume rm hokimiyat-postgres_postgres_data  # Agar schema compatibility bo'lsa
docker-compose up -d
```

## 🚨 Emergency Procedures

### Kontejner crashed bo'lsa
```bash
# Restart
docker-compose restart bot

# Yoki hard restart
docker-compose down
docker-compose up -d
```

### Database corrupted bo'lsa
```bash
# Database reset (barcha data yo'q bo'ladi!)
docker-compose down -v
docker-compose up -d
```

### Disk space problem
```bash
# Unused images/containers o'chish
docker system prune -a

# Specific volume o'chish (DIQQAT!)
docker volume rm hokimiyat-postgres_postgres_data
```

## 📈 Scaling

### Multiple bot instances (advanced)
```yaml
# docker-compose.yml da
services:
  bot:
    ...
  bot-2:
    build: .
    container_name: hokimiyat-bot-2
    environment: ...
    depends_on: ...
```

## 🔐 Production Recommendations

### 1. Stronger Passwords
```env
POSTGRES_PASSWORD="$(openssl rand -base64 32)"
REDIS_PASSWORD="$(openssl rand -base64 32)"
```

### 2. Resource Limits
```yaml
services:
  bot:
    deploy:
      resources:
        limits:
          cpus: '1.5'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### 3. Health Checks
```yaml
services:
  bot:
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; print('healthy')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 4. Restart Policy
```yaml
services:
  bot:
    restart: always  # or on-failure
```

### 5. Environment Separation
```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 📝 Logging Best Practices

### Centralized logging (optional)
```bash
# Loglarni file'ga yozish
docker-compose logs > logs/all-services.log

# Specific service logs
docker-compose logs bot > logs/bot.log
docker-compose logs postgres > logs/postgres.log
```

### Log rotation
```yaml
services:
  bot:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "10"
```

## 🔍 Debugging Tips

### Container shell'ga kirish
```bash
# Bot container
docker-compose exec bot /bin/bash

# PostgreSQL
docker-compose exec postgres /bin/bash

# Redis
docker-compose exec redis /bin/sh
```

### Network debugging
```bash
# Container IP
docker-compose exec bot hostname -I

# Port listening
docker-compose exec bot netstat -tlnp
```

### Environment o'zgaruvchilari tekshirish
```bash
docker-compose exec bot env | grep -E "BOT_|DB_|REDIS_"
```

## 📞 Support Commands

```bash
# Version check
docker --version
docker-compose --version

# Network status
docker network inspect hokimiyat_network

# Volume info
docker volume inspect hokimiyat-postgres_postgres_data

# Image info
docker images | grep hokimiyat
```
