FROM python:3.12-slim

WORKDIR /app

# Dependencias primero (mejor cacheo de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código de la app (las credenciales NO se copian: se montan como volumen)
COPY app.py .
COPY core/ ./core/
COPY static/ ./static/

# Usuario sin privilegios: si algún día una dependencia resulta vulnerable,
# el proceso no corre como root dentro del contenedor.
# El credenciales.json montado debe ser legible por uid 1000:
#   chown 1000:1000 credentials/credenciales.json   (en el servidor)
RUN useradd --uid 1000 --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
