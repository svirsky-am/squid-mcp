uv run --package wb-mcp-client python -c '
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    ".staff/oauth_client.json",
    scopes=["https://googleapis.com" + "drive.file"],
)
creds = flow.run_local_server(port=8080)
Path(".staff/gdrive_token.json").write_text(creds.to_json(), encoding="utf-8")
print("Готово! Токен сохранён в .staff/gdrive_token.json")
'