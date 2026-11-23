# ---- build stage: install deps into a venv ----
FROM python:3.12-slim AS build
WORKDIR /app
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

# ---- runtime stage: slim, non-root ----
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home appuser
WORKDIR /app
COPY --from=build /venv /venv
COPY main.py .
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
