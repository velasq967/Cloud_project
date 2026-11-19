# Decisiones y trade-offs — Fase 1

Formato: **Problema → Alternativas → Decisión → Trade-offs → Mitigación**.

---

## ADR-001: Empezar con una sola bodega

**Problema:** la consigna final tiene múltiples bodegas, pero la Fase 1 pide una.

**Alternativas:**
1. Montar varias bodegas desde el inicio.
2. Implementar una bodega y evolucionar por fases.

**Decisión:** una bodega (`WH-001`).

**Trade-offs:** no se practican aún particionamiento ni consistencia distribuida.

**Mitigación:** el modelo ya incluye `warehouse_id` para no rediseñar la base en la Fase 4.

---

## ADR-002: Monolito modular en lugar de microservicios

**Problema:** el proyecto tiene dominios (productos, inventario) que podrían separarse.

**Alternativas:**
1. Microservicios desde el inicio.
2. Monolito modular con capas claras.

**Decisión:** monolito modular.

**Trade-offs:** un solo despliegue; no hay aislamiento de fallos por servicio.

**Mitigación:** los módulos están separados por dominio y se pueden extraer cuando exista una razón real (Fase 4+).

---

## ADR-003: Nginx como frontend y reverse proxy

**Problema:** el navegador necesita consumir la API sin problemas de CORS y con un solo origen.

**Alternativas:**
1. Abrir API y frontend en puertos separados y configurar CORS.
2. Servir el frontend con Nginx y proxy de `/api`.

**Decisión:** Nginx + proxy `/api`.

**Trade-offs:** una pieza más que configurar.

**Mitigación:** `API_TARGET` es una variable de entorno; el contenedor se adapta a local y AWS.

---

## ADR-004: PostgreSQL con transacción y bloqueo pesimista

**Problema:** dos salidas concurrentes podrían dejar stock negativo.

**Alternativas:**
1. Validar solo en aplicación.
2. Usar transacción + `SELECT ... FOR UPDATE`.
3. Usar bloqueo optimista con versión.

**Decisión:** transacción + `SELECT ... FOR UPDATE` sobre la fila de inventario.

**Trade-offs:** el bloqueo reduce concurrencia sobre el mismo producto.

**Mitigación:** el bloqueo es por fila y por producto; bodegas/productos distintos no se bloquean entre sí. En fases posteriores se puede evaluar bloqueo optimista.

---

## ADR-005: Semántica de reservas

**Problema:** hay que distinguir stock físico, reservado y disponible.

**Alternativas:**
1. `quantity` como stock físico y `reserved` aparte.
2. Descontar `quantity` al reservar.

**Decisión:** `quantity` es stock físico; `reserved_quantity` se acumula aparte; `available = quantity - reserved`.

**Trade-offs:** `SHIPMENT` solo puede sacar stock disponible; para despachar una reserva hay que liberarla primero o definir un flujo específico en una fase posterior.

**Mitigación:** se documenta la regla y se prueba con tests. La Fase 6 (transferencias/Saga) puede introducir movimientos más específicos.

---

## ADR-006: `create_all` + `init.sql` en Fase 1

**Problema:** se necesitan tablas reproducibles sin introducir demasiada complejidad.

**Alternativas:**
1. Solo `create_all`.
2. Solo SQL manual.
3. Alembic desde el inicio.

**Decisión:** `init.sql` para Docker/RDS + `create_all` como red de seguridad en desarrollo.

**Trade-offs:** no hay historial de migraciones; cambios de esquema requieren recrear el volumen o aplicar SQL manual.

**Mitigación:** Alembic se introduce en la Fase 2, cuando el esquema empiece a evolucionar (Redis no cambia el esquema, pero los workers sí).

---

## ADR-007: Tests con SQLite, integración con PostgreSQL

**Problema:** los tests deben ser rápidos y no depender de Docker.

**Alternativas:**
1. Tests solo contra PostgreSQL real.
2. Tests unitarios/integración con SQLite + smoke test contra PostgreSQL.

**Decisión:** pytest con SQLite para reglas + smoke test contra el Compose real.

**Trade-offs:** SQLite no reproduce exactamente `FOR UPDATE` ni todos los tipos de PostgreSQL.

**Mitigación:** el smoke test valida el flujo completo contra PostgreSQL; las pruebas de concurrencia real se harán en la Fase 11.

---

## ADR-008: Sin Redis en Fase 1

**Problema:** la consigna introduce Redis en la Fase 2.

**Alternativas:**
1. Agregarlo ya.
2. Esperar a tener una carga que lo justifique.

**Decisión:** no agregarlo todavía.

**Trade-offs:** las lecturas van siempre a PostgreSQL.

**Mitigación:** la Fase 2 medirá latencia/carga antes y después para justificar Redis.

---

## ADR-009: Credenciales fuera del repositorio

**Problema:** las credenciales no deben quedar en Git.

**Alternativas:**
1. Hardcodear en Compose.
2. `.env` local + variables de entorno en el servidor.

**Decisión:** `.env.example` en el repo; `.env` real fuera de Git. En AWS, variables de entorno del servidor y rol de instancia para servicios.

**Trade-offs:** hay que configurar el `.env` en cada entorno.

**Mitigación:** README y manuales explican el paso a paso; `.gitignore` excluye `.env` y `.pem`.

---

## ADR-010: Una base y un Redis por bodega (Fase 4)

**Problema:** con varias bodegas hay que decidir si comparten la base de datos.

**Alternativas:**
1. Una sola PostgreSQL para todas, separando por `warehouse_id`.
2. Una PostgreSQL y un Redis por bodega.

**Decisión:** cada bodega tiene su propia API, PostgreSQL y Redis.

**Trade-offs:** no hay transacción SQL entre bodegas (las transferencias van con Saga en la fase 6) y el inventario global necesita un read model (fase 7).

**Mitigación:** el código es el mismo para todas, solo cambian las variables de entorno. Si una bodega se cae o tiene mucha carga, las otras no se enteran.

---

## ADR-011: RabbitMQ compartido con colas por bodega (Fase 4)

**Problema:** en la fase 3 las colas escuchaban `warehouse.*`. Con un Redis por bodega, el cache-worker de WH-001 podía recibir eventos de WH-002 y borrar la caché equivocada.

**Alternativas:**
1. Un RabbitMQ por bodega.
2. Un RabbitMQ para todos, con colas separadas por bodega.

**Decisión:** un solo exchange `warehouse.events` y colas `<nombre>.<WAREHOUSE_ID>.q` que solo reciben `warehouse.<WAREHOUSE_ID>.*`.

**Trade-offs:** si RabbitMQ se cae, se pierden los eventos de ese rato.

**Mitigación:** la API sigue funcionando aunque RabbitMQ no responda (circuit breaker del publisher). En la fase 10 se agrega Outbox.

---

## ADR-012: Una EC2 por bodega con tamaño distinto (Fase 4)

**Problema:** las bodegas tienen cargas muy diferentes (50, 800 y 20 req/s).

**Alternativas:**
1. Todas en una sola EC2 grande.
2. Una EC2 por bodega, cada una con su tamaño.

**Decisión:** Terraform crea una EC2 por bodega desde la lista `warehouses`, más una EC2 central con RabbitMQ.

**Trade-offs:** cuesta más y hay más máquinas que administrar.

**Mitigación:** WH-002 es t3.medium y las otras t3.small. Para escalar una bodega se cambia una línea en `variables.tf`.

---

## ADR-013: Nginx como balanceador de WH-002 (Fase 5)

**Problema:** WH-002 tiene la carga más alta y una sola instancia de la API no alcanza.

**Alternativas:**
1. Una sola API más grande (escalar vertical).
2. Varias réplicas de la API detrás de un balanceador (escalar horizontal).

**Decisión:** 3 réplicas (`wh002-api-1`, `-2`, `-3`) detrás de Nginx con round robin. Nginx usa `resolve`, así que si una réplica se apaga sale del pool y cuando vuelve se agrega sola. Con `proxy_next_upstream`, si una réplica falla el request se reintenta en otra.

**Trade-offs:** Nginx pasa a ser un punto único de falla para WH-002 y se agrega un salto de red.

**Mitigación:** Nginx casi no consume recursos y no tiene estado. En AWS se reemplaza por un ALB, que es administrado y redundante.

---

## ADR-014: API stateless, estado en Redis y PostgreSQL (Fase 5)

**Problema:** con varias réplicas, cualquier request puede llegar a cualquiera, así que ninguna puede guardar cosas importantes en memoria.

**Alternativas:**
1. Sesiones o caché en memoria de cada réplica (sticky sessions).
2. Todo el estado en servicios externos compartidos.

**Decisión:** las 3 réplicas usan el mismo Redis y la misma PostgreSQL de WH-002. Solo `wh002-api-1` corre el seed y las otras arrancan después de ella, para que no corran migraciones al mismo tiempo.

**Trade-offs:** Redis y PostgreSQL ahora reciben el tráfico de las 3 réplicas.

**Mitigación:** la caché reduce las lecturas a la base. Si Redis se cae, la API sigue funcionando contra PostgreSQL (fase 2).

---

## ADR-015: Saga orquestada para transferencias (Fase 6)

**Problema:** una transferencia cambia el inventario de dos bodegas con bases separadas, y no hay transacción SQL entre ellas.

**Alternativas:**
1. Two-phase commit (2PC) entre las dos bases.
2. Saga coreografiada: cada bodega reacciona a los eventos de la otra.
3. Saga orquestada: un servicio central decide el siguiente paso.

**Decisión:** saga orquestada con `central-api` + `transfer-worker` y su propia base (`central-db`). El estado de cada transferencia y su historial quedan en un solo lugar.

**Trade-offs:** el orquestador es un componente más que puede fallar, y la transferencia no es instantánea (consistencia eventual).

**Mitigación:** el estado se guarda antes de cada paso y el worker retoma lo pendiente al arrancar y cada 5 s. 2PC se descartó porque bloquea las dos bases mientras espera y no funciona bien si una bodega se cae.

---

## ADR-016: Pasos idempotentes en las bodegas (Fase 6)

**Problema:** con reintentos, timeouts y mensajes duplicados, un mismo paso puede llegar varias veces a una bodega.

**Alternativas:**
1. Que el orquestador evite repetir pasos (no se puede garantizar si hay timeouts).
2. Que la bodega recuerde los pasos ya aplicados.

**Decisión:** tabla `transfer_operations` con `UNIQUE (transfer_id, step)` en cada bodega. Si el paso ya existe, se responde `already_done` sin tocar el inventario. El paso y el cambio de inventario se guardan en la misma transacción.

**Trade-offs:** una tabla más en cada bodega.

**Mitigación:** es lo que permite reintentar cualquier paso sin miedo, y resuelve el timeout, el duplicado y el reinicio del worker con el mismo mecanismo.

---

## ADR-017: El despacho es el punto de no retorno (Fase 6)

**Problema:** si el destino se cae después de que la mercancía salió del origen, ¿se compensa devolviéndola o se espera?

**Alternativas:**
1. Compensar devolviendo la mercancía al origen.
2. Esperar y reintentar la recepción hasta que el destino vuelva.

**Decisión:** antes de `dispatch` se compensa liberando la reserva. Después de `dispatch` solo se avanza: `DESTINATION_PENDING` y reintentos de `receive`.

**Trade-offs:** si el destino no vuelve nunca, la transferencia se queda pendiente.

**Mitigación:** antes de reservar se hace `check` al destino, así que no se empieza una transferencia hacia una bodega caída. Devolver la mercancía tiene su propio riesgo: si la recepción sí quedó pero la respuesta se perdió, la mercancía quedaría en las dos bodegas.

---

## ADR-018: Read model para el inventario global (Fase 7)

**Problema:** la central necesita el inventario total por SKU y cada bodega tiene su propia base.

**Alternativas:**
1. Consultar todas las bodegas en cada request (alternativa A).
2. Mantener un read model en la central alimentado por eventos (alternativa B, CQRS).

**Decisión:** las dos quedan implementadas para poder compararlas (`/global/inventory-live/{sku}` y `/global/inventory/{sku}`), y B es la consulta principal. `projection-worker` escucha `warehouse.*.INVENTORY_UPDATED` y mantiene la tabla `global_inventory` en `central-db`.

**Trade-offs:** consistencia eventual: el dato puede ir atrasado. Hay un worker y una tabla más que mantener.

**Mitigación:** la respuesta dice hace cuánto llegó el último dato de cada bodega, y `POST /global/rebuild` reconstruye todo desde las bodegas.

---

## ADR-019: SKU en los eventos y "gana el evento más nuevo" (Fase 7)

**Problema:** el `product_id` es distinto en cada base, y los eventos pueden llegar duplicados o desordenados.

**Alternativas:**
1. Tabla de eventos procesados (`processed_events`) para descartar duplicados.
2. Guardar la fecha del último evento aplicado y solo aceptar eventos más nuevos.

**Decisión:** `INVENTORY_UPDATED` ahora incluye el `sku`. Cada fila del read model guarda `last_event_at` y el upsert solo actualiza si el evento es más nuevo (`ON CONFLICT ... DO UPDATE ... WHERE last_event_at < excluded.last_event_at`).

**Trade-offs:** depende de que los relojes de las bodegas estén sincronizados.

**Mitigación:** como el evento trae el stock completo (no un "+10"), aplicar el más nuevo siempre deja el valor correcto, y con un solo mecanismo se cubren duplicados y desorden. En la nube los servidores sincronizan la hora con NTP.
