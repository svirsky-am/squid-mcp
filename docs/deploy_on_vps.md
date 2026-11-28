```sh
apt update && apt install -y docker-compose-v2
docker compose up -d --build
docker compose logs -f

```



генерация MCP_BEARER_TOKEN
```sh
openssl rand -hex 32
```




```sh
curl -i -X POST "https://market-squid-mcp.ru:4443/mcp" \
  -H "Authorization: Bearer 04025a3849b2f47afcc94d1a26d37c63bac91e76be7585deaa694fc39679ac0sdf" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'


```