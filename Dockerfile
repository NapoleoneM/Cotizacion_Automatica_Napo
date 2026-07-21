FROM python:3.12-slim

WORKDIR /app

# Dependencias primero (mejor cacheo de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código de la app (las credenciales NO se copian: se montan como volumen)
COPY app.py .
COPY core/ ./core/
COPY static/ ./static/

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
