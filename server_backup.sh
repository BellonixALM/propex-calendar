#!/bin/bash
# server_backup.sh – щоденний резервний архів проекту та завантаження в S3 (або інший bucket)
#
# 1) Заархівувати весь проект (виключаючи .git, node_modules if desired)
# 2) Завантажити архів у S3 за допомогою aws cli
# 3) Видалити локальні архіви старші за 7 днів

# Параметри (замініть на ваші значення)
S3_BUCKET="YOUR_S3_BUCKET_NAME"   # <-- ваш bucket
BACKUP_DIR="$(pwd)"
DATE=$(date +%F)
ARCHIVE="${BACKUP_DIR}/backup_${DATE}.tgz"

# 1. Створити архів (виключаємо .git та node_modules)
#   Якщо у вас немає node_modules у репозиторії, можна видалити --exclude='node_modules'

tar --exclude='./.git' --exclude='node_modules' --exclude='backup_*.tgz' --exclude='*.tgz' -czf "$ARCHIVE" -C "$BACKUP_DIR" .

# 2. Завантажити в S3 (потребує налаштованих AWS credentials)
#   Якщо ви користуєтесь іншим інструментом (gsutil, rclone), замініть цю команду
aws s3 cp "$ARCHIVE" "s3://${S3_BUCKET}/backups/" --storage-class STANDARD_IA

# 3. Очистити локальні старі архіви (старші 30 днів)
find "$BACKUP_DIR" -name "backup_*.tgz" -type f -mtime +30 -exec rm {} \;

# Вихідний код 0 в разі успіху
exit 0
