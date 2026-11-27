#!/usr/bin/env bash
set -euo pipefail

# Базовый гарантированный список IPv4-подсетей Yandex Cloud и Яндекса
BASE_CIDRS=(
  # Yandex Cloud (AS200350)
  "51.250.0.0/16"
  "84.201.128.0/17"
  "130.193.32.0/19"
  "158.160.0.0/16"
  "178.154.192.0/18"
  "217.28.224.0/20"
  # Яндекс (AS13238)
  "5.45.192.0/18"
  "5.255.192.0/18"
  "37.9.64.0/18"
  "37.140.128.0/18"
  "77.88.0.0/18"
  "87.250.224.0/19"
  "93.158.128.0/18"
  "95.108.128.0/17"
  "141.8.128.0/18"
  "178.154.128.0/18"
  "185.32.187.0/24"
  "213.180.192.0/19"
)

# Дополняем базовый список актуальными маршрутами через whois (если whois доступен)
WHOIS_CIDRS=""
if command -v whois >/dev/null 2>&1; then
  WHOIS_CIDRS=$(
    {
      whois -h whois.ripe.net -- '-i origin AS200350' 2>/dev/null || true
      whois -h whois.ripe.net -- '-i origin AS13238' 2>/dev/null || true
    } | awk '/^route:/ {print $2}'
  )
fi

ALL_CIDRS=$(
  {
    printf "%s\n" "${BASE_CIDRS[@]}"
    printf "%s\n" "$WHOIS_CIDRS"
  } | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' | sort -u
)

echo "Применяем $(echo "$ALL_CIDRS" | wc -l) IPv4-подсетей Яндекса для порта 443..."

for cidr in $ALL_CIDRS; do
  ufw allow from "$cidr" to any port 443 proto tcp comment "Yandex MCP" >/dev/null
  ufw route allow proto tcp from "$cidr" to any port 443 comment "Yandex MCP Docker" >/dev/null
done

ufw reload
echo "Правила UFW успешно обновлены."

