# Running with Docker

Quickstart
1. Build: `docker build -t orrin:local .`
2. Compose: `docker-compose up --build`
3. Volumes: mount persistent volumes for WAL and memory indexes.

Debugging
- Use `docker logs -f` and attach debuggers to exposed ports.
