# Настройка доступа к Google Диску и авторизации

Документ описывает настройку Google Cloud Console и получение OAuth-токена для автоматической и ручной загрузки Excel-отчётов на Google Диск.

> **Почему используется пользовательский OAuth-токен (`authorized_user`), а не Service Account?**  
> У сервисных аккаунтов Google нет собственной квоты хранилища (`0 ГБ`). При попытке загрузить файл в папку обычного личного аккаунта (`@gmail.com`) Google Drive API возвращает ошибку `403 storageQuotaExceeded`. Авторизация через OAuth 2.0 с сохранением `refresh_token` позволяет загружать файлы от имени владельца аккаунта в его основную квоту. (Сервисный аккаунт поддерживается кодом только для корпоративных **Общих дисков / Shared Drives** в Google Workspace.)

---

## 1. Настройка проекта в Google Cloud Console

1. Откройте [Google Cloud Console](https://google.com) и выберите ваш проект.
2. Включите Google Drive API:
   * Перейдите в **APIs & Services → Library**.
   * Найдите **Google Drive API** и нажмите **Enable**.

---

## 2. Настройка экрана согласия (OAuth Consent Screen)

1. Перейдите в **APIs & Services → OAuth consent screen** (или **Google Auth Platform → Audience**).
2. Выберите тип аудитории **External** и заполните обязательные поля (название приложения, например `wb-alice-tool`, и email разработчика).
3. Оставьте приложение в статусе **Testing** (публикация и верификация Google не требуются).
4. В блоке **Test users** нажмите **+ Add users**, укажите ваш `@gmail.com` и сохраните изменения. *(Без этого шага при входе возникнет ошибка `403: access_denied`.)*

---

## 3. Создание OAuth Client ID

1. Перейдите в **APIs & Services → Credentials** (или **Google Auth Platform → Clients**).
2. Нажмите **+ Create Credentials → OAuth client ID**.
3. Выберите тип приложения:
   * **Рекомендуемый вариант:** **`Desktop app`** (Приложение для ПК) — разрешает любой локальный порт для перенаправления.
   * **Если выбран `Web application`:** в разделе **Authorized redirect URIs** обязательно добавьте `http://localhost:8080/`.
4. Нажмите **Create**, скачайте JSON-файл и сохраните его в проект как `.staff/oauth_client.json`.

---

## 4. Получение `gdrive_token.json`

На компьютере с браузером запустите утилиту из папки `tools/`:

```bash
uv run --package wb-mcp-client python tools/generate_gdrive_token.py \
  --client-secrets .staff/oauth_client.json \
  --output .staff/gdrive_token.json \
  --port 8080
```

1. В открывшемся окне браузера войдите в ваш Google-аккаунт.
2. На экране предупреждения о непроверенном приложении нажмите **Advanced (Дополнительные настройки) → Go to wb-alice-tool (unsafe)** и разрешите доступ к файлам Google Диска (`drive.file`).
3. После подтверждения в `.staff/gdrive_token.json` сохранится JSON с `refresh_token`. При дальнейшей работе приложение будет продлевать `access_token` автоматически без участия пользователя.
4. При развёртывании на выделенном Linux-сервере без браузера просто скопируйте готовый файл `.staff/gdrive_token.json` на сервер.

---

## 5. Настройка переменных окружения

1. Откройте целевую папку на [Google Диске](https://google.com) и скопируйте её ID из адресной строки (`https://google.comdrive/folders/<FOLDER_ID>`).
2. Пропишите параметры в `.staff/env`:

```env
ENABLE_GDRIVE_UPLOAD=true
GOOGLE_CREDENTIALS_PATH=".staff/gdrive_token.json"
GOOGLE_DRIVE_FOLDER_ID="ВАШ_FOLDER_ID"
```

---

## 6. Проверка работы

```bash
set -a && source .staff/env && set +a

# Построение отчёта из БД и выгрузка на Google Диск
uv run --package wb-mcp-client wb-report

# Выгрузка последнего уже готового отчёта без пересборки
uv run --package wb-mcp-server wb-upload-gdrive
```

> **Безопасность:** убедитесь, что директория `.staff/` добавлена в `.gitignore`, чтобы ключи `oauth_client.json` и `gdrive_token.json` не попали в репозиторий.
