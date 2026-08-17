FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY game.py .
COPY statuses.yaml .
COPY events/ events/
COPY quests/ quests/
COPY characters/ characters/

CMD ["python", "-u", "game.py"]