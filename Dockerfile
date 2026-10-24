# ---- web app ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- API + agents ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 ZS_WEB_DIR=/app/web
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/zerosecond ./zerosecond
COPY backend/data/model_params.json backend/data/calibration.json ./data/
COPY --from=web /web/dist /app/web
RUN useradd -m zs && chown -R zs /app
USER zs
EXPOSE 8000
CMD ["sh", "-c", "uvicorn zerosecond.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --timeout-graceful-shutdown 2"]
