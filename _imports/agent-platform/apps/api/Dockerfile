# 后端镜像：python:3.12-slim，非 root 运行
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 数据目录（SQLite 持久化挂载点）
RUN mkdir -p /app/data && chown -R nobody:nogroup /app
USER nobody

EXPOSE 8000
# 默认零配置本地模式；LLM Key 等通过环境变量注入（见 .env.example）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
