FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# 项目代码
COPY src/ src/
COPY api/ api/
COPY fetchers/ fetchers/
COPY config/ config/
COPY rss_fetcher.py run.py ./

EXPOSE 8000

CMD ["python", "run.py", "api"]
