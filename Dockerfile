FROM python:3.12-slim

WORKDIR /app

# Requirements before source: Docker caches layers in order, so editing a .py
# file rebuilds from here down instead of reinstalling every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# This service will clone arbitrary repos off the internet on Day 3.
# Root is a poor default anywhere; here it's a genuinely bad idea.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "codecompass.main:app", "--host", "0.0.0.0", "--port", "8000"]