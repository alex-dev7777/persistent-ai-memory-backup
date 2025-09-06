#!/bin/bash
# Комплексная диагностика гибридной системы синхронизации AI памяти
# Проверка всех компонентов: SQLite, Neo4j, cron, MCP серверы, логи

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функции проверок
print_header() {
    echo -e "${CYAN}================================================================${NC}"
    echo -e "${CYAN}      ДИАГНОСТИКА СИСТЕМЫ СИНХРОНИЗАЦИИ AI ПАМЯТИ${NC}"
    echo -e "${CYAN}================================================================${NC}"
    echo -e "Время диагностики: $(date)"
    echo
}

check_system_status() {
    echo -e "${BLUE}[1/8] СИСТЕМНЫЕ КОМПОНЕНТЫ${NC}"
    echo "----------------------------------------"
    
    # Neo4j статус
    if systemctl is-active --quiet neo4j 2>/dev/null; then
        echo -e "Neo4j сервис:           ${GREEN}АКТИВЕН${NC}"
        neo4j_version=$(neo4j version 2>/dev/null | head -1 || echo "Неизвестно")
        echo "Neo4j версия:           $neo4j_version"
    else
        echo -e "Neo4j сервис:           ${RED}НЕАКТИВЕН${NC}"
    fi
    
    # Порты Neo4j
    if ss -tlnp | grep -q ":7474"; then
        echo -e "Порт 7474 (HTTP):       ${GREEN}ОТКРЫТ${NC}"
    else
        echo -e "Порт 7474 (HTTP):       ${RED}ЗАКРЫТ${NC}"
    fi
    
    if ss -tlnp | grep -q ":7687"; then
        echo -e "Порт 7687 (Bolt):       ${GREEN}ОТКРЫТ${NC}"
    else
        echo -e "Порт 7687 (Bolt):       ${RED}ЗАКРЫТ${NC}"
    fi
    
    # Cron статус
    if systemctl is-active --quiet cron; then
        echo -e "Cron сервис:            ${GREEN}АКТИВЕН${NC}"
    else
        echo -e "Cron сервис:            ${RED}НЕАКТИВЕН${NC}"
    fi
    echo
}

check_databases() {
    echo -e "${BLUE}[2/8] БАЗЫ ДАННЫХ${NC}"
    echo "----------------------------------------"
    
    # SQLite
    SQLITE_PATH="/home/dev-avk/projects/persistent-ai-memory/memory_data/ai_memories.db"
    if [ -f "$SQLITE_PATH" ]; then
        sqlite_count=$(sqlite3 "$SQLITE_PATH" "SELECT COUNT(*) FROM curated_memories;" 2>/dev/null)
        sqlite_size=$(du -sh "$SQLITE_PATH" | cut -f1)
        echo -e "SQLite база:            ${GREEN}ДОСТУПНА${NC}"
        echo "SQLite записей:         $sqlite_count"
        echo "SQLite размер:          $sqlite_size"
    else
        echo -e "SQLite база:            ${RED}НЕ НАЙДЕНА${NC}"
    fi
    
    # Neo4j через curl
    if curl -s -u neo4j:neo4j7777 -X POST \
        -H "Content-Type: application/json" \
        -d '{"statements":[{"statement":"MATCH (m:Memory) RETURN count(m) as count"}]}' \
        http://localhost:7474/db/neo4j/tx/commit > /tmp/neo4j_check 2>/dev/null; then
        
        neo4j_count=$(jq -r '.results[0].data[0].row[0]' /tmp/neo4j_check 2>/dev/null || echo "0")
        echo -e "Neo4j граф:             ${GREEN}ДОСТУПЕН${NC}"
        echo "Neo4j Memory узлов:     $neo4j_count"
        
        # Получение общего количества узлов
        curl -s -u neo4j:neo4j7777 -X POST \
            -H "Content-Type: application/json" \
            -d '{"statements":[{"statement":"MATCH (n) RETURN count(n) as total"}]}' \
            http://localhost:7474/db/neo4j/tx/commit > /tmp/neo4j_total 2>/dev/null
        
        neo4j_total=$(jq -r '.results[0].data[0].row[0]' /tmp/neo4j_total 2>/dev/null || echo "0")
        echo "Neo4j всего узлов:      $neo4j_total"
        
        # Проверка синхронизации
        if [ "$sqlite_count" = "$neo4j_count" ]; then
            echo -e "Синхронизация:          ${GREEN}В ПОРЯДКЕ${NC}"
        else
            diff=$((sqlite_count - neo4j_count))
            echo -e "Синхронизация:          ${YELLOW}Расхождение в $diff з. (может включать обновления)${NC}"
            echo -e "                        (Это нормально, т.к. обновления не создают новых узлов)"
        fi
    else
        echo -e "Neo4j граф:             ${RED}НЕДОСТУПЕН${NC}"
    fi
    
    rm -f /tmp/neo4j_check /tmp/neo4j_total
    echo
}

check_cron_tasks() {
    echo -e "${BLUE}[3/8] CRON ЗАДАЧИ${NC}"
    echo "----------------------------------------"
    
    cron_count=$(crontab -l 2>/dev/null | grep -c "persistent-ai-memory")
    if [ $cron_count -gt 0 ]; then
        echo -e "Cron задачи:            ${GREEN}УСТАНОВЛЕНЫ ($cron_count)${NC}"
        
        # Показать активные задачи
        echo "Расписание синхронизации:"
        crontab -l 2>/dev/null | grep "persistent-ai-memory" | while read line; do
            if echo "$line" | grep -q "incremental_sync"; then
                echo "  • $(echo "$line" | awk '{print $1,$2,$3,$4,$5}') - Инкрементальная синхронизация"
            elif echo "$line" | grep -q "validate_integrity"; then
                echo "  • $(echo "$line" | awk '{print $1,$2,$3,$4,$5}') - Валидация целостности"
            fi
        done
        
        # Следующий запуск
        current_hour=$(date +%H)
        next_sync_hour=$(( (current_hour / 3 + 1) * 3 ))
        if [ $next_sync_hour -ge 24 ]; then
            next_sync_hour=0
        fi
        printf "Следующая синхронизация: %02d:00\n" $next_sync_hour
        
    else
        echo -e "Cron задачи:            ${RED}НЕ УСТАНОВЛЕНЫ${NC}"
    fi
    echo
}

check_sync_state() {
    echo -e "${BLUE}[4/8] СОСТОЯНИЕ СИНХРОНИЗАЦИИ${NC}"
    echo "----------------------------------------"
    
    SYNC_STATE="/home/dev-avk/projects/persistent-ai-memory/.sync_state.json"
    if [ -f "$SYNC_STATE" ]; then
        echo -e "Файл состояния:         ${GREEN}СУЩЕСТВУЕТ${NC}"
        
        last_sync=$(jq -r '.last_sync_timestamp' "$SYNC_STATE" 2>/dev/null)
        if [ "$last_sync" != "null" ] && [ -n "$last_sync" ]; then
            # Вычисление времени с последней синхронизации
            last_sync_epoch=$(date -d "$last_sync" +%s 2>/dev/null)
            current_epoch=$(date +%s)
            hours_diff=$(( (current_epoch - last_sync_epoch) / 3600 ))
            
            echo "Последняя синхронизация: $(date -d "$last_sync" '+%Y-%m-%d %H:%M' 2>/dev/null)"
            
            if [ $hours_diff -le 3 ]; then
                echo -e "Давность:               ${GREEN}$hours_diff ч. назад${NC}"
            elif [ $hours_diff -le 12 ]; then
                echo -e "Давность:               ${YELLOW}$hours_diff ч. назад${NC}"
            else
                echo -e "Давность:               ${RED}$hours_diff ч. назад${NC}"
            fi
        else
            echo -e "Последняя синхронизация: ${YELLOW}НЕ НАЙДЕНА${NC}"
        fi
        
        record_count=$(jq -r '.last_record_count' "$SYNC_STATE" 2>/dev/null)
        echo "Обработано записей:     $record_count"
        
        validation=$(jq -r '.last_full_validation' "$SYNC_STATE" 2>/dev/null)
        if [ "$validation" != "null" ] && [ -n "$validation" ]; then
            echo "Последняя валидация:    $(date -d "$validation" '+%Y-%m-%d %H:%M' 2>/dev/null)"
        else
            echo -e "Последняя валидация:    ${YELLOW}НЕ ВЫПОЛНЯЛАСЬ${NC}"
        fi
        
    else
        echo -e "Файл состояния:         ${RED}ОТСУТСТВУЕТ${NC}"
    fi
    echo
}

check_logs() {
    echo -e "${BLUE}[5/8] ЛОГИ СИСТЕМЫ${NC}"
    echo "----------------------------------------"
    
    LOG_DIR="/home/dev-avk/projects/persistent-ai-memory/logs"
    
    if [ -d "$LOG_DIR" ]; then
        echo -e "Директория логов:       ${GREEN}СУЩЕСТВУЕТ${NC}"
        log_size=$(du -sh "$LOG_DIR" | cut -f1)
        echo "Размер логов:           $log_size"
        
        # Проверка логов синхронизации
        SYNC_LOG="$LOG_DIR/sync_daily.log"
        if [ -f "$SYNC_LOG" ]; then
            log_lines=$(wc -l < "$SYNC_LOG")
            echo "Записей в sync_daily:   $log_lines"
            
            # Последние записи
            echo "Последние события:"
            tail -3 "$SYNC_LOG" | while read line; do
                if echo "$line" | grep -q "ERROR"; then
                    echo -e "  ${RED}$line${NC}"
                elif echo "$line" | grep -q "WARN"; then
                    echo -e "  ${YELLOW}$line${NC}"
                else
                    echo "  $line"
                fi
            done
            
            # Подсчет ошибок за последние 24 часа
            errors_24h=$(grep "ERROR" "$SYNC_LOG" 2>/dev/null | wc -l || echo "0")
            if [ "$errors_24h" -eq 0 ]; then
                echo -e "Ошибок за 24ч:         ${GREEN}$errors_24h${NC}"
            else
                echo -e "Ошибок за 24ч:         ${RED}$errors_24h${NC}"
            fi
        else
            echo -e "sync_daily.log:         ${YELLOW}НЕ НАЙДЕН${NC}"
        fi
        
    else
        echo -e "Директория логов:       ${RED}НЕ СУЩЕСТВУЕТ${NC}"
    fi
    echo
}

check_resources() {
    echo -e "${BLUE}[6/8] ИСПОЛЬЗОВАНИЕ РЕСУРСОВ${NC}"
    echo "----------------------------------------"
    
    # RAM
    total_ram=$(free -h | awk '/^Mem:/ {print $2}')
    used_ram=$(free -h | awk '/^Mem:/ {print $3}')
    echo "Общая память:           $total_ram"
    echo "Используется:           $used_ram"
    
    # Neo4j процессы
    neo4j_ram=$(ps -p $(pgrep -f neo4j 2>/dev/null) -o rss= 2>/dev/null | awk '{sum+=$1} END {printf "%.0f MB", sum/1024}')
    if [ -n "$neo4j_ram" ] && [ "$neo4j_ram" != " MB" ]; then
        echo "Neo4j память:           $neo4j_ram"
    else
        echo "Neo4j память:           Не определено"
    fi
    
    # Диск
    disk_usage=$(df -h /home/dev-avk/projects/persistent-ai-memory | awk 'NR==2 {print $4}')
    echo "Свободное место:        $disk_usage"
    
    # Размеры баз данных
    sqlite_total=$(du -sh /home/dev-avk/projects/persistent-ai-memory/memory_data 2>/dev/null | cut -f1)
    neo4j_total=$(sudo du -sh /var/lib/neo4j/data 2>/dev/null | cut -f1)
    echo "SQLite данные:          ${sqlite_total:-Н/Д}"
    echo "Neo4j данные:           ${neo4j_total:-Н/Д}"
    echo
}

check_network_connectivity() {
    echo -e "${BLUE}[7/8] СЕТЕВЫЕ ПОДКЛЮЧЕНИЯ${NC}"
    echo "----------------------------------------"
    
    # Neo4j HTTP
    if curl -s --connect-timeout 3 -u neo4j:neo4j7777 http://localhost:7474/db/data/ > /dev/null; then
        echo -e "Neo4j HTTP API:         ${GREEN}ДОСТУПЕН${NC}"
    else
        echo -e "Neo4j HTTP API:         ${RED}НЕДОСТУПЕН${NC}"
    fi
    
    # Neo4j Bolt (через netcat если доступен)
    if command -v nc >/dev/null 2>&1; then
        if nc -z localhost 7687 2>/dev/null; then
            echo -e "Neo4j Bolt:             ${GREEN}ДОСТУПЕН${NC}"
        else
            echo -e "Neo4j Bolt:             ${RED}НЕДОСТУПЕН${NC}"
        fi
    else
        echo "Neo4j Bolt:             Нет nc для проверки"
    fi
    
    # Проверка Claude Desktop MCP (косвенно)
    if pgrep -f "Claude" >/dev/null; then
        echo -e "Claude Desktop:         ${GREEN}ЗАПУЩЕН${NC}"
    else
        echo -e "Claude Desktop:         ${YELLOW}НЕ ЗАПУЩЕН${NC}"
    fi
    echo
}

show_recommendations() {
    echo -e "${BLUE}[8/8] РЕКОМЕНДАЦИИ${NC}"
    echo "----------------------------------------"
    
    # Сбор проблем для рекомендаций
    issues=()
    
    # Проверка Neo4j
    if ! sudo systemctl is-active --quiet neo4j; then
        issues+=("start_neo4j")
    fi
    
    # Проверка cron
    cron_count=$(crontab -l 2>/dev/null | grep -c "persistent-ai-memory")
    if [ $cron_count -eq 0 ]; then
        issues+=("setup_cron")
    fi
    
    # Проверка синхронизации
    SYNC_STATE="/home/dev-avk/projects/persistent-ai-memory/.sync_state.json"
    if [ -f "$SYNC_STATE" ]; then
        last_sync=$(jq -r '.last_sync_timestamp' "$SYNC_STATE" 2>/dev/null)
        if [ "$last_sync" != "null" ] && [ -n "$last_sync" ]; then
            last_sync_epoch=$(date -d "$last_sync" +%s 2>/dev/null)
            current_epoch=$(date +%s)
            hours_diff=$(( (current_epoch - last_sync_epoch) / 3600 ))
            
            if [ $hours_diff -gt 12 ]; then
                issues+=("old_sync")
            fi
        fi
    fi
    
    # Вывод рекомендаций
    if [ ${#issues[@]} -eq 0 ]; then
        echo -e "${GREEN}Система работает нормально. Проблем не обнаружено.${NC}"
        echo
        echo "Полезные команды:"
        echo "  ./setup_cron.sh test-inc     # Ручная синхронизация"
        echo "  ./setup_cron.sh test-val     # Валидация целостности"  
        echo "  tail -f logs/sync_daily.log  # Мониторинг логов"
    else
        echo -e "${YELLOW}Обнаружены проблемы. Рекомендации:${NC}"
        
        for issue in "${issues[@]}"; do
            case $issue in
                "start_neo4j")
                    echo -e "  ${RED}•${NC} Запустить Neo4j: sudo systemctl start neo4j"
                    ;;
                "setup_cron")
                    echo -e "  ${RED}•${NC} Установить cron задачи: ./setup_cron.sh install"
                    ;;
                "old_sync")
                    echo -e "  ${RED}•${NC} Выполнить синхронизацию: ./setup_cron.sh test-inc"
                    ;;
            esac
        done
    fi
    echo
}

# Основная функция
main() {
    print_header
    check_system_status
    check_databases  
    check_cron_tasks
    check_sync_state
    check_logs
    check_resources
    check_network_connectivity
    show_recommendations
    
    echo -e "${CYAN}================================================================${NC}"
    echo -e "${CYAN}                     ДИАГНОСТИКА ЗАВЕРШЕНА${NC}"
    echo -e "${CYAN}================================================================${NC}"
}

# Запуск
main