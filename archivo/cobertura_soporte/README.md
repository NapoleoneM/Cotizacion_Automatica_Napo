# Cobertura de soporte — archivo (retirada en agosto de 2026)

Esta carpeta guarda **la lógica de cobertura del panel de turnos tal como
funcionaba hasta el 27 de agosto de 2026**, por si más adelante vuelve a haber
personal de soporte en el chat center.

Nada de aquí se importa ni se ejecuta. Son copias de referencia.

## Por qué se retiró

El chat center dejó de tener rol de soporte: **todos pasaron a ser vendedores**,
y quedaron dos turnos de ventas más un tercer bloque para la auditoría de
calidad. Sin soporte no hay a quién pedirle que cubra a quién, así que el panel
pasó a ser **informativo**: muestra quién está en línea, quién avisó por qué no
está y a quién no se espera hoy. La presencia, los estados y las novedades se
siguen registrando igual.

## Qué se fue con eso

- La sección roja **"Requieren cobertura"** y su contador en la lengüeta.
- El botón **"Yo lo cubro"** / "liberar", y el registro de coberturas.
- Los **vencimientos**: 90 min de una cobertura en turno, 150 min (2.5 h) del
  ciclo de "pendientes de clientes", y la revisión diaria de vacaciones.
- La lógica de **"Pendientes de clientes"** (turno 2/3 antes de entrar, y
  cualquier turno después de salir).
- Los **15 min de tolerancia** al entrar (existían para amortiguar la alarma).
- El **pitido repetido cada minuto** y las **notificaciones nativas** del
  navegador.
- Las métricas de Gestión derivadas de todo eso: `minutos_sin_cobertura`,
  `episodios_sin_cobertura`, `veces_cubierto`, `minutos_cubierto`,
  `veces_cubriendo`, `veces_respondio`, `min_respuesta_prom`, y el bloque
  "Soporte — cobertura y tiempo de respuesta".
- Que el `*` al final de un nombre en la hoja marcara a alguien como Soporte
  (el asterisco se sigue quitando del nombre, pero ya no asigna rol).

## Qué NO se tocó

- Las **tablas `coberturas` y `alertas`** siguen creándose en
  `core/almacen.py` → `_init()`, con todo su histórico. Simplemente ya no se
  escriben.
- `/api/torre/historial` **sigue devolviendo** la tabla `coberturas`, porque la
  Torre de Control la espera. Para fechas nuevas llega vacía.
- Presencia, estados, novedades, ajustes del día, vacaciones, almuerzo
  automático, sello de fecha/hora, PIN de la jefa y el panel Equipo: todo
  intacto.

## Contenido de la carpeta

| Archivo | Qué guarda |
|---|---|
| `turnos_cobertura.py` | `calcular_cobertura()` completa, las constantes (`TOLERANCIA_MIN`, `VENCIMIENTO_*`, `_ROLES_NO_CUBRIR`), `_rol_cubrible()` y el fragmento del `*` → Soporte |
| `almacen_cobertura.py` | Las secciones COBERTURAS y ALERTAS de `core/almacen.py`, y los fragmentos que se quitaron de `resumen()` |
| `app_cobertura.py` | Los endpoints `/api/turnos/cubrir` y `/cubrir/cerrar`, el modelo `CoberturaReq` y el cableado de `/api/turnos/estado` |
| `frontend_cobertura.md` | Todo el HTML, JS y CSS retirado (`botonCubrir`, `esSoporteYo`, notificaciones, repique, veredictos de Gestión, estilos) |
| `test_almacen_alertas.py` | La prueba de trazabilidad de alertas y tiempos de respuesta (su reemplazo actual es `tools/test_almacen.py`) |
| `TURNOS_con_cobertura.md` | Copia íntegra del `TURNOS.md` de antes del cambio — es la explicación completa del mecanismo, con todos sus casos |

## Si hay que reactivarlo

1. Leer primero **`TURNOS_con_cobertura.md`**: ahí está el porqué de cada
   decisión (por qué dos ciclos de vencimiento distintos, por qué "aún no
   entran" nunca alarma dentro de la tolerancia, etc.).
2. Devolver las piezas a su sitio siguiendo cada archivo de esta carpeta.
   `calcular_panel()` en `core/turnos.py` es la versión recortada de
   `calcular_cobertura()`: conviene reemplazarla y no intentar fusionarlas.
3. Volver a poner el rol en el flujo: hoy los roles se leen (hoja `Roles` y
   panel Equipo) y se muestran, pero **no deciden nada**. Hay que restituir
   `_rol_cubrible()` en los puntos marcados.
4. Recuperar `tools/test_almacen_alertas.py` y revisar
   `tools/test_turnos.py`: sus pruebas actuales afirman explícitamente que el
   panel **no** devuelve `requieren_cobertura` y que el `*` **no** asigna rol.
5. Ojo con lo que cambió alrededor y NO conviene revertir sin pensarlo:
   - `TURNOS[3]` pasó de `(14.0, 21.0)` a `(10.0, 18.0)`: el tercer bloque es
     ahora la auditoría de calidad, no un turno de ventas de tarde.
   - El parser aprendió a tolerar un rótulo de turno **sin número** y a
     ignorar un rango de horas con el fin antes del inicio. Eso es
     independiente de la cobertura: conviene conservarlo.
   - En `calcular_panel()` la señal de presencia se evalúa **antes** que la
     novedad reportada (en `calcular_cobertura()` era al revés, y la novedad
     solo pesaba si no había señal reciente).
