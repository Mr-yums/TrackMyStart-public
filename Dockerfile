# [Sol] Même image testée puis déployée ; exécution sans root.
FROM node:22-alpine AS frontend
WORKDIR /src
COPY yumnews/static/js/ ./
RUN for f in *.js; do node --check "$f"; done
COPY tests/js/ /tests/
RUN CHECKOUT_JS_DIR=/src node --experimental-vm-modules --test /tests/*.test.cjs
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && pip check
RUN useradd --uid 10001 --create-home app
COPY --chown=app:app . .
COPY --from=frontend --chown=app:app /src/ ./yumnews/static/js/
USER app
EXPOSE 8800
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8800", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
