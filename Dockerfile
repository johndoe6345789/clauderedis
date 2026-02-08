FROM python:3.11-slim

WORKDIR /app

COPY claude_cache_server.py /app/

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    redis \
    httpx

EXPOSE 8000

CMD ["uvicorn", "claude_cache_server:app", "--host", "0.0.0.0", "--port", "8000"]
