FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
# The console serves the UI, manages the neuro-san runtime, and proxies chat.
CMD ["uvicorn", "console.app:app", "--host", "0.0.0.0", "--port", "8080"]
