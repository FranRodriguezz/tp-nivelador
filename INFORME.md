# Informe

## Ejercicio 1 — Escalado a 5 clientes

Se definieron 5 servicios de cliente en `docker-compose.yaml` (`client_0` a
`client_4`), cada uno con su propio `container_name` y `AGENCY_ID`, todos
dependientes de `server` vía `depends_on`.

**Ajuste adicional**: se detectó que, con 5 clientes arrancando en paralelo,
el presupuesto original de reconexión (`CONNECTION_ATTEMPTS_MAX=3`,
`CONNECTION_ATTEMPS_DELAY_MS=200`, ~600ms totales) resultaba insuficiente en
el entorno de desarrollo utilizado: el servidor Python tardaba sistemáticamente
más que ese margen en levantar el socket de escucha, ya que `depends_on` solo
garantiza el orden de arranque de contenedores, no que el proceso interno ya
esté aceptando conexiones. Se aumentaron las constantes a
`CONNECTION_ATTEMPTS_MAX=15` y `CONNECTION_ATTEMPS_DELAY_MS=500` (~7.5s de
margen), suficiente para el entorno de prueba.

## Ejercicio 2 — Exposición de puertos

Se agregó el mapeo `ports: ["5678:5678"]` al servicio `server` en
`docker-compose.yaml`, permitiendo verificar el funcionamiento del echo server
desde el equipo anfitrión con `nc localhost 5678`.

## Ejercicio 3 — Lectura de apuestas y persistencia de resultados

Se agregaron las variables `INPUT_FILE`/`OUTPUT_FILE` a `ClientConfig` y se
montaron como volúmenes en `docker-compose.yaml` (`./input/input-N.csv` de
solo lectura, y `./output` con permisos de escritura), evitando así que un
cambio en los archivos de entrada obligue a reconstruir la imagen.

El cliente lee `INPUT_FILE` línea por línea con `bufio.Scanner`, envía cada
línea al servidor y persiste la respuesta (en esta etapa, aún el eco simple)
en `OUTPUT_FILE`. Se agregó un `.gitignore` (`output/*`, `__pycache__/`,
`*.pyc`) para no versionar artefactos generados en cada corrida.

## Ejercicio 4 — `recv_all`/`send_all` tolerantes a short read/write

Se reimplementaron `SendAll`/`RecvAll` (Go) y `send_all`/`recv_all` (Python)
con un loop que acumula bytes enviados/recibidos hasta alcanzar el tamaño
esperado, en vez de asumir que una única llamada a `Write`/`Read` (Go) o
`send`/`recv` (Python) mueve la totalidad de los datos solicitados. Esto
respeta la restricción de la consigna de utilizar únicamente los métodos
`Read`/`Write` de `io.Reader`/`io.Writer` en Go, y `send`/`recv` de
`socket.socket` en Python (sin `recv_into` ni otras variantes).

Un caso particular a destacar en Python: `recv()` puede devolver `0` bytes sin
lanzar excepción para señalizar que el otro extremo cerró la conexión —a
diferencia de Go, donde `Read()` devuelve un `error` (`io.EOF`) en ese mismo
caso—, por lo que `recv_all` verifica explícitamente ese escenario y lanza
`ConnectionError`.

**Efecto observado**: una vez implementado correctamente, el sistema dejó de
funcionar de punta a punta bajo el esquema de buffer fijo del ejercicio 3
(cliente y servidor pedían un tamaño constante, 512/1024 bytes, que ya no
coincidía con el tamaño real de cada respuesta), entrando en deadlock mutuo.
Esto evidenció la necesidad de un protocolo con framing explícito, resuelto
en el ejercicio 5.

## Ejercicio 5 — Protocolo de comunicación

### Diseño general

Se implementó un protocolo binario simple, con un header de tamaño fijo (3 bytes)
que precede a cada mensaje, seguido de un payload de tamaño variable serializado
como texto delimitado por comas.

**Nota:** el uso de `json` (Python) y `encoding/json` (Go) está prohibido por la
consigna (validado por el test `Json`), por lo que se optó por un formato de
serialización propio.

### Formato del header

| Campo | Tamaño | Descripción |
|---|---|---|
| `msg_type` | 1 byte | Tipo de mensaje (ver tabla siguiente) |
| `length`   | 2 bytes | Longitud en bytes del payload que sigue |

El campo `length` se codifica en big-endian (`>BH` en Python con `struct`,
desplazamiento de bits manual en Go), permitiendo payloads de hasta 65535 bytes.

### Tipos de mensaje

| Tipo | Valor | Dirección | Payload |
|---|---|---|---|
| `BET`     | 0 | cliente → servidor | Campos de una apuesta separados por coma: `agency_id,first_name,last_name,document,birthdate,number` |
| `DONE`    | 1 | cliente → servidor | Vacío. Señaliza que el cliente terminó de enviar apuestas. |
| `WINNERS` | 2 | servidor → cliente | Lista de DNI ganadores separados por coma. |

### Decisiones de diseño

- **Por qué un mensaje `DONE` separado en vez de marcar la última apuesta**: 
  evita que el cliente necesite hacer lookahead sobre el archivo de entrada 
  (leer una línea de más para saber si la actual es la última), manteniendo 
  la responsabilidad de "contenido de apuesta" separada de "señal de fin de 
  stream".

- **Por qué `WINNERS` solo lleva el documento, no la apuesta completa**: 
  el servidor ya filtra las apuestas ganadoras por `agency_id` antes de 
  responder, por lo que el cliente no necesita volver a verificar a qué 
  agencia pertenece cada resultado. El documento es el único dato que la 
  agencia no puede reconstruir sin consultar al servidor.

- **Por qué las apuestas se serializan como texto delimitado por comas 
  y no en un formato binario más compacto**: simplicidad de implementación 
  dado que `json` está prohibido, y reutiliza la misma convención que ya usa 
  `Lottery.store_bets`/`load_bets` internamente para persistir en CSV.
  **Limitación conocida**: si algún campo de texto (ej. `first_name`) 
  contuviera una coma, el parseo por `split(",")` se rompería. No se 
  implementó escaping para este TP dado que los datos de entrada no 
  presentan ese caso.

### Manejo de errores y short read/write

El envío y recepción de cada mensaje se apoya en `send_all`/`recv_all` 
(`safe_socket`), que garantizan mandar/recibir la totalidad de los bytes 
esperados incluso si el sistema operativo entrega los datos en fragmentos 
más chicos que el tamaño solicitado (short write / short read). Estas 
funciones fueron implementadas en el ejercicio 4 usando únicamente 
`send`/`recv` (Python) y `Read`/`Write` (Go), sin bibliotecas externas.

## Ejercicio 6 — Batching

### Cambios al protocolo

Se reemplazó el tipo de mensaje `BET` (una apuesta por mensaje) por `BATCH`,
que transporta entre 1 y `BATCH_SIZE` apuestas codificadas, separadas por
salto de línea (`\n`) dentro del payload —usando la coma para separar los
campos de una apuesta individual, y el salto de línea para separar apuestas
dentro del batch—.

Se agregó un nuevo tipo de mensaje, `ACK`, con payload vacío, que el servidor
envía al cliente inmediatamente después de persistir con éxito un batch
completo. El cliente no envía el siguiente batch hasta recibir este `ACK`,
logrando así que el grueso de la sincronización esté dado por el intercambio
de mensajes y no por temporizaciones fijas.

Tipos de mensaje resultantes:

| Tipo | Valor | Dirección | Payload |
|---|---|---|---|
| `BATCH`   | 0 | cliente → servidor | N apuestas codificadas, separadas por `\n` |
| `DONE`    | 1 | cliente → servidor | Vacío |
| `WINNERS` | 2 | servidor → cliente | Lista de DNI ganadores separados por coma |
| `ACK`     | 3 | servidor → cliente | Vacío (confirmación) |

### Configuración

El tamaño de batch es configurable mediante la variable de entorno
`BATCH_SIZE` (definida en `docker-compose.yaml` para cada cliente). El
cliente acumula apuestas parseadas en memoria hasta alcanzar `BATCH_SIZE`
elementos, momento en el cual arma y envía el batch; al finalizar la lectura
del archivo de entrada, si quedó un resto de apuestas sin completar un batch
entero, se envía igualmente como un batch más chico.

Se utilizó `BATCH_SIZE=100` para las pruebas, un valor intermedio que permite
observar múltiples confirmaciones por agencia sin acercarse al límite de
65535 bytes que admite el campo de longitud del header (2 bytes).

### Manejo de errores

Ante cualquier error de decodificación de una apuesta dentro del batch, el
servidor no envía el `ACK` correspondiente; la conexión se corta al
propagarse la excepción, lo cual el cliente detecta como un error de
comunicación estándar (no se implementó un código de error explícito dentro
de `ACK`, ni reintento automático de un batch fallido, dado que la consigna
no lo exige).

### Verificación

Se validó que la cantidad de mensajes recibidos por el servidor por agencia
coincide con la cantidad esperada de batches (`⌈apuestas / BATCH_SIZE⌉ + 1`
por el mensaje `DONE`), y que el listado final de ganadores por agencia se
mantiene idéntico al obtenido antes de introducir el batching.