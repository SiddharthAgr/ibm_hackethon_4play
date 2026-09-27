# ── Stage 1: MCP server (Node.js / STDIO transport) ──────────────────────────
FROM node:20-alpine AS mcp-server

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --omit=dev

COPY mcp/ ./mcp/
COPY memory/ ./memory/
COPY demo/ ./demo/
COPY reports/ ./reports/

ENTRYPOINT ["node", "mcp/server.js"]

# ── Stage 2: Python tools / pytest ───────────────────────────────────────────
FROM python:3.11-slim AS python-tools

WORKDIR /app

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY python/ ./python/
COPY tests/ ./tests/
COPY evaluation/ ./evaluation/

CMD ["pytest"]
