#!/bin/bash
# Установка cron задач для гибридной синхронизации
# Ежедневная инкрементальная синхронизация (03:15)
# Еженедельная валидация целостности (воскресенье 02:30)

# Функция установки cron задач
install_sync_cron() {
    echo "Установка cron задач для синхронизации..."
    
    # Создание временного cron файла
    CRON_TEMP="/tmp/sync_cron_temp"
    
    # Сохранение существующих cron задач
    crontab -l 2>/dev/null > "$CRON_TEMP"
    
    # Добавление новых задач синхронизации
    cat >> "$CRON_TEMP" << 'EOF'

# Гибридная синхронизация AI памяти
# Инкрементальная синхронизация каждые 3 часа
0 */3 * * * cd /home/dev-avk/projects/persistent-ai-memory && source venv/bin/activate && python incremental_sync.py >> /home/dev-avk/projects/persistent-ai-memory/logs/cron.log 2>&1

# Еженедельная валидация целостности (воскресенье в 02:30) 
30 2 * * 0 cd /home/dev-avk/projects/persistent-ai-memory && source venv/bin/activate && python validate_integrity.py >> /home/dev-avk/projects/persistent-ai-memory/logs/cron.log 2>&1

# Ротация логов каждый месяц (1 число в 01:00)
0 1 1 * * find /home/dev-avk/projects/persistent-ai-memory/logs -name "*.log" -mtime +30 -delete

EOF
    
    # Установка новых cron задач
    crontab "$CRON_TEMP"
    
    # Удаление временного файла
    rm -f "$CRON_TEMP"
    
    echo "Cron задачи установлены успешно:"
    echo "- Инкрементальная синхронизация: каждые 3 часа (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00)"
    echo "- Еженедельная валидация: Воскресенье 02:30"
    echo "- Ротация логов: 1 число каждого месяца"
}

# Функция удаления cron задач
remove_sync_cron() {
    echo "Удаление cron задач синхронизации..."
    
    # Создание временного файла без задач синхронизации
    crontab -l 2>/dev/null | grep -v "persistent-ai-memory" | grep -v "Гибридная синхронизация" | grep -v "incremental_sync.py" | grep -v "validate_integrity.py" > /tmp/cron_clean
    
    # Установка очищенного crontab
    crontab /tmp/cron_clean
    rm -f /tmp/cron_clean
    
    echo "Cron задачи синхронизации удалены"
}

# Проверка статуса cron задач
check_sync_cron() {
    echo "Текущие cron задачи синхронизации:"
    crontab -l 2>/dev/null | grep -E "(persistent-ai-memory|incremental_sync|validate_integrity)" || echo "Нет активных задач синхронизации"
}

# Тест инкрементальной синхронизации
test_incremental_sync() {
    echo "Тестирование инкрементальной синхронизации..."
    cd /home/dev-avk/projects/persistent-ai-memory
    source venv/bin/activate
    python incremental_sync.py
}

# Тест валидации целостности
test_validation() {
    echo "Тестирование валидации целостности..."
    cd /home/dev-avk/projects/persistent-ai-memory
    source venv/bin/activate
    python validate_integrity.py
}

# Главное меню
main_menu() {
    echo "Управление cron задачами гибридной синхронизации"
    echo "================================================"
    echo "1. Установить cron задачи"
    echo "2. Удалить cron задачи" 
    echo "3. Проверить статус"
    echo "4. Тест инкрементальной синхронизации"
    echo "5. Тест валидации целостности"
    echo "6. Выход"
    echo
    read -p "Выберите действие (1-6): " choice
    
    case $choice in
        1) install_sync_cron ;;
        2) remove_sync_cron ;;
        3) check_sync_cron ;;
        4) test_incremental_sync ;;
        5) test_validation ;;
        6) exit 0 ;;
        *) echo "Неверный выбор"; main_menu ;;
    esac
}

# Обработка аргументов командной строки
if [[ $# -gt 0 ]]; then
    case $1 in
        install) install_sync_cron ;;
        remove) remove_sync_cron ;;
        status) check_sync_cron ;;
        test-inc) test_incremental_sync ;;
        test-val) test_validation ;;
        *) echo "Использование: $0 [install|remove|status|test-inc|test-val]" ;;
    esac
else
    main_menu
fi
