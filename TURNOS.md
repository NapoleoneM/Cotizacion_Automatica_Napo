# Panel de turnos

Panel lateral (fuera de la calculadora) que muestra **en qué anda el equipo
del chat center ahora mismo**: quién está conectado, quién avisó por qué no
está, y a quién no se espera hoy.

No hay login: cada vendedor elige su primer nombre una sola vez (queda en su
navegador). Es una herramienta de coordinación, no de control de acceso.

> **Agosto de 2026 — el panel dejó de pedir coberturas.** Se eliminó el rol de
> soporte: todos son vendedores y nadie tiene que cubrir a nadie. Con eso se
> fueron la alarma roja "Requieren cobertura", el botón "Yo lo cubro", el
> contador de la lengüeta, los pitidos repetidos y las notificaciones del
> navegador. Lo que queda es **informativo, y se registra**: la presencia, los
> estados y las novedades siguen guardándose en la base de datos (es lo que
> alimenta el resumen de Gestión y la Torre de Control).

---

## Cómo funciona

1. **Presencia automática.** Como todos usan la calculadora para cotizar, al
   abrirla se envía una señal con el nombre elegido (y se repite cada 3 min
   mientras la pestaña esté abierta).
2. **El panel cruza tres cosas:** el horario semanal (Google Sheets), esa señal
   de presencia y la hora actual.
3. **Lo que muestra:**
   - **Ausencia informada** — en su turno, pero con una explicación: almuerzo,
     zona presencial, una sede del cuadro (Santa Fe, El Tesoro, Mostrador) o
     una novedad reportada.
   - **Novedades de hoy** — ausencias/permisos reportados, con hora y nota.
   - **En línea** — con actividad reciente.
   - **Aún no entran** — su turno todavía no comienza.
   - **Hoy no se espera** — compensatorio, ausencia, cambio de horario,
     vacaciones, y los turnos que ya terminaron.

Quien está **en su turno y no ha dado ninguna señal no aparece en ninguna
lista**: no hay nada que afirmar sobre esa persona y ya no hay a quién avisarle
para que la cubra. Esa falta de registro sí queda en el historial, y se ve en
**Gestión** (días con señal y hora de entrada típica).

**Después del cierre del día** (el fin más tardío entre los turnos: 7pm de
lunes a viernes con los horarios de hoy) el panel deja de mostrar a quien no
dio señal — no hay nada que informar. Pero **quien sí está dando señal se
sigue viendo en "En línea"** a cualquier hora: se quedó trabajando y eso es un
hecho, no una suposición.

Cualquiera puede reportar una novedad (propia o de un compañero), y quitarla.

---

## Cómo se reparten las responsabilidades

Hay dos horizontes de tiempo distintos y cada uno vive donde mejor funciona:

| | Dónde | Por qué |
|---|---|---|
| **Plan de la semana** | Google Sheets, hoja `Horarios` | Es trabajo de criterio y excepciones (compensatorios, Santafé, domingo reducido, Ceiba, notas puntuales). La jefa ya lo domina y el pantallazo para WhatsApp ya funciona. |
| **Ajustes de hoy** | La app | Un cambio a última hora tiene que ser **instantáneo y visible para todos**. Editar la hoja a media jornada no le avisa a nadie. |

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
quedan marcadas con **✎** para que se entienda por qué el panel dice algo
distinto al cuadro de la semana. La ✕ deshace el ajuste.

Los ajustes los puede registrar cualquiera con sesión (igual que las novedades),
pero siempre queda constancia del autor. Si más adelante conviene restringirlo a
la jefa, es un cambio pequeño.

## De dónde salen los nombres y los turnos

Hay **dos fuentes posibles**, y la app usa la primera que esté disponible:

1. **La hoja `Horarios` de Google Sheets** (la más rica: trae compensatorios,
   ausencias y cambios de horario por color). Ver la sección siguiente.
2. **El equipo registrado dentro de la app** — la jefa entra con su PIN y en el
   panel aparece **"Equipo del chat center"**: escribe el primer nombre, elige
   rol (Red social / Página web / Venta presencial / Auditoría de calidad /
   Jefa) y turno (1, 2 o 3). Clic en una persona para editarla; la ✕ la
   desactiva (no se borra: su historial sigue teniendo sentido). El rol es solo
   una etiqueta para el resumen de Gestión: ya no cambia lo que muestra el
   panel.

Con la opción 2 el panel funciona **sin depender de Sheets**: cada persona
trabaja su turno de lunes a sábado. Es la forma más rápida de arrancar. El pie
del panel indica qué fuente está en uso.

## Aviso sonoro

Un aviso en pantalla no sirve si nadie la está mirando, así que el panel
**suena una vez** cuando entra una novedad nueva:

- **Doble pitido** — una novedad *importante* (Ausencia, Incapacidad, Salida
  anticipada, Apoyo a presencial, Capacitación, Reunión): dejan chats sin
  atender.
- **Un pitido** — el resto (Llegada tarde, Cita médica, Permiso…).

Además, si la pestaña está en segundo plano, **el título parpadea** con el
nombre de la persona. La campanita 🔔 de la cabecera silencia el sonido (queda
guardado por navegador, así cada quien decide). Al abrir el panel no suena: solo
avisa de lo que llega *después*.

Ya **no** hay pitido repetido cada minuto ni notificaciones nativas del
navegador: existían para que soporte reaccionara a una cobertura, y las
coberturas se eliminaron.

El sonido se genera en el navegador (sin archivos externos). Si el navegador lo
bloquea por su política de autoplay, el aviso visual sigue funcionando.

## Sello de fecha y hora

Arriba del panel hay una franja con la **fecha y hora del servidor** dibujada
como **imagen** (`/api/reloj.png`), no como texto. Así, si alguien toma un
pantallazo para reportar una novedad, la fecha no se puede alterar editando el
HTML con las herramientas del navegador.

> Nota honesta: en un navegador nada es 100 % infalsificable — quien se empeñe
> puede reemplazar una imagen. La prueba fuerte es el **registro en la base de
> datos**, que guarda la hora del servidor en el momento del reporte; el sello
> solo hace que el pantallazo sea creíble de un vistazo.

## Cambiar de PIN / salir

En la cabecera del panel hay un botón **salir**: cierra la sesión y vuelve a
pedir el PIN. Es necesario porque la sesión dura 7 días, así que sin él quien
entró como vendedor no podría pasar al PIN de la jefa.

## La hoja de horarios (lo que mantiene la jefe de ventas)

El panel lee el **mismo cuadro semanal que ya se usa**, no hay que cambiar la
forma de trabajar. Solo debe vivir en Google Sheets y estar compartida en
**solo lectura** con el service account de la app.

Formato esperado:

- Una **fila de encabezado** con los días: `Lunes 27`, `Martes 28`, … `Domingo 2`
  (basta con que empiece por el nombre del día).
- Un **bloque por turno**. Hoy son tres: los dos turnos de ventas y, en el
  tercero, la **auditoría de calidad** (una sola persona, 10am a 6pm). El
  programa los trata igual. La primera celda del bloque lleva el rótulo:
  `1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm`
  Si el rótulo trae horas con `am/pm`, esas manda; si son ambiguas (`2:00 a 9:00`)
  se usan los horarios de respaldo definidos en `core/turnos.py` → `TURNOS`.
  Dos tolerancias, por si el rótulo viene escrito a la carrera:
  - **Sin número** (`Turno 10:00am a 6:00pm`) se usa la posición del bloque en
    la hoja. Lo que va después de la palabra "Turno" no se confunde con el
    número: en `Turno 10:00am` el 10 es la hora.
  - **Un rango con la hora de fin antes de la de inicio** (`10:00pm a 6:00pm`,
    casi siempre un `pm` donde iba `am`) se **ignora** y manda el respaldo del
    código, con un aviso en el log. El programa no adivina la intención: hay
    que corregir la hoja.
- Debajo de cada día, los **primeros nombres** de los vendedores de ese turno.
- El `*` al final de un nombre (ej. `Cristian*`) marcaba a soporte. Ese rol ya
  no existe, así que hoy el asterisco **no hace nada**: se le quita al nombre
  para que `Elvia*` y `Elvia` no cuenten como dos personas, y nada más.
- El título `Semana del ... al ...` **ya no hace falta escribirlo**: el panel
  calcula solo la semana en curso (corte el sábado a las 11pm).
- Una fila **`Leyenda:`** que marca dónde termina el cuadro — todo lo que va
  después (la leyenda, la tabla de almuerzo) se ignora al buscar turnos y
  nombres. Debajo de esa fila, el texto del estado y **el color a su
  derecha**: `Compensatorio`, `Ausencia`, `Cambio de Horario`, `CC Santafe`,
  `CC Tesoro` (o los nombres cortos `Santafe`/`Tesoro`, siguen funcionando).

Los **colores de las celdas** se leen igual que en la tabla de precios. Hay
tres formas de "no atender chats" y el panel las trata distinto:

| Estado | Significa | Dónde aparece |
|---|---|---|
| `Compensatorio`, `Ausencia`, `Cambio de Horario` | No trabaja ese día | "Hoy no se espera" |
| `CC Santafe`, `CC Tesoro` | Está trabajando, pero **presencial** en esa sede — sus chats quedan sin atender todo el turno | "Ausencia informada" (morado), igual que el traslado a zona presencial que reporta la propia persona |
| (celda blanca / sin color) | Normal | Según su señal de presencia |

### Hoja opcional `Roles`

Dos columnas: `Nombre | Rol`. Es la única fuente de roles desde que el `*` del
cuadro dejó de asignar ninguno, y es útil si prefieres administrarlos en un
solo lugar en vez de tocar cada celda. El rol **no cambia lo que muestra el
panel** (nadie cubre a nadie): sirve como etiqueta en el resumen de Gestión.

### Tabla de almuerzo (opcional)

Una tabla `Almuerzo | Desde | Hasta` con una fila por turno (`1 Turno`,
`2 Turno`, `3 Turno`) y sus horas — debajo de la leyenda, o **al lado** del
cuadro (en las mismas filas que la gente de turno 1, como quedó en agosto de
2026): el programa ubica la columna real donde está escrito "Almuerzo" en
vez de asumir una posición fija, así que ambas formas funcionan igual. El
rótulo `1 Turno`/`2 Turno`/`3 Turno` de esta tabla **nunca cuenta como un
bloque de turno nuevo**, aunque quede en las mismas filas que el turno 1: el
programa solo busca el rótulo del bloque en la columna justo antes de que
empiecen los días. Si la tabla no está en la hoja, se usa el respaldo por
código (`core/turnos.py` → `ALMUERZOS`). Ver más abajo cómo se aplica
automáticamente.

### Columna opcional `Vacaciones`

Una lista de nombres, uno por fila, debajo del rótulo `Vacaciones` — en
cualquier columna de la hoja (hoy vive en la columna T, al lado de la tabla
de Almuerzo). El programa ubica la columna real igual que con "Almuerzo", así
que se puede mover sin romper nada. Quien esté en esta lista **manda sobre
cualquier otra cosa** que diga el cuadro para esa persona (turno normal,
compensatorio, lo que sea) — no hace falta quitarla del cuadro para ponerla
en vacaciones, ni tampoco hace falta que tenga fila en el cuadro para
aparecer aquí (alguien que ya no está en el horario semanal, pero sigue de
vacaciones, funciona igual). Ver "Vacaciones" más abajo para el
comportamiento en el panel.

### Columna opcional `Auxiliares de bodega`

Misma mecánica que `Vacaciones`: el rótulo (basta que empiece por
"auxiliar") en cualquier columna, y debajo un nombre por fila. Hoy vive en la
columna **V** con Ferney y Jhian.

Esta gente **no atiende chats y no tiene turno en el cuadro**, pero sí usa la
calculadora, así que:

- Entra al selector **"Soy:"**, para que su presencia quede registrada igual
  que la de todos.
- **No aparece en ninguna lista del panel** — no hay turno con el que
  comparar, y no habría nada que informar.
- Al elegir su nombre y marcar **"Estoy: En zona presencial"**, se les
  habilitan los **datos de bodega** en la pestaña "Valor Tienda" (ver abajo).

---

## Datos de bodega en "Valor Tienda"

Los auxiliares cargan los productos a EFFI, y para eso necesitan más que el
precio sugerido. Con el peso y el tipo de material, la pestaña les muestra
además:

| Valor | Cómo se calcula | Columna de EFFI |
|---|---|---|
| **Costo** | `REDONDEAR.MAS(costo_gr × peso; -2)` (a la centena) | `S` (= `Inputs!L`) |
| **Precio mínimo venta** | `REDONDEAR(Costo × 1,05; 0)` | `T` |
| **Tarifa 1** | `Valor CO ÷ 1,19` (sin IVA) — **la única sin redondear**, va con dos decimales | `AB` |
| **Tarifa 2** | `x_mayor_cop × peso`, al millar | `AC` |
| **Tarifa 3 (Valor CO.)** | el mismo precio sugerido de tienda, sin recalcular | `AD` (= `Inputs!M`) |
| **Tarifa 4** | `joyerias_cop × peso`, al millar | `AE` |
| **Tarifa 5 (USD)** | `REDONDEAR.MAS(shopi_gr_usd × peso; 0)`, en dólares | `AF` |

Las **tarifas 2 y 4 nunca aplican acá**: sus fórmulas exigen que la categoría
sea "Pulsera Tejida" **y** que haya costo manual, y esta pestaña no pide
ninguna de las dos cosas. Se muestran igual, apagadas y con la nota "no
aplica", porque el auxiliar necesita saber que esas dos columnas de EFFI van
vacías (no es que falte el dato).

Los enteros llevan **separador de miles** para leerlos de un vistazo
(`6.900.000`). La Tarifa 1 es la excepción y se deja tal cual sale de la hoja
(`8605042,02`): es la única con decimales, y así se reconoce al compararla
contra la plantilla. Ninguna lleva `$` — son cifras de carga, no de lectura.

Mientras se ven los datos de bodega, la tarjeta "Precio sugerido para tienda"
**se oculta**: es el mismo número que "Tarifa 3 (Valor CO.)" y verlo dos veces
solo estorba. Para el resto del equipo, que no ve este bloque, la tarjeta
sigue igual que siempre.

Las cuatro cifras salen de la **misma fila de `pricing_gramo`** que el precio
de tienda (columna F `costo`, columna G `shopi_gr_cop`), así que la app **no
consulta el documento del catálogo**: un dato menos que pedirle a Google y una
hoja menos a la que darle acceso. Las fórmulas se leyeron del documento
"Ferney - Catálogo Napoleone Medellín" el 27/08/2026 y están replicadas en
`core/tienda_logic.py` → `detalle_bodega()`, con `tools/test_tienda.py` como
prueba de regresión.

> **Alcance:** solo el modelo de precio **"Pesado"** (peso y calidad), que es
> lo que pide esta pestaña. Con Piedra, Fabricación, Piercing, Set, Oferta y
> Pulsera Combo necesitan datos que no se piden acá (costo manual, peso del
> set 2, descuento) y tablas que no están en el espejo (`tarifas_joya`,
> `tarifas_piercing`, `var`). Si algún día se necesitan, hay que espejar esas
> hojas primero.

### Quién los ve

Hacen falta **las dos condiciones a la vez**:

1. El nombre elegido en "Soy:" está en la columna `Auxiliares de bodega`.
2. Su estado es **"En zona presencial"**.

Con "En chat" **no** se activan, y a un vendedor no se le activan nunca —
aunque escriba el nombre de un auxiliar, porque el estado lo marca la propia
persona y se guarda en el servidor. La comprobación vive en `app.py` →
`_puede_ver_bodega()`, **no en el navegador**: así el bloque no se puede
destapar editando el HTML, y el costo no viaja al cliente que no debe verlo.

El motivo de esconderlo es práctico: el costo confunde al equipo de ventas con
el precio de venta, y no es un dato que usen.

---

## Estados del vendedor

El vendedor marca en el panel **"Estoy:"** — En chat, Almuerzo, En zona
presencial (se quitaron *Disponible*, que "En chat" ya cubre, y *Baño*, por
ser tiempos demasiado breves para justificar un aviso). Capacitación y
Reunión **no están aquí**: al ser planeadas con anticipación, se reportan
como **novedad** (ver más abajo), no como estado en vivo. "Desconectado"
tampoco es seleccionable a mano — lo marca solo el navegador al cerrar la
pestaña (ver más abajo).

Marcar un estado es lo que hace que la persona aparezca en **Ausencia
informada** en vez de simplemente no aparecer: es la diferencia entre "está en
almuerzo" y "no sabemos nada de ella".

### Almuerzo automático

Dentro de la ventana de almuerzo de su turno (ver la tabla de la hoja, o el
respaldo `ALMUERZOS` en el código), la persona **queda marcada "Almuerzo"
sola**, sin tener que seleccionarlo — aparece en "Ausencia informada". Lo único
que lo invalida es que ya haya marcado **"Desconectado"** explícitamente.

> **El turno 3 no tiene almuerzo automático hoy.** El respaldo del código solo
> cubre los turnos 1 y 2: el del turno 3 era el de cuando ese bloque iba de
> 2pm a 9pm (almorzaba 6:00-6:20pm) y, al pasar a auditoría de calidad
> (10am-6pm), esa ventana caía justo al terminar la jornada. Se quitó en vez de
> inventarle una hora. Para que Laura tenga almuerzo automático hay que
> **agregar la fila `3 Turno` a la tabla de Almuerzo de la hoja** — la hoja
> siempre manda sobre el respaldo.

### Vacaciones

Quien esté en la columna `Vacaciones` de la hoja aparece en **"Hoy no se
espera"** con esa etiqueta, sin importar qué diga el cuadro para esa persona
(turno normal, compensatorio, lo que sea), y funciona igual tenga o no una fila
en el cuadro esta semana.

> Antes, vacaciones y turno terminado disparaban una revisión periódica de
> "clientes en proceso sin atender" que alguien tenía que confirmar. Eso se fue
> con las coberturas — ver `archivo/cobertura_soporte/`.

### Desconectado automático al cerrar

Si la persona cierra la pestaña o el navegador, el panel marca **"Desconectado"**
solo (vía `navigator.sendBeacon`, pensado para que la señal salga incluso
mientras la página se está cerrando). Así no queda "en línea" fantasma después
de que alguien se va.

## Apoyo a la zona presencial

Cuando la tienda se llena (o falta una vendedora presencial) y un vendedor de
chats pasa a atender allá, **no es una ausencia**: está trabajando, pero sus
chats quedan sin atender por prioridad de cliente presencial. El programa lo
trata como un caso propio:

- La persona marca el estado **"En zona presencial"**, o se reporta la novedad
  **"Apoyo a presencial"** (esta última **suena**, porque deja chats solos).
- Aparece en **morado** con la nota *"sus chats quedan libres"*, distinto de una
  ausencia normal (amarillo).
- La jefa ve en su resumen los **minutos desviados a presencial**, por persona y
  en total: es el costo operativo de frenar los chats.

> Sobre la medición: cada cambio de estado es un punto en el tiempo, así que un
> tramo se mide hasta el cambio siguiente. Si un día terminó sin marcar la
> salida del estado, ese tramo cuenta **0** — se prefiere quedarse corto antes
> que inventar minutos. El tramo abierto de hoy sí cuenta hasta ahora.

## Personal rotativo

El área rota mucho, así que **solo la jefa** puede editar el equipo desde el
panel: agregar, cambiar rol/turno, y quitar con la ✕. Quitar **desactiva** (no
borra) para que el historial siga teniendo sentido; el mismo botón (↺) la vuelve
a activar si regresa.

El rol que se le asigna aquí (ej. "Venta presencial") es una **etiqueta para
el resumen de Gestión**: ya no cambia lo que muestra el panel. Si la hoja
(cuadro o pestaña `Roles`) dice algo, esa manda; si no, se usa el de Equipo.

## Vista de gestión (jefa de ventas)

Con el **PIN de la jefa** (`APP_PIN_JEFA`, distinto al de todos) la sesión toma
rol `jefa` y aparece al final del panel **Gestión · semana en curso**: por
persona, hora de entrada típica, días con señal, novedades y minutos desviados
a presencial. Es lo que permite ver quién no está registrando su entrada, ya
que el panel en vivo dejó de avisarlo. Un vendedor no la ve, y el servidor
responde **403** si intenta consultarla.

La lista va ordenada por **menos días con señal primero** — lo que la jefa
revisa de una. Las métricas de cobertura y de tiempo de respuesta de soporte
que había antes ya no existen (ver `archivo/cobertura_soporte/`).

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
| `TURNOS_HOJA` | Nombre de la pestaña del cuadro | `Horarios` — **la pestaña real se llama `Chatcenter Horarios`, así que esta variable hay que definirla** |
| `TURNOS_HOJA_ROLES` | Pestaña opcional de roles | `Roles` |
| `ESTADO_DIR` | Carpeta de la base de datos | `datos/` del proyecto |
| `APP_PIN_JEFA` | PIN de la jefa (rol de gestión) | sin definir → sin rol jefa |
| `TORRE_TOKEN` | Token del puente de la Torre | sin definir → puente apagado |

El cuadro vive en una pestaña del documento espejo que ya lee la calculadora,
así que no hay que compartir nada nuevo. Pero **ojo con el nombre**: la pestaña
se llama `Chatcenter Horarios` (la jefa la renombró) y el valor por defecto del
código sigue siendo `Horarios`, que **no existe**. Sin `TURNOS_HOJA` en el
`.env` del servidor, la app no encuentra el horario y cae **en silencio** al
equipo registrado en la app — solo se nota en el pie del panel ("usando equipo
de la app") y en el log. En el `.env`:

```
TURNOS_HOJA=Chatcenter Horarios
```

Ajuste fino en `core/turnos.py`: `UMBRAL_INACTIVO_MIN` (minutos sin señal para
dejar de contar a alguien como "En línea", 30). Es el único que queda; los
umbrales de cobertura y tolerancia se retiraron con el mecanismo.

---

## Almacén

`datos/chatcenter.sqlite3` (volumen Docker), con **historial**: es lo que permite
mirar puntualidad y reincidencias por semana, y lo que consume la Torre. Tablas:
`presencia` (última señal y hora de entrada por día), `estados`, `novedades`
(con la franja afectada) y `ajustes`. Solo primer nombre y marcas de tiempo:
nada sensible.

Las tablas `coberturas` y `alertas` **siguen existiendo con su histórico**, pero
ya no se escriben: se dejaron porque los datos de antes siguen siendo válidos y
la Torre las lee. Ver `archivo/cobertura_soporte/`.

En el servidor, la carpeta debe ser escribible por el usuario del contenedor:

```bash
mkdir -p datos && chown 1000:1000 datos
```

---

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/turnos/estado` | Todo lo que muestra el panel |
| POST | `/api/precio-tienda` | Precio de tienda; con los datos de bodega si quien pregunta es auxiliar en zona presencial |
| POST | `/api/turnos/presencia` | Señal de presencia (la envía sola la app) |
| POST | `/api/turnos/estado-asesor` | Marcar en qué está (en chat, almuerzo, zona presencial) |
| POST | `/api/turnos/novedad` | Reportar ausencia/permiso/llegada tarde |
| POST | `/api/turnos/novedad/quitar` | Quitar una novedad |
| POST | `/api/turnos/ajuste` | Mover horario de hoy (turno/entrada/no viene/extra) |
| POST | `/api/turnos/ajuste/quitar` | Deshacer un ajuste |
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
python tools/test_turnos.py     # parser del cuadro + listas del panel, sin red
python tools/test_almacen.py    # presencia, estados, novedades y resumen (SQLite temporal)
python tools/test_tienda.py     # precio de tienda + datos de bodega (EFFI), sin red
```

`test_turnos.py` recrea un cuadro semanal de ejemplo (con colores) y verifica el
parseo — incluidos los rótulos de turno mal escritos, la tabla de Almuerzo al
lado del cuadro y la columna Vacaciones — y en qué lista del panel cae cada
persona a distintas horas. `test_almacen.py` usa un SQLite temporal (no toca el
real) y cubre presencia, estados, novedades, ajustes, equipo y el resumen de
Gestión.

---

## Historial del cambio grande

El mecanismo de **cobertura de soporte** ("Requieren cobertura", "Yo lo cubro",
pendientes de clientes, alarmas sonoras insistentes) se retiró el **27 de
agosto de 2026**, cuando el chat center dejó de tener rol de soporte. Está
guardado completo en **`archivo/cobertura_soporte/`** — código, frontend,
pruebas y este mismo documento tal como estaba — por si vuelve a haber personal
de soporte. Ese README explica qué habría que devolver a su sitio.
