FROM node:22-bookworm-slim AS ui
WORKDIR /ui
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000
WORKDIR /app
COPY requirements/web.txt requirements/web.txt
RUN pip install --no-cache-dir -r requirements/web.txt && useradd --create-home appuser
COPY backend/ backend/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY datasets/snapshot.json datasets/snapshot.json
COPY --from=ui /ui/dist frontend/dist
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
