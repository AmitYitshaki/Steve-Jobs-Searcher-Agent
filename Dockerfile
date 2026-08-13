FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN pip install --no-cache-dir -e .

# The Playwright base image already ships a non-root user `pwuser` at UID/GID
# 1000. That matches the default AWS EC2 host user, so bind-mounted volumes
# (./data, ./logs) stay writable without any host-side chown gymnastics.
# Reuse it instead of creating a second user that would collide on UID 1000.
RUN chown -R pwuser:pwuser /app

USER pwuser

CMD ["python", "-m", "scheduler"]
