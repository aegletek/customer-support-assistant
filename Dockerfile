# syntax=docker/dockerfile:1.7

ARG AVANTIQ_CORE_IMAGE=avantiq-core:demo-443123d
FROM ${AVANTIQ_CORE_IMAGE} AS runtime

USER root
WORKDIR /app

COPY pyproject.toml README.md ./
COPY customer_support_assistant ./customer_support_assistant

RUN pip install --no-cache-dir . \
    && chown -R avantiq:avantiq /app

USER avantiq

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"

CMD ["uvicorn", "customer_support_assistant.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
