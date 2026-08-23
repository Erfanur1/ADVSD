# Multi-purpose image for Student 1's backend and frontend.
# Build target chosen via BACKEND/FRONTEND command in docker-compose.
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /tmp/backend.txt
COPY frontend/requirements.txt /tmp/frontend.txt
RUN pip install --no-cache-dir -r /tmp/backend.txt -r /tmp/frontend.txt
COPY . .
# default: backend
CMD ["sh", "-c", "python backend/init_db.py && python backend/app.py"]
