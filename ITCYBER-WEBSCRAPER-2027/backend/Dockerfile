FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ITCYBER_DATA_DIR=/data/dashboard_data \
    ITCYBER_OUTPUT_DIR=/data/output \
    ITCYBER_BROWSER_PROFILE_DIR=/data/browser_profile \
    ITCYBER_HEADLESS=false

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN mkdir -p /data/dashboard_data /data/output /data/browser_profile

EXPOSE 8080

# IMPORTANT: sh -c is intentional. Railway injects PORT at runtime and shell
# expansion is required for Dockerfile/image start commands.
CMD ["sh", "-c", "xvfb-run -a python -u dashboard_server.py --host 0.0.0.0 --port ${PORT:-8080} --no-open"]
