FROM python:3.12-slim

WORKDIR /app

# Same layer-caching principle as the frontend: requirements.txt changes
# rarely, app code changes often -- so install deps in their own layer
# BEFORE copying the rest of the source.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

EXPOSE 8000

# Run as a non-root user inside the container -- ties back to the OS
# section on users/permissions: even though container processes are
# namespace-isolated, running as root inside a container is still bad
# practice (defense in depth against container-escape vulnerabilities).
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
