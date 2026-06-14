#!/usr/bin/env python3
"""
gen-singbox-tun.py - генерирует config.json для sing-box, который создаёт
tun-интерфейс, забирает весь системный трафик и пускает его через socks5
xray (см. vless2xray.py).

Архитектура:
    [система] -> tun (sing-box, auto_route) -> socks5 127.0.0.1:1080 -> xray -> VLESS-сервер

sing-box сам настраивает таблицы маршрутизации/iptables (auto_route,
auto_detect_interface), петли не будет: socks-сервер на 127.0.0.1 не
заворачивается в tun, а исходящее соединение делает сам xray через обычный
шлюз.

Использование:
    python3 gen-singbox-tun.py -o singbox-tun.json
    python3 gen-singbox-tun.py --socks-port 1080 --dns 1.1.1.1 -o singbox-tun.json

Запуск (нужен root, т.к. создаётся сетевой интерфейс):
    sudo sing-box run -c singbox-tun.json
"""

import json
import argparse


def build_config(socks_port, interface, mtu, dns_server, ipv6):
    address = ["172.19.0.1/30"]
    if ipv6:
        address.append("fdfe:dcba:9876::1/126")

    dns_servers = [
        {
            "type": "tls",
            "tag": "proxy-dns",
            "server": dns_server,
            "detour": "proxy",
        },
        {
            "type": "local",
            "tag": "local-dns",
        },
    ]

    config = {
        "log": {"level": "warn"},
        "dns": {
            "servers": dns_servers,
            "final": "proxy-dns",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": interface,
                "address": address,
                "mtu": mtu,
                "auto_route": True,
                "strict_route": True,
                "stack": "system",
                "sniff": True,
            }
        ],
        "outbounds": [
            {
                "type": "socks",
                "tag": "proxy",
                "server": "127.0.0.1",
                "server_port": socks_port,
                "version": "5",
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "auto_detect_interface": True,
            "rules": [
                {"protocol": "dns", "action": "hijack-dns"},
            ],
            "final": "proxy",
        },
    }
    return config


def main():
    ap = argparse.ArgumentParser(description="Генератор tun-конфига sing-box для xray socks5")
    ap.add_argument("-o", "--output", default="singbox-tun.json", help="путь к итоговому config.json")
    ap.add_argument("--socks-port", type=int, default=1080, help="порт socks5 xray (см. vless2xray.py)")
    ap.add_argument("--interface", default="tun0", help="имя tun-интерфейса")
    ap.add_argument("--mtu", type=int, default=1500, help="MTU tun-интерфейса")
    ap.add_argument("--dns", default="1.1.1.1", help="DNS-сервер, который будет резолвить через proxy (DoT)")
    ap.add_argument("--ipv6", action="store_true", help="включить IPv6 на tun-интерфейсе")
    args = ap.parse_args()

    config = build_config(args.socks_port, args.interface, args.mtu, args.dns, args.ipv6)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"Готово: {args.output}")
    print(f"TUN интерфейс: {args.interface} (MTU {args.mtu})")
    print(f"Socks5 backend: 127.0.0.1:{args.socks_port}")
    print()
    print("Запуск (нужны права root для создания интерфейса):")
    print(f"  sudo sing-box run -c {args.output}")


if __name__ == "__main__":
    main()
