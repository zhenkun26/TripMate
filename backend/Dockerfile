FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先拷贝依赖清单，充分利用镜像层缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8000

# 配置全部经环境变量注入（见 docker-compose.yml / .env）
CMD ["uv", "run", "--no-sync", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
