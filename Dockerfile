FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install uv

RUN uv pip install --system .

COPY . .

CMD ["python", "app/main.py"]