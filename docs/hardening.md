# Защита сервера (Hardening): ограничение доступа к порту 443 через UFW

Документ описывает настройку фаервола **UFW** на VPS так, чтобы порт `443` был доступен только для подсетей Яндекса (`AS13238` и `AS200350`), с автоматическим обновлением через `cron`.

---

## 1. Интеграция Docker и UFW

По умолчанию Docker обходит правила `ufw`. Чтобы применить ограничения к опубликованным портам (включая порт `443`), добавьте блок правил `DOCKER-USER` в конец файла `/etc/ufw/after.rules` и перезапустите службу:

```bash
sudo systemctl restart ufw
```
*(Полный текст правил фильтрации для `after.rules` можно найти в репозитории проекта).*

---

## 2. Базовая настройка UFW

Перед включением фаервола разрешите SSH, чтобы не потерять доступ к серверу:

```bash
sudo apt update && sudo apt install -y ufw whois
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw --force enable
```

---

## 3. Размещение скрипта в `/opt/squid-mcp`

Скопируйте скрипт из репозитория (`tools/update_yandex_ufw.sh`) в рабочую директорию VPS и запустите для первичной настройки правил:

```bash
sudo mkdir -p /opt/squid-mcp
sudo cp tools/update_yandex_ufw.sh /opt/squid-mcp/update_yandex_ufw.sh
sudo chmod +x /opt/squid-mcp/update_yandex_ufw.sh
sudo /opt/squid-mcp/update_yandex_ufw.sh
sudo ufw status numbered
```

---

## 4. Автоматическое обновление через `cron`

Для регулярного обновления подсетей Яндекса (например, каждое воскресенье в `04:00`) добавьте задачу в `crontab` (`sudo crontab -e`):

```cron
0 4 * * 0 /opt/squid-mcp/update_yandex_ufw.sh >> /var/log/yandex-ufw.log 2>&1
```

---

## 5. Проверка доступности и диагностика

* **Тест с локального устройства**: для проверки `curl`-запросом временно отключите UFW (`sudo ufw disable`), выполните запрос к `/mcp` с Bearer-токеном и снова включите фаервол (`sudo ufw enable`).
* **Логирование**: при возникновении таймаутов проверьте заблокированные пакеты командой:
  ```bash
  sudo dmesg | grep -E "UFW.*BLOCK" | grep "DPT=443" | tail -n 10
  ```

