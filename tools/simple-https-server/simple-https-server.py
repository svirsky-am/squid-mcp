import http.server
import ssl

# Настройки сервера
HOST = "136.234.88.117"
PORT = 443

# Настройка SSL-контекста
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

# Создание и запуск сервера (раздает файлы из текущей директории)
server_address = (HOST, PORT)
httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"HTTPS сервер запущен на https://{HOST}:{PORT}")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nСервер остановлен.")
    httpd.server_close()
