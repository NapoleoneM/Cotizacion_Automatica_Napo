# Panel de turnos y cobertura

Panel lateral (fuera de la calculadora) para que el equipo de **soporte** vea
al instante **a qué vendedores de redes debe cubrir**, sin tener que revisar
manualmente quién entró a su turno.

No hay login: cada asesor elige su primer nombre una sola vez (queda en su
navegador). Es una herramienta de coordinación, no de control de acceso.

---

## Cómo funciona

1. **Presencia automática.** Como todos usan la calculadora para cotizar, al
   abrirla se envía una señal con el nombre elegido (y se repite cada 3 min
   mientras la pestaña esté abierta).
2. **El panel cruza tres cosas:** el horario semanal (Google Sheets), esa señal
   de presencia y la hora actual.
3. **Resultado para soporte:**
   - **Requieren cobertura** — su turno ya empezó (con 15 min de gracia) y no
     hay señal: *a estos hay que entrarles*.
   - **Novedades de hoy** — ausencias/permisos reportados, con hora y nota.
   - **En línea** — con actividad reciente.
   - **Aún no entran** — su turno todavía no comienza (no se alerta).
   - **Hoy no se espera** — compensatorio, ausencia o cambio de horario.

La lengüeta del borde derecho se pone **roja con un contador** cuando hay gente
por cubrir, así soporte lo nota sin abrir el panel.

Cualquiera puede reportar una novedad (propia o de un compañero), y quitarla.

---

## Cómo se reparten las responsabilidades

Hay dos horizontes de tiempo distintos y cada uno vive donde mejor funciona:

| | Dónde | Por qué |
|---|---|---|
| **Plan de la semana** | Google Sheets, hoja `Horarios` | Es trabajo de criterio y excepciones (compensatorios, Santafé, domingo reducido, Ceiba, notas puntuales). La jefa ya lo domina y el pantallazo para WhatsApp ya funciona. |
| **Ajustes de hoy** | La app | Un cambio a última hora tiene que ser **instantáneo y visible para soporte**. Editar la hoja a media jornada no le avisa a nadie. |

La regla: **el plan viene del Sheet; los ajustes de hoy pesan más que el plan.**

> Para los horarios **no hace falta Apps Script**: si el cuadro está en una hoja
> del documento espejo, la app lo lee en vivo (caché de 2 minutos). El script de
> los precios existe solo porque hay que copiarlos del CORE, que la app no ve.

## Ajustes de hoy

Movimientos que aplican **solo a la fecha** y **no tocan el plan de la semana**:

| Ajuste | Qué hace en el panel |
|---|---|
| **Cambia de turno** | La persona pasa a contar en el turno indicado hoy |
| **Entra más tarde** | Corre su hora de entrada: antes de esa hora no se alerta |
| **Hoy no viene** | Sale de las alertas y pasa a "hoy no se espera" |
| **Entra extra** | Aparece aunque no estuviera programada |

Cada ajuste guarda **quién lo hizo y el motivo**, y las personas afectadas
quedan marcadas con **✎** para que soporte entienda por qué el panel dice algo
distinto al cuadro de la semana. La ✕ deshace el ajuste.

Los ajustes los puede registrar cualquiera con sesión (igual que las novedades),
pero siempre queda constancia del autor. Si más adelante conviene restringirlo a
la jefa y a soporte, es un cambio pequeño.

## De dónde salen los nombres y los turnos

Hay **dos fuentes posibles**, y la app usa la primera que esté disponible:

1. **La hoja `Horarios` de Google Sheets** (la más rica: trae compensatorios,
   ausencias y cambios de horario por color). Ver la sección siguiente.
2. **El equipo registrado dentro de la app** — la jefa entra con su PIN y en el
   panel aparece **"Equipo del chat center"**: escribe el primer nombre, elige
   rol (Red social / Página web / Soporte / Jefa) y turno (1, 2 o 3). Clic en una
   persona para editarla; la ✕ la desactiva (no se borra: su historial sigue
   teniendo sentido).

Con la opción 2 el panel funciona **sin depender de Sheets**: cada persona
trabaja su turno de lunes a sábado. Es la forma más rápida de arrancar. El pie
del panel indica qué fuente está en uso.

## Aviso sonoro

Un contador rojo no sirve si nadie mira la pantalla, así que el panel **suena**
cuando aparece algo que exige acción:

- **Doble pitido** — una novedad *importante* (Ausencia, Incapacidad, Salida
  anticipada) o alguien nuevo que queda **sin cubrir**.
- **Un pitido** — el resto de novedades (Llegada tarde, Cita médica, Permiso…).

Además, si la pestaña está en segundo plano, **el título parpadea** con el
nombre de la persona. La campanita 🔔 de la cabecera silencia el sonido (queda
guardado por navegador, así cada quien decide). Al abrir el panel no suena: solo
avisa de lo que llega *después*.

El sonido se genera en el navegador (sin archivos externos). Si el navegador lo
bloquea por su política de autoplay, el aviso visual sigue funcionando.

## Sello de fecha y hora

Arriba del panel hay una franja con la **fecha y hora del servidor** dibujada
como **imagen** (`/api/reloj.png`), no como texto. Así, si un asesor toma un
pantallazo para reportar una novedad, la fecha no se puede alterar editando el
HTML con las herramientas del navegador.

> Nota honesta: en un navegador nada es 100 % infalsificable — quien se empeñe
> puede reemplazar una imagen. La prueba fuerte es el **registro en la base de
> datos**, que guarda la hora del servidor en el momento del reporte; el sello
> solo hace que el pantallazo sea creíble de un vistazo.

## Cambiar de PIN / salir

En la cabecera del panel hay un botón **salir**: cierra la sesión y vuelve a
pedir el PIN. Es necesario porque la sesión dura 7 días, así que sin él quien
entró como asesor no podría pasar al PIN de la jefa.

## La hoja de horarios (lo que mantiene la jefe de ventas)

El panel lee el **mismo cuadro semanal que ya se usa**, no hay que cambiar la
forma de trabajar. Solo debe vivir en Google Sheets y estar compartida en
**solo lectura** con el service account de la app.

Formato esperado:

- Una **fila de encabezado** con los días: `Lunes 27`, `Martes 28`, … `Domingo 2`
  (basta con que empiece por el nombre del día).
- Un **bloque por turno**, cuya primera celda contiene el rótulo:
  `1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm`
  Si el rótulo trae horas con `am/pm`, esas manda; si son ambiguas (`2:00 a 9:00`)
  se usan los horarios de respaldo definidos en `core/turnos.py` → `TURNOS`.
- Debajo de cada día, los **primeros nombres** de los asesores de ese turno.
- **Soporte se marca con un `*` al final del nombre** (ej. `Cristian*`): no se
  le pide cobertura a sí mismo, sin necesitar una hoja `Roles` aparte. El
  asterisco no se muestra en el panel, solo se usa para identificarlo.
- El título `Semana del ... al ...` **ya no hace falta escribirlo**: el panel
  calcula solo la semana en curso (corte el sábado a las 11pm).
- Una fila **`Leyenda:`** que marca dónde termina el cuadro — todo lo que va
  después (la leyenda, la tabla de almuerzo) se ignora al buscar turnos y
  nombres. Debajo de esa fila, el texto del estado y **el color a su
  derecha**: `Compensatorio`, `Ausencia`, `Cambio de Horario`, `CC Santafe`,
  `CC Tesoro` (o los nombres cortos `Santafe`/`Tesoro`, siguen funcionando).

Los **colores de las celdas** se leen igual que en la tabla de precios. Hay
tres formas de "no cubrir chats" y el panel las trata distinto:

| Estado | Significa | Dónde aparece |
|---|---|---|
| `Compensatorio`, `Ausencia`, `Cambio de Horario` | No trabaja ese día | "Hoy no se espera" (sin alarma, sin botón de cubrir) |
| `CC Santafe`, `CC Tesoro` | Está trabajando, pero **presencial** en esa sede — sus chats quedan sin atender todo el turno | "Ausencia informada" (morado, con "Yo lo cubro"), igual que el traslado a zona presencial que reporta el propio asesor |
| (celda blanca / sin color) | Normal | Cobertura normal por presencia |

### Hoja opcional `Roles`

Dos columnas: `Nombre | Rol`. Es un mecanismo aparte del `*` (se **suman** los
dos, no hace falta elegir uno) — útil si prefieres administrar los roles en un
solo lugar en vez de tocar cada celda del cuadro. No se pide cobertura de quien
tenga en su rol las palabras *soporte*, *jefe*, *coordin*, *web* o *página*.
Si ninguno de los dos mecanismos aplica, se asume que la persona es cubrible
(mejor avisar de más que dejar un chat solo).

### Tabla de almuerzo (opcional)

Debajo de la leyenda, una tabla `Almuerzo | Desde | Hasta` con una fila por
turno (`1 Turno`, `2 Turno`, `3 Turno`) y sus horas. Si no está, se usa el
respaldo por código (`core/turnos.py` → `ALMUERZOS`). Ver más abajo cómo se
aplica automáticamente.

---

## Estados del asesor

El asesor marca en el panel **"Estoy:"** — En chat, Almuerzo, Capacitación,
Reunión, Desconectado (se quitaron *Disponible*, que "En chat" ya cubre, y
*Baño*, por ser tiempos demasiado breves para justificar un aviso). Sirve para
separar dos cosas que antes se confundían:

- **Requieren cobertura (rojo):** en turno y **sin ninguna explicación**. Esto
  es lo que de verdad hay que atender.
- **Ausencia informada (amarillo):** en turno pero con un estado (almuerzo,
  capacitación…) o una novedad reportada. Soporte decide si cubre.

El contador rojo de la lengüeta cuenta **solo** los del primer grupo, para que
una alerta signifique siempre lo mismo.

### Almuerzo automático

Dentro de la ventana de almuerzo de su turno (ver la tabla de la hoja, o el
respaldo `ALMUERZOS` en el código), el asesor **queda marcado "Almuerzo"
solo**, sin tener que seleccionarlo — aparece en "Ausencia informada" y no
dispara alarma. Lo único que lo invalida es que ya haya marcado
**"Desconectado"** explícitamente.

### Desconectado automático al cerrar

Si el asesor cierra la pestaña o el navegador, el panel marca **"Desconectado"**
solo (vía `navigator.sendBeacon`, pensado para que la señal salga incluso
mientras la página se está cerrando). Así no queda "en línea" fantasma después
de que alguien se va.

## Apoyo a la zona presencial

Cuando la tienda se llena (o falta una vendedora presencial) y un vendedor de
chats pasa a atender allá, **no es una ausencia**: está trabajando, pero sus
chats quedan sin atender por prioridad de cliente presencial. El programa lo
trata como un caso propio:

- El asesor marca el estado **"En zona presencial"**, o se reporta la novedad
  **"Apoyo a presencial"** (esta última **suena**, porque deja chats solos).
- Aparece en **morado** con la nota *"sus chats quedan libres"*, distinto de una
  ausencia normal (amarillo) y de una alarma sin explicación (rojo).
- Soporte puede pulsar **Yo lo cubro** igual que en cualquier otro caso.
- La jefa ve en su resumen los **minutos desviados a presencial**, por persona y
  en total: es el costo operativo de frenar los chats.

Las **vendedoras presenciales** (rol `Venta presencial`) están en el equipo pero
nunca se piden cubrir: no atienden chats.

> Sobre la medición: cada cambio de estado es un punto en el tiempo, así que un
> tramo se mide hasta el cambio siguiente. Si un día terminó sin marcar la
> salida del estado, ese tramo cuenta **0** — se prefiere quedarse corto antes
> que inventar minutos. El tramo abierto de hoy sí cuenta hasta ahora.

## Personal rotativo

El área rota mucho, así que **solo la jefa** puede editar el equipo desde el
panel: agregar, cambiar rol/turno, y quitar con la ✕. Quitar **desactiva** (no
borra) para que el historial siga teniendo sentido; el mismo botón (↺) la vuelve
a activar si regresa.

## "Yo lo cubro"

En cada persona por cubrir hay un botón **Yo lo cubro** — **solo visible para
soporte** (quien eligió en "Soy:" un nombre marcado con `*` en la hoja, o con
rol Soporte en la hoja `Roles`). Un asesor de redes ve quién está cubriendo,
pero no el botón. Quien lo pulsa queda registrado como cobertura activa y el
resto ve *"cubre Mariana desde 2:15pm"*. Evita que dos personas de soporte
entren a la misma cuenta y deja el rastro de quién cubrió qué (y por cuántos
minutos).

## Vista de gestión (jefa de ventas)

Con el **PIN de la jefa** (`APP_PIN_JEFA`, distinto al de todos) la sesión toma
rol `jefa` y aparece al final del panel **Gestión · semana en curso**: por
persona, hora de entrada típica, días con señal, novedades y minutos cubierto.
Un asesor no la ve, y el servidor responde **403** si intenta consultarla.

## Puente con la Torre de Control

La Torre de Control (proyecto Django aparte) hace el análisis profundo. Para no
tener dos verdades, lee de la calculadora lo que esta captura:

```
GET /api/torre/historial?desde=2026-07-27&hasta=2026-08-02
Cabecera:  X-Token: <TORRE_TOKEN>
```

Devuelve las 4 tablas crudas (`presencia`, `estados`, `novedades`,
`coberturas`). Se autentica con su propio token, **no** con la cookie del
navegador; sin token configurado responde 503, con token inválido 401.

## Configuración (variables de entorno)

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `TURNOS_SHEET_ID` | Documento donde está el cuadro | el mismo documento espejo de precios |
| `TURNOS_HOJA` | Nombre de la pestaña del cuadro | `Horarios` |
| `TURNOS_HOJA_ROLES` | Pestaña opcional de roles | `Roles` |
| `ESTADO_DIR` | Carpeta de la base de datos | `datos/` del proyecto |
| `APP_PIN_JEFA` | PIN de la jefa (rol de gestión) | sin definir → sin rol jefa |
| `TORRE_TOKEN` | Token del puente de la Torre | sin definir → puente apagado |

Lo más simple es **agregar una pestaña `Horarios`** al documento espejo que ya
lee la calculadora: así no hay que compartir nada nuevo ni tocar variables.

Ajustes finos en `core/turnos.py`:
`TOLERANCIA_MIN` (gracia tras el inicio del turno, 15 min) y
`UMBRAL_INACTIVO_MIN` (sin señal para considerar inactivo, 30 min).

---

## Almacén

`datos/chatcenter.sqlite3` (volumen Docker), con **historial**: es lo que permite
mirar puntualidad y reincidencias por semana, y lo que consume la Torre. Tablas:
`presencia` (última señal y hora de entrada por día), `estados`, `novedades`
(con franja afectada y quién cubrió) y `coberturas`. Solo primer nombre y marcas
de tiempo: nada sensible.

En el servidor, la carpeta debe ser escribible por el usuario del contenedor:

```bash
mkdir -p datos && chown 1000:1000 datos
```

---

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/turnos/estado` | Todo lo que muestra el panel |
| POST | `/api/turnos/presencia` | Señal de presencia (la envía sola la app) |
| POST | `/api/turnos/estado-asesor` | Marcar en qué está (almuerzo, capacitación…) |
| POST | `/api/turnos/novedad` | Reportar ausencia/permiso/llegada tarde |
| POST | `/api/turnos/novedad/quitar` | Quitar una novedad |
| POST | `/api/turnos/ajuste` | Mover horario de hoy (turno/entrada/no viene/extra) |
| POST | `/api/turnos/ajuste/quitar` | Deshacer un ajuste |
| POST | `/api/turnos/cubrir` | "Yo lo cubro" |
| POST | `/api/turnos/cubrir/cerrar` | Liberar la cobertura |
| GET | `/api/equipo` | Lista del equipo (para el selector) |
| GET | `/api/equipo/gestion` | Equipo con inactivas — **solo jefa** |
| POST | `/api/equipo/guardar` | Agregar/editar persona — **solo jefa** |
| POST | `/api/equipo/quitar` | Desactivar persona — **solo jefa** |
| GET | `/api/gestion/resumen` | Métricas de la semana — **solo jefa** |
| GET | `/api/gestion/dia` | Foto de un día — **solo jefa** |
| GET | `/api/reloj.png` | Sello de fecha/hora del servidor |
| POST | `/api/salir` | Cerrar sesión (cambiar de PIN) |
| GET | `/api/torre/historial` | Puente para la Torre — **token propio** |

Todos exigen sesión (PIN) salvo el puente, que usa su token.

---

## Pruebas

```bash
python tools/test_turnos.py     # parser del cuadro + lógica de cobertura, sin red
```

Recrea un cuadro semanal de ejemplo (con colores) y verifica el parseo, la
tolerancia, los compensatorios, los roles y las alertas a distintas horas.
