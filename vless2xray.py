#!/usr/bin/env python3
"""
vless2xray.py - конвертирует vless:// ссылку в config.json для xray-core

Использование:
    python3 vless2xray.py "vless://uuid@host:port?...#remark" -o config.json
    python3 vless2xray.py -f links.txt -o config.json   # первая строка файла
    echo "vless://..." | python3 vless2xray.py -o config.json

Опции:
    --socks-port  порт для socks5 inbound (по умолчанию 1080)
    --http-port   порт для http inbound (по умолчанию 2080)
    --no-http     не добавлять http inbound
"""

import sys
import json
import argparse
from urllib.parse import urlparse, parse_qs, unquote


def parse_vless(url: str):
    if not url.startswith("vless://"):
        raise ValueError("Ссылка должна начинаться с vless://")

    parsed = urlparse(url)
    uuid = parsed.username
    host = parsed.hostname
    port = parsed.port
    if not uuid or not host or not port:
        raise ValueError("Не удалось разобрать uuid/host/port из ссылки")

    params = parse_qs(parsed.query)
    remark = unquote(parsed.fragment) if parsed.fragment else "proxy"

    def get(key, default=None):
        return params.get(key, [default])[0]

    network = get("type", "tcp")
    security = get("security", "none")
    flow = get("flow", "")
    encryption = get("encryption", "none")

    user = {
        "id": uuid,
        "encryption": encryption,
        "level": 0,
    }
    if flow:
        user["flow"] = flow

    outbound = {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [user],
                }
            ]
        },
        "streamSettings": {
            "network": network,
        },
    }
    stream = outbound["streamSettings"]

    # --- security ---
    if security == "tls":
        tls = {
            "serverName": get("sni", host),
            "allowInsecure": False,
        }
        alpn = get("alpn")
        if alpn:
            tls["alpn"] = alpn.split(",")
        fp = get("fp")
        if fp:
            tls["fingerprint"] = fp
        stream["security"] = "tls"
        stream["tlsSettings"] = tls

    elif security == "reality":
        reality = {
            "serverName": get("sni", host),
            "fingerprint": get("fp", "chrome"),
            "publicKey": get("pbk", ""),
            "shortId": get("sid", ""),
        }
        spx = get("spx")
        if spx:
            reality["spiderX"] = spx
        stream["security"] = "reality"
        stream["realitySettings"] = reality

    # --- transport ---
    if network == "ws":
        ws = {"path": get("path", "/")}
        ws_host = get("host")
        if ws_host:
            ws["headers"] = {"Host": ws_host}
        stream["wsSettings"] = ws

    elif network == "grpc":
        stream["grpcSettings"] = {
            "serviceName": get("serviceName", get("path", "")),
            "multiMode": get("mode", "gun") == "multi",
        }

    elif network == "tcp":
        if get("headerType") == "http":
            stream["tcpSettings"] = {
                "header": {
                    "type": "http",
                    "request": {
                        "path": [get("path", "/")],
                        "headers": {"Host": [get("host", host)]},
                    },
                }
            }

    elif network in ("h2", "http"):
        h2 = {"path": get("path", "/")}
        h2_host = get("host")
        if h2_host:
            h2["host"] = [h2_host]
        stream["httpSettings"] = h2

    elif network == "httpupgrade":
        hu = {"path": get("path", "/")}
        hu_host = get("host")
        if hu_host:
            hu["host"] = hu_host
        stream["httpupgradeSettings"] = hu

    elif network in ("xhttp", "splithttp"):
        xh = {"path": get("path", "/")}
        xh_host = get("host")
        if xh_host:
            xh["host"] = xh_host
        stream["xhttpSettings"] = xh

    return outbound, remark


def build_config(outbound, remark, socks_port, http_port, add_http, tun=False,
                 tun_name="xray0", tun_mtu=1492, add_proxy_inbounds=True):
    inbounds = []

    if add_proxy_inbounds:
        inbounds.append(
            {
                "tag": "socks-in",
                "port": socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                },
            }
        )
        if add_http:
            inbounds.append(
                {
                    "tag": "http-in",
                    "port": http_port,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                    "settings": {},
                }
            )

    if tun:
        inbounds.append(
            {
                "tag": "tun-in",
                "port": 0,
                "protocol": "tun",
                "settings": {
                    "name": tun_name,
                    "MTU": tun_mtu,
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                },
            }
        )

    in_tags = []
    if add_proxy_inbounds:
        in_tags.append("socks-in")
        if add_http:
            in_tags.append("http-in")
    if tun:
        in_tags.append("tun-in")

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "block", "protocol": "blackhole", "settings": {}},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": in_tags,
                    "outboundTag": "proxy",
                }
            ],
        },
    }
    return config


def main():
    ap = argparse.ArgumentParser(description="Конвертер vless:// в xray config.json")
    ap.add_argument("link", nargs="?", help="vless:// ссылка")
    ap.add_argument("-f", "--file", help="файл с ссылкой (берётся первая непустая строка)")
    ap.add_argument("-o", "--output", default="config.json", help="путь к итоговому config.json")
    ap.add_argument("--socks-port", type=int, default=1080, help="порт socks5 inbound")
    ap.add_argument("--http-port", type=int, default=2080, help="порт http inbound")
    ap.add_argument("--no-http", action="store_true", help="не добавлять http inbound")
    ap.add_argument("--tun", action="store_true", help="добавить tun inbound (имя по умолчанию xray0)")
    ap.add_argument("--tun-name", default="xray0", help="имя tun-интерфейса (по умолчанию xray0)")
    ap.add_argument("--tun-mtu", type=int, default=1492, help="MTU tun-интерфейса")
    ap.add_argument("--tun-only", action="store_true", help="не добавлять socks/http inbound, только tun")
    args = ap.parse_args()

    if args.link:
        link = args.link.strip()
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            link = next((line.strip() for line in f if line.strip()), "")
    elif not sys.stdin.isatty():
        link = sys.stdin.readline().strip()
    else:
        ap.error("Нужно передать ссылку аргументом, файлом (-f) или через stdin")
        return

    outbound, remark = parse_vless(link)
    config = build_config(
        outbound,
        remark,
        socks_port=args.socks_port,
        http_port=args.http_port,
        add_http=not args.no_http,
        tun=args.tun,
        tun_name=args.tun_name,
        tun_mtu=args.tun_mtu,
        add_proxy_inbounds=not args.tun_only,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"Готово: {args.output}")
    print(f"Профиль: {remark}")
    if not args.tun_only:
        print(f"Socks5 порт: {args.socks_port}")
        if not args.no_http:
            print(f"HTTP порт: {args.http_port}")
    if args.tun:
        print(f"TUN интерфейс: {args.tun_name} (MTU {args.tun_mtu})")
        print("Не забудь запустить xray-tun.sh up после старта xray для настройки маршрутизации")


if __name__ == "__main__":
    main()
