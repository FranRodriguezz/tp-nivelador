# TP0 - Sistemas Distribuidos I (75.74) - Informe

**Alumno**: Franco Ezequiel Rodríguez

**Padrón**: 102815

**Facultad**: FIUBA — Facultad de Ingeniería, Universidad de Buenos Aires

**Materia**: Sistemas Distribuidos I

**Cuatrimestre**: 2do 2026

---

**Nota general**: cada sección de este informe documenta las decisiones
tomadas en el momento de resolver ese ejercicio puntual. Algunas de esas
decisiones fueron modificadas en ejercicios posteriores (por ejemplo, el
tipo de mensaje `BET` del ejercicio 5 fue reemplazado por `BATCH` en el
ejercicio 6). El informe no vuelve a editar retroactivamente las secciones
anteriores para reflejar esos cambios; el diseño final vigente es el
descrito en la última sección donde el elemento en cuestión fue modificado.

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

**Nota**: la carpeta `input/` incluye un sexto archivo (`input-5.csv`) además
de los cinco usados. Se mantuvieron 5 clientes siguiendo la consigna
literal del ejercicio 1 ("Definir en el archivo `docker-compose.yaml` cinco
contenedores de clientes"), sin asumir que la cantidad de archivos de
entrada disponibles define la cantidad de clientes a levantar.

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

## Ejercicio 7 — Concurrencia y quorum

### Concurrencia

Se modificó `Server.run()` para que, tras aceptar cada conexión, delegue su
procesamiento a un `threading.Thread` independiente (`target=self._handle_client`)
en lugar de bloquear el loop principal hasta que esa conexión termine. Esto
permite que el servidor acepte y procese múltiples agencias en paralelo, en
vez de atenderlas serialmente como en los ejercicios anteriores.

Se optó por `threading` en lugar de `multiprocessing` dado que el trabajo del
servidor es mayormente I/O-bound (esperando datos de red), no CPU-bound. El
Global Interpreter Lock (GIL) de Python impide la ejecución simultánea de
bytecode en threads distintos, pero se libera automáticamente durante
operaciones de I/O bloqueante (`socket.recv`/`send`, `Condition.wait()`), por
lo que el paralelismo real logrado —solapar la espera de datos de una agencia
con el procesamiento de otra— no se ve limitado por el GIL en este caso de uso.

### Exclusión mutua sobre el storage compartido

`Lottery.store_bets` y `Lottery.load_bets` acceden al mismo archivo en disco
(`STORAGE_PATH`), compartido entre todos los threads. Ambas llamadas se
protegen con un único `threading.Lock` (`self.lottery_lock`), garantizando
que nunca dos threads lean o escriban el archivo simultáneamente.

### Storage único vs. uno por agencia

Se optó por un único archivo de storage (`STORAGE_PATH`) compartido entre
todas las agencias, en lugar de un archivo por agencia. Un storage por
agencia eliminaría la necesidad de sincronización sobre el recurso
(cada agencia escribiría en su propio archivo, sin contención), pero
también evitaría ejercitar el problema de concurrencia real que pide el
enunciado del ejercicio 7 — el propósito del ejercicio es precisamente
coordinar el acceso a un recurso genuinamente compartido entre threads.

### Quorum de agencias

Se agregó la variable de entorno `AGENCY_QUORUM_MIN`, que define la cantidad
mínima de agencias que deben notificar su finalización (mensaje `DONE`) antes
de que cualquiera de ellas pueda calcular y recibir su listado de ganadores.

La sincronización se implementa con un `threading.Condition` (`self.condition`)
y un contador compartido (`self.agencies_done`). Al recibir `DONE`, cada
thread, dentro de un único bloque `with self.condition:`, incrementa el
contador, notifica a los threads en espera si se alcanzó el quorum
(`notify_all()`), y luego espera (`wait()`) hasta que el quorum se cumpla —
esto último también cubre el caso del propio thread que aún no alcanzó el
mínimo con su incremento. Una vez satisfecho el quorum, todas las agencias
que lleguen después pasan sin esperar, ya que la condición de espera no
vuelve a ser verdadera (el contador es monótonamente creciente).

Se optó por incremento + notificación + espera dentro de una única sección
crítica (en lugar de operaciones separadas) para evitar una condición de
carrera en la que una notificación se emita antes de que algún thread haya
llegado a esperar, perdiéndose sin efecto.

### Limitación conocida

No se implementó un mecanismo de timeout ante agencias que nunca lleguen a
enviar su `DONE` (por ejemplo, ante una caída de red): en ese escenario, las
agencias que sí completaron su envío pero no alcanzaron el quorum quedarían
esperando indefinidamente.

## Ejercicio 8 — Cierre gracioso ante SIGTERM

### Servidor

Se capturó `SIGTERM` con `signal.signal(signal.SIGTERM, self.on_sigterm)`. El
manejador activa una flag compartida (`self.shutting_down`) y notifica a
todos los threads que pudieran estar esperando el quorum
(`self.condition.notify_all()`).

Para que ningún thread quede bloqueado indefinidamente ante la señal, se
aplicó timeout a los tres puntos de espera bloqueante del servidor:

- `server_socket.accept()`: timeout de 2s, revisando `self.shutting_down` en
  cada vuelta del loop de aceptación de conexiones.
- `client_socket.recv()` (dentro de `protocol.recv_message`): mismo timeout,
  cortando la conexión sin calcular ganadores si el corte fue por shutdown
  (no por un `DONE` real del cliente).
- `condition.wait()`: la condición de espera del quorum ahora también
  contempla `self.shutting_down`, permitiendo que los threads salgan sin
  haber alcanzado el mínimo de agencias si el servidor se está cerrando.

En ambos casos de salida forzada (timeout esperando mensajes, o quorum
interrumpido), el servidor no envía `WINNERS`, evitando entregar un
resultado parcial o inconsistente a la agencia.

Al recibir la señal, el proceso principal espera (`Thread.join`) a que todos
los threads de clientes activos finalicen, con un presupuesto de tiempo
total acotado (10s) que se reparte entre los threads restantes —evitando que
el tiempo de cierre crezca proporcionalmente a la cantidad de conexiones
activas—, coordinado con `stop_grace_period: 15s` en `docker-compose.yaml`.

### Cliente

Se capturó `SIGTERM` con `signal.Notify` sobre un canal (`os/signal`,
`syscall.SIGTERM`), siguiendo el patrón idiomático de Go (sin
`futures`/`asyncio`, tal como en el servidor). Se revisa el canal de forma
no bloqueante (`select` con rama `default`) en dos puntos: antes de procesar
cada línea del archivo de entrada, y antes de enviar el batch final/`DONE`.

Adicionalmente, la espera de la respuesta `WINNERS` tras el `DONE` se
protegió con `SetReadDeadline` (2s) en un loop, ya que es una llamada
bloqueante sin límite de tiempo por defecto que, de no interrumpirse, dejaría
al cliente esperando indefinidamente si el servidor nunca llega a completar
el quorum (evidenciado por el test `SigtermHandling` de la cátedra, que
configura un escenario donde el quorum requerido nunca puede alcanzarse).

En ambos casos, el cierre por señal retorna sin error (`nil`): un cierre
gracioso ante una señal de terminación es un comportamiento correcto, no una
falla, por lo que no se refleja como un código de salida distinto de 0.

## Fixes de última hora (validación contra `make test`)

Durante la validación final con la batería de tests de la cátedra
(`make test`) se detectaron y corrigieron los siguientes problemas, no
evidentes en las pruebas manuales anteriores:

- **Falso positivo en el test `ForcedExit`**: el nombre del método
  `exit_gracefully` hacía que se detectara como uso de funciones de salida
  tipo shell (`exit`/`quit`) mediante el patrón de regex que usa el test.
  Se modificó el nombre del método a `handle_sigterm` para que el test pasara
  correctamente.

- **Formato de `WINNERS` no coincidía con lo esperado por `OutputFiles`**:
  el diseño original enviaba solo el documento (DNI) de cada ganador. El
  test de la cátedra compara el contenido de `OUTPUT_FILE` contra la fila
  completa del `INPUT_FILE` original. Se modificó `encode_winners` para que
  transmita la fila completa (`first_name,last_name,document,birthdate,number`),
  omitiendo únicamente `agency_id` (redundante, ya conocido por la agencia).

- **`send_all` trataba un short-write de 0 bytes como cierre de conexión**:
  el test `ServerShortReadWrite` simula un socket cuyo `send()` puede
  devolver legítimamente 0 bytes en una llamada puntual (no como señal de
  cierre, sino como parte normal de un short-write). Se removió el chequeo
  de `n == 0` como caso de error en `send_all`, dejando que el loop
  simplemente reintente.

- **Espera de `WINNERS` sin timeout en el cliente**: ver detalle en la
  sección de Ejercicio 8 más arriba (descubierto mediante el test
  `SigtermHandling`).

- **Conflictos de nombre de contenedor entre corridas manuales y `make test`**:
  los `docker-compose` de la carpeta `tests/compose_files/` reutilizan
  nombres de contenedor (`server`, `client_0`) iguales a los del
  `docker-compose.yaml` raíz. Correr pruebas manuales y `make test` sin un
  `make down`/`docker rm -f` intermedio entre ambos puede generar fallos por
  conflicto de nombres, no relacionados con la lógica de la aplicación.