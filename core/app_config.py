"""Configuración mínima para la versión WEB.

Los módulos de cálculo (cotizacion_logic, mayorista_logic, tabla_precios) son
IDÉNTICOS a los del escritorio y solo dependen de `log` de aquí. La versión de
escritorio tenía además rutas en %APPDATA%, caché y config de tema; en web nada
de eso aplica (el estado vive en el servidor / navegador), así que este archivo
es una versión reducida que solo expone el logger.
"""
import logging

APP_NOMBRE = "Calculadora Napo"
APP_VERSION = "2.0.1-web"

log = logging.getLogger("calculadora_napo")
