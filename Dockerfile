FROM python:3.11-slim

# Avoid writing .pyc files inside the container.
# This keeps the container filesystem cleaner and reduces incidental bytecode artifacts.
ENV PYTHONDONTWRITEBYTECODE=1

# Flush stdout/stderr immediately so app logs and script output appear in real time.
# This is useful for Docker logs and for long-running fetch/ingest scripts.
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]