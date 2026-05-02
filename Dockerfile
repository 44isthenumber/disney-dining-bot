FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY . .

ENV DISNEY_BROWSER_PROFILE_DIR=/data/browser-profile
ENV DISNEY_HEADLESS=true

CMD ["bash", "run_bot.sh"]
