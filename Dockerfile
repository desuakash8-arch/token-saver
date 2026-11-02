FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TIKTOKEN_CACHE_DIR=/app/tokenizer-cache TOKEN_SAVER_DB=/app/data/token_saver.sqlite3
COPY pyproject.toml README.md ./
COPY token_saver ./token_saver
RUN pip install --no-cache-dir . && python -m token_saver warmup && useradd --create-home healer && mkdir -p /app/data && chown -R healer:healer /app
USER healer
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
CMD ["python", "-m", "token_saver", "serve", "--host", "0.0.0.0"]
