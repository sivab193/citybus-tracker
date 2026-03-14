FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default: run the API server
CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8080"]
