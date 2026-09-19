FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY config ./config
RUN pip install --no-cache-dir .
RUN mkdir -p /data
EXPOSE 4010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4010"]
