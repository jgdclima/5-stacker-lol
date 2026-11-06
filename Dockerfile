FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into image (fallback if volumes aren't mounted)
COPY bot.py data_manager.py rating_engine.py riot_api.py schedule_checker.py github_tickets.py ./

# Create data directory mount point
RUN mkdir -p /app/data

CMD ["python", "bot.py"]

