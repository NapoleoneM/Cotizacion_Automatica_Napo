# Calculadora Napo — Versión Web

Versión web de la calculadora, pensada para usarse desde el navegador (PC o
celular) sin instalar nada. **Reutiliza exactamente la misma lógica de cálculo
de la versión de escritorio**, así que los resultados son idénticos.

---

## Recomendación de infraestructura

**VPS Hostinger (KVM2) + Docker + FastAPI**, en un subdominio de
`napoleonejoyas.tech` (ej. `calculadora.napoleonejoyas.tech`).

**Por qué el VPS y no cPanel:**
- La lógica de cálculo ya está escrita y probada en **Python**. En el VPS se
  reutiliza tal cual → **cero reescritura, resultados idénticos** al escritorio.
- cPanel está orientado a **PHP/WordPress**; usar Python allí es limitado y
  obligaría a reescribir toda la matemática en PHP (riesgo de discrepancias en
  montos, justo lo que se ha cuidado con test de regresión).
- Docker aísla este proyecto de los demás del VPS.

**Seguridad (mejora sobre el escritorio):** el `credenciales.json` vive **solo en
el servidor**; el navegador nunca lo ve. El servidor habla con Google Sheets y
devuelve únicamente resultados.

---

## Arquitectura

```
Navegador  ──HTTP──►  FastAPI (app.py)  ──►  core/  (lógica compartida)
(HTML/CSS/JS)                             │        cotizacion_logic.py
                                          │        mayorista_logic.py
                                          └──►  Google Sheets (espejo, solo lectura)
```

- **Backend** `app.py`: expone JSON (`/api/retail`, `/api/mayorista`,
  `/api/actualizar-precios`, `/api/tabla`) y sirve el frontend estático.
- **core/**: copia EXACTA de los módulos de cálculo del escritorio.
- **static/**: interfaz web (Retail, Mayorista, Tabla de precios, tema claro/oscuro,
  auto-cálculo, copiar para WhatsApp, limpieza del nombre pegado).
- Los precios de Sheets se cachean en memoria del servidor y se refrescan con el
  botón "Actualizar precios".

---

## Desarrollo local

```bash
cd Version_Web
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```
Abrir http://localhost:8000  (las credenciales se toman de `../credentials/` o de
`./credentials/`, o de la variable de entorno `GOOGLE_CREDS`).

---

## Despliegue en el VPS con Docker

El VPS ya corre **Traefik** (proyecto `n8n`, red `n8n_default`) como proxy
inverso para los demás sitios de Napoleone Joyas. Este proyecto se conecta a
esa misma red por labels — sin publicar puertos al host, igual que
`napoleone-pulseras` y los demás.

1. Clonar el repo en el VPS (ej. `/root/calculadora-napo-web/`).
2. Colocar `credenciales.json` en `./credentials/` (esa carpeta NO se sube a
   git ni se hornea en la imagen; se monta como volumen de solo lectura).
3. Construir y levantar:
   ```bash
   docker compose up -d --build
   ```
4. El DNS (`calculadora.napoleonejoyas.tech` → IP del VPS, registro A) y el
   certificado HTTPS los resuelve Traefik automáticamente (labels
   `traefik.enable`, `Host(...)`, `tls.certresolver=mytlschallenge` en
   `docker-compose.yml`).

---

## Mantener sincronizado con el escritorio

Los archivos en `core/` (`cotizacion_logic.py`, `mayorista_logic.py`,
`tabla_precios.py`) son **copias** de `../Version_desktop/core/`. Si algún día se
ajusta una condición de cálculo, hay que copiar el archivo aquí también para que
ambas versiones sigan dando lo mismo. (El `app_config.py` de aquí es una versión
reducida: solo expone el logger, sin rutas de escritorio.)

---

*Napoleone Joyas — herramienta de uso interno*
