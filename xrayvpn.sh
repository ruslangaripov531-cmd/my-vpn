#!/bin/bash
# xrayvpn.sh - быстрая генерация конфигов и управление xray + sing-box (tun)
#
# Расположение: ~/Download/xrayvpn/
# В этой же папке должны лежать:
#   - vless2xray.py
#   - gen-singbox-tun.py
#   - xray         (бинарь xray-core)
#   - sing-box     (бинарь sing-box, если не установлен в систему)
#
# Команды:
#   ./xrayvpn.sh gen "vless://..."     - сгенерировать config.json и singbox-tun.json
#   ./xrayvpn.sh start                 - запустить xray и sing-box (tun)
#   ./xrayvpn.sh stop                  - остановить оба
#   ./xrayvpn.sh restart "vless://..." - сгенерировать конфиг + перезапустить всё
#   ./xrayvpn.sh status                - статус процессов
#   ./xrayvpn.sh log [xray|singbox]    - посмотреть логи (по умолчанию xray)

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG="$DIR/config.json"
SINGBOX_CONF="$DIR/singbox-tun.json"
RUN_DIR="$DIR/run"
mkdir -p "$RUN_DIR"

XRAY_BIN="$DIR/xray"
SINGBOX_BIN="$DIR/sing-box"
[ -x "$SINGBOX_BIN" ] || SINGBOX_BIN="sing-box"   # использовать из PATH, если своего нет

SOCKS_PORT=1080

gen() {
    local link="${1:?Нужна vless:// ссылка}"
    echo "[*] Генерирую $CONFIG"
    python3 "$DIR/vless2xray.py" "$link" --socks-port "$SOCKS_PORT" -o "$CONFIG"
    echo "[*] Генерирую $SINGBOX_CONF"
    python3 "$DIR/gen-singbox-tun.py" --socks-port "$SOCKS_PORT" -o "$SINGBOX_CONF"
}

start() {
    if [ ! -f "$CONFIG" ] || [ ! -f "$SINGBOX_CONF" ]; then
        echo "Конфиги не найдены. Сначала: $0 gen \"vless://...\"" >&2
        exit 1
    fi

    if [ -f "$RUN_DIR/xray.pid" ] && kill -0 "$(cat "$RUN_DIR/xray.pid")" 2>/dev/null; then
        echo "[*] xray уже запущен (pid $(cat "$RUN_DIR/xray.pid"))"
    else
        echo "[*] Запускаю xray"
        nohup "$XRAY_BIN" run -c "$CONFIG" > "$RUN_DIR/xray.log" 2>&1 &
        echo $! > "$RUN_DIR/xray.pid"
        sleep 1
    fi

    if [ -f "$RUN_DIR/singbox.pid" ] && sudo kill -0 "$(cat "$RUN_DIR/singbox.pid")" 2>/dev/null; then
        echo "[*] sing-box уже запущен (pid $(cat "$RUN_DIR/singbox.pid"))"
    else
        echo "[*] Запускаю sing-box (нужны права root для tun)"
        sudo nohup "$SINGBOX_BIN" run -c "$SINGBOX_CONF" > "$RUN_DIR/singbox.log" 2>&1 &
        echo $! > "$RUN_DIR/singbox.pid"
    fi

    echo "[+] Готово."
}

stop() {
    if [ -f "$RUN_DIR/singbox.pid" ]; then
        local pid
        pid="$(cat "$RUN_DIR/singbox.pid")"
        if sudo kill -0 "$pid" 2>/dev/null; then
            echo "[*] Останавливаю sing-box (pid $pid)"
            sudo kill "$pid" 2>/dev/null || true
        fi
        rm -f "$RUN_DIR/singbox.pid"
    fi

    if [ -f "$RUN_DIR/xray.pid" ]; then
        local pid
        pid="$(cat "$RUN_DIR/xray.pid")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "[*] Останавливаю xray (pid $pid)"
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$RUN_DIR/xray.pid"
    fi

    echo "[+] Остановлено."
}

status() {
    if [ -f "$RUN_DIR/xray.pid" ] && kill -0 "$(cat "$RUN_DIR/xray.pid")" 2>/dev/null; then
        echo "xray:     запущен (pid $(cat "$RUN_DIR/xray.pid"))"
    else
        echo "xray:     не запущен"
    fi

    if [ -f "$RUN_DIR/singbox.pid" ] && sudo kill -0 "$(cat "$RUN_DIR/singbox.pid")" 2>/dev/null; then
        echo "sing-box: запущен (pid $(cat "$RUN_DIR/singbox.pid"))"
    else
        echo "sing-box: не запущен"
    fi
}

log() {
    local which="${1:-xray}"
    case "$which" in
        xray) tail -f "$RUN_DIR/xray.log" ;;
        singbox|sing-box) tail -f "$RUN_DIR/singbox.log" ;;
        *) echo "Использование: $0 log [xray|singbox]" >&2; exit 1 ;;
    esac
}

case "${1:-}" in
    gen) gen "${2:-}" ;;
    start) start ;;
    stop) stop ;;
    restart)
        stop
        if [ -n "${2:-}" ]; then
            gen "$2"
        fi
        start
        ;;
    status) status ;;
    log) log "${2:-}" ;;
    *)
        echo "Использование: $0 {gen <vless://...>|start|stop|restart [vless://...]|status|log [xray|singbox]}" >&2
        exit 1
        ;;
esac
