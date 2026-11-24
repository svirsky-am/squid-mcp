
# Examples
```
uv init --lib packages/shared-lib
uv init --app packages/api-service

```
## example add uv package 


```sh 

uv add --package wb-mcp-client --dev pytest
uv add --package wb-mcp-client httpx
uv add --package wb-mcp-client --dev pytest anyio pytest-asyncio pytest-tornasync pytest-trio pytest-twisted
uv add --package wb-mcp-server google-api-python-client google-auth
uv add --package wb-mcp-server --dev pytest pytest-asyncio httpx2
```

# 1. Создайте пакет MCP-сервера в workspace
```sh
/etc/systemd/system/wb-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now wb-mcp
```



# Подключение диска

Как настроить доступ со стороны Google: в Google Cloud Console включите Google Drive API, создайте Service Account, скачайте его JSON-ключ на сервер и расшарьте нужную папку на Google Диске на email этого сервисного аккаунта с правами «Редактор»

Чтобы настроить Service Account для работы с Google Drive API, выполните следующие шаги в Google Cloud Console:
1. Создайте проект и включите API
	• Откройте Google Cloud Console и выберите или создайте проект.
	• Перейдите в APIs & Services → Library, найдите Google Drive API и нажмите Enable. [1] (https://support.google.com/workspacemigrate/answer/10839762?hl=ru), [2] (https://docs.cloud.google.com/iam/docs/keys-create-delete), [3] (https://docs.ispring.ru/pages/viewpage.action?pageId=119866165)
2. Создайте сервисный аккаунт
	• Перейдите в IAM & Admin → Service Accounts (или APIs & Services → Credentials → Create Credentials → Service account).
	• Нажмите Create Service Account, укажите имя (Service account name) и ID, при необходимости задайте роли и нажмите Done. [1] (https://developers.google.com/workspace/guides/create-credentials), [2] (https://knowledge.workspace.google.com/admin/users/create-a-service-account?hl=ru), [3] (https://osipenkov.ru/create-service-account/), [4] (https://docs.ispring.ru/pages/viewpage.action?pageId=119866165), [5] (https://support.google.com/workspacemigrate/answer/10839762?hl=ru)
3. Скачайте JSON-ключ
	• Нажмите на email созданного сервисного аккаунта и откройте вкладку Keys.
	• Выберите Add key → Create new key, укажите тип JSON и нажмите Create — файл ключа скачается на компьютер. [1] (https://osipenkov.ru/create-service-account/), [2] (https://docs.cloud.google.com/iam/docs/keys-create-delete)
4. Выдайте доступ к нужным папкам или файлам на Google Диске
	• Скопируйте email сервисного аккаунта (вида имя@://gserviceaccount.com).
	• В Google Диске откройте «Поделиться» для нужной папки или файла и добавьте этот email с правами Редактор или Читатель (иначе аккаунт увидит только файлы, созданные им самим). Для ресурсов Google Workspace может также потребоваться настройка делегирования полномочий в масштабе домена (Domain-wide delegation). [1] (https://developers.google.com/workspace/guides/create-credentials)
Уточните, пожалуйста:
• На каком языке или платформе вы пишете интеграцию (например, Python, Node.js, Apps Script)?
• Нужно ли работать с личным Google Диском или с общими дисками / доменом Google Workspace?
Это поможет дать готовый пример кода и подсказать нужные настройки прав.
