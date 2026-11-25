import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://googleapis.com" + "drive.file"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генерация OAuth-токена (authorized_user) для загрузки отчётов на Google Диск"
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=Path(".staff/oauth_client.json"),
        help="Путь к JSON-файлу OAuth Client ID из Google Cloud Console",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".staff/gdrive_token.json"),
        help="Путь для сохранения итогового JSON с refresh_token",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Локальный порт для OAuth redirect URI (по умолчанию 8080)",
    )
    args = parser.parse_args()

    if not args.client_secrets.exists():
        raise FileNotFoundError(f"Файл OAuth Client не найден: {args.client_secrets}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secrets),
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=args.port)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    token_data = json.loads(creds.to_json())
    token_data.setdefault("type", "authorized_user")
    args.output.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"Токен успешно сохранён в {args.output}")


if __name__ == "__main__":
    main()