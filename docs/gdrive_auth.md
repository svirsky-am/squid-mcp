# Настройка авторизации Google Drive и получение `gdrive_token.json`

Для выгрузки Excel-отчётов в папку обычного личного аккаунта Google (`@gmail.com`) используется пользовательский OAuth 2.0 токен (`authorized_user`), так как у сервисных аккаунтов Google отсутствует собственная квота хранилища (`403 storageQuotaExceeded`).

---

## Шаг 1. Настройка проекта в Google Cloud Console

1. Откройте [Google Cloud Console](https://google.com) и выберите ваш проект.
2. Включите API:
   * Перейдите в **APIs & Services → Library**.
   * Найдите **Google Drive API** и нажмите **Enable**.

---

## Шаг 2. Настройка экрана согласия (OAuth Consent Screen)

1. Откройте **APIs & Services → OAuth consent screen** (или **Google Auth Platform → Audience**).
2. Выберите тип аудитории **External**, укажите название приложения (например, `wb-alice-tool`) и контактный email.
3. Оставьте статус приложения **Testing** (публикация не требуется).
4. В разделе **Test users** нажмите **+ Add users**, добавьте ваш email (например, `svirsky.a.m@gmail.com`) и сохраните.  
   *(Без добавления в Test users вход будет заблокирован с ошибкой `403: access_denied`.)*

---

## Шаг 3. Создание `oauth_client.json`

1. Перейдите в **APIs & Services → Credentials** (или **Google Auth Platform → Clients**).
2. Нажмите **+ Create Credentials → OAuth client ID**.
3. Выберите тип приложения:
   * **Рекомендуемый вариант:** **`Desktop app`** (Приложение для ПК).
   * **Если выбран `Web application`:** в разделе **Authorized redirect URIs** добавьте `http://localhost:8080/`.
4. Нажмите **Create**, скачайте JSON-файл и сохраните его локально в проект как `.staff/oauth_client.json`.

---

## Шаг 4. Конвертация `oauth_client.json` в `gdrive_token.json`

На компьютере с браузером запустите утилиту из папки `tools/`:

```bash
uv run --package wb-mcp-client python tools/generate_gdrive_token.py \
  --client-secrets .staff/oauth_client.json \
  --output .staff/gdrive_token.json \
  --port 8080
```

1. В открывшемся окне браузера выберите ваш Google-аккаунт.
2. На экране предупреждения о непроверенном приложении нажмите **Advanced (Дополнительные настройки) → Go to wb-alice-tool (unsafe)** и разрешите доступ к Google Диску (`drive.file`).
3. Скрипт сохранит итоговый файл `.staff/gdrive_token.json`, содержащий `refresh_token` и поле `"type": "authorized_user"`.
4. При деплое на сервер скопируйте готовый `.staff/gdrive_token.json` в директорию `.staff/` на VPS. Дальнейшее обновление `access_token` происходит автоматически.

---

## Шаг 5. Проверка выгрузки

Убедитесь, что в `.staff/env` указаны переменные:

```env
ENABLE_GDRIVE_UPLOAD=true
GOOGLE_CREDENTIALS_PATH=".staff/gdrive_token.json"
GOOGLE_DRIVE_FOLDER_ID="1V6W_-OqoYov5PkC78mwV6MxGU0EkjldH"
```

Запустите проверку сборки отчёта и выгрузки:

```bash
set -a && source .staff/env && set +a
uv run --package wb-mcp-client wb-report
```

