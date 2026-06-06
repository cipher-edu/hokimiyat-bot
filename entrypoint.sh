#!/bin/sh
set -e

# Choose which bot script to run based on DB_TYPE (env var)
case "${DB_TYPE:-sqlite}" in
  postgresql)
    exec python bot_postgress_sql.py
    ;;
  sqlite)
    exec python bot_redis_sqlite.py
    ;;
  *)
    exec python main.py
    ;;
esac
