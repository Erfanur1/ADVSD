FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /tmp/b.txt
RUN pip install --no-cache-dir -r /tmp/b.txt
COPY . .
CMD ["python", "backend/app.py"]
