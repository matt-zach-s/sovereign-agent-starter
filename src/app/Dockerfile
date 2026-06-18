FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target=/opt/deps --ignore-installed -r requirements.txt

COPY . .

ENV PORT=8080
ENV PYTHONPATH=/opt/deps
EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
