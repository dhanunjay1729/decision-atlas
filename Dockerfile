FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY frontend ./frontend
RUN npm run build && npm prune --omit=dev

FROM python:3.13-slim-bookworm
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements*.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-cloud.txt
COPY --from=frontend /app/node_modules ./node_modules
COPY --from=frontend /app/dist ./dist
COPY package.json ./
COPY backend ./backend
RUN mkdir -p /app/work
ENV LEDGER_PATH=/app/work/usage.sqlite3 MODEL_PROVIDER=vercel TOTAL_MODEL_BUDGET_USD=2
EXPOSE 8000
CMD ["python","-m","uvicorn","app.main:app","--app-dir","backend","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
