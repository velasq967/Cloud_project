# Entrega final — Warehouse Cloud Platform

Proyecto integrador del curso **Computación en la Nube e Internet de las Cosas**. Este documento sigue la guía de entrega y evaluación: los siete entregables, la evaluación conceptual y la pregunta final. Cubre las fases 1 a 11.

---

## 1. Código (Git)

Aquí la estructura está casi como pide la rúbrica, con la excepción de que no hay una carpeta `tests/` en la raíz: cada servicio tiene sus propios tests en su carpeta correspondiente (`services/<servicio>/tests/`). Así cada servicio se prueba de forma independiente y `pytest` los recorre todos desde la raíz (`pyproject.toml`).

| Carpeta | Contenido |
| --- | --- |
| `services/` | Un directorio por servicio: `warehouse-api`, `workers`, `central`, `batch`, `lambda`, `frontend`, `load-balancer` (y los servicios IoT de la Fase 12) |
| `services/*/tests/` | Tests unitarios y de integración de cada servicio |
| `infrastructure/compose/` | Docker Compose por entorno: `compose.multi.yml` (todo en local), `compose.node.yml` (una bodega por EC2), `compose.central.yml` (EC2 central), `compose.core.yml` (una sola bodega, fases 1–3) |
| `infrastructure/observability/` | Configuración de Prometheus |
| `terraform/` | Infraestructura de AWS como código |
| `scripts/` | Pruebas de extremo a extremo y de fallos (`smoke-test`, `fault-test-wh002`, `lb-test`, `saga-test`, `cqrs-test`) y scripts de AWS |
| `load-tests/k6/` | Pruebas de carga |
| `libs/common/` | Código compartido: contrato de eventos, logging, correlation ID |
| `db/warehouse/` | `schema.sql` y `seed.sql` de referencia (el esquema real lo aplica Alembic en `services/warehouse-api/migrations/`) |
| `docs/` | Documentación, ADRs (`decisions.md`) y evidencias (`docs/evidencias/`) |
| `.github/workflows/` | CI: lint, tests y build de las imágenes |

---

## 2. Arquitectura final

```text
                              INTERNET
                                  |
                         +--------+--------+
                         |                 |
                   +-----+-----+           |
                   |  Central  |           |
                   |    API    |           |
                   +-----+-----+           |
                         |                 |
          +--------------+--------------+  |
          |              |              |  |
     Central DB      RabbitMQ        Workers centrales
    (Read Model)         |          (Saga, Proyeccion)
                         |                 |
        +----------------+-------+---------+-------+
        |                        |                 |
        v                        v                 v
   Warehouse 1              Warehouse 2       Warehouse 3
        |                        |                 |
        |                  Load Balancer           |
        |                        |                 |
   +----+----+              +----+----+       +----+----+
   |    |    |              |    |    |       |    |    |
  API Redis Workers       API x3 Redis Workers API Redis Workers
   |                        |                  |
   v                        v                  v
PostgreSQL              PostgreSQL         PostgreSQL
   |                        |                  |
   +------------------------+------------------+
                            |
                          Batch
                            |
                            v
                            S3
                            |
                            v
                          Lambda
```

### Principios

1. **Cada bodega es autónoma:** tiene su propia API, PostgreSQL, Redis y workers. Las bodegas no comparten base de datos.
2. **La central consolida y coordina:** mantiene el inventario global en un read model (CQRS) y orquesta las transferencias (Saga). No ejecuta operaciones de inventario de las bodegas.
3. **Los eventos desacoplan:** cada cambio de inventario se guarda junto con su evento (outbox) y se publica en RabbitMQ; los efectos secundarios ocurren en workers.
4. **Redis acelera lecturas; PostgreSQL es la fuente de verdad.**
5. **El procesamiento pesado sale del request:** reportes en workers, consolidación diaria en batch, procesamiento por evento en Lambda.
6. **Observabilidad transversal:** correlation ID, logs JSON y métricas en todos los servicios.

### Diferencias con la arquitectura de referencia

- **Load balancer:** está frente a WH-002 (Nginx con 3 réplicas, en local), no frente a la central. En AWS cada bodega tiene una instancia de la API.
- **S3, Batch y Lambda:** el batch consulta las bodegas por HTTP y sube los reportes a S3; S3 dispara la Lambda. Ninguno de los dos depende de RabbitMQ.
- **Bases de datos:** PostgreSQL corre en contenedores en cada EC2, no en RDS (ver ADR-027).
- **IoT (Fase 12):** el equipo integró la extensión IoT (MQTT, ingesta y workers) bajo el perfil `iot` de Docker Compose; está fuera del alcance de este documento.

---

## 3. ADRs

Las decisiones de las fases 1 a 7 están en `docs/decisions.md` (ADR-001 a ADR-019). Las de las fases 2, 3 y 8 a 11, y las del despliegue en AWS, se documentan aquí (ADR-020 a ADR-028).

### Decisiones registradas en `docs/decisions.md`

| ADR | Decisión | Fase |
| --- | --- | --- |
| 001 | Empezar con una sola bodega | 1 |
| 002 | Monolito modular en lugar de microservicios | 1 |
| 003 | Nginx como frontend y reverse proxy | 1 |
| 004 | Transacción y bloqueo pesimista (`SELECT … FOR UPDATE`) | 1 |
| 005 | Semántica de reservas (físico, reservado, disponible) | 1 |
| 006 | `create_all` + `init.sql` (luego Alembic) | 1 |
| 007 | Tests con SQLite, integración con PostgreSQL | 1 |
| 008 | Sin Redis en la Fase 1 | 1 |
| 009 | Credenciales fuera del repositorio | 1 |
| 010 | Una base y un Redis por bodega | 4 |
| 011 | RabbitMQ compartido con colas por bodega | 4 |
| 012 | Una EC2 por bodega con tamaño distinto | 4 |
| 013 | Nginx como balanceador de WH-002 | 5 |
| 014 | API stateless, estado en Redis y PostgreSQL | 5 |
| 015 | Saga orquestada para transferencias | 6 |
| 016 | Pasos idempotentes en las bodegas | 6 |
| 017 | El despacho es el punto de no retorno | 6 |
| 018 | Read model para el inventario global | 7 |
| 019 | SKU en los eventos y "gana el evento más nuevo" | 7 |

### ADR-020 — Uso de Redis (cache-aside)

**Contexto.** Las lecturas de inventario son la operación más frecuente (WH-002 tiene 800 req/s de lectura) y todas iban a PostgreSQL.

**Alternativas.** (1) Solo PostgreSQL. (2) Caché en memoria de cada instancia de la API. (3) Redis compartido por bodega con cache-aside.

**Decisión.** Redis por bodega con cache-aside: se busca en Redis, si no está se lee de PostgreSQL y se guarda con TTL de 30 s. Después de cada movimiento se borra la clave (`warehouse:<bodega>:inventory:<producto>`). Las validaciones de stock siempre leen PostgreSQL con `SELECT … FOR UPDATE`.

**Consecuencias.** Una API pasó de 56 a 388 req/s y de 6,9 % a 0 % de errores (Fase 11). La caché en memoria se descartó porque con varias réplicas cada una tendría un valor distinto. Riesgo aceptado: un dato puede quedar viejo hasta 30 s, pero nunca se usa para validar escrituras. Si Redis cae, la API sigue respondiendo desde PostgreSQL.

### ADR-021 — RabbitMQ y workers para procesos asíncronos

**Contexto.** Auditar, invalidar caché, generar reportes y avisar a la central no deben hacer más lento cada request ni hacerlo fallar.

**Alternativas.** (1) Hacerlo todo dentro del request. (2) Tareas en segundo plano dentro del mismo proceso de la API. (3) Un broker de mensajes con workers independientes.

**Decisión.** RabbitMQ con un exchange `topic` (`warehouse.events`), routing key `warehouse.<bodega>.<tipo>` y workers separados: auditoría, caché, reportes y outbox en cada bodega; Saga y proyección en la central. `POST /reports` responde 202 y el worker hace el reporte.

**Consecuencias.** La API responde rápido y los workers escalan por separado. A cambio aparecen duplicados, reintentos, orden de los mensajes y mensajes inválidos, que se resuelven en los ADR-022 y 023.

### ADR-022 — Outbox transaccional

**Contexto.** Guardar en PostgreSQL y publicar en RabbitMQ son dos sistemas distintos: si RabbitMQ estaba caído, el cambio de inventario quedaba sin evento y la central con el dato viejo.

**Alternativas.** (1) Publicar directo después del commit. (2) Transacción distribuida entre base y broker. (3) Outbox: guardar el evento en la misma transacción y publicarlo después.

**Decisión.** Tabla `outbox_events` escrita en la misma transacción que el inventario y el movimiento (también para `REPORT_REQUESTED`). Después del commit, la API publica solo los eventos de esa operación, con una conexión; el `outbox-worker` publica cada segundo los que hayan quedado pendientes (`FOR UPDATE SKIP LOCKED`).

**Consecuencias.** Ningún cambio queda sin su evento, aunque RabbitMQ esté caído. La entrega es "al menos una vez": un evento puede publicarse dos veces, por eso los consumidores son idempotentes (`processed_events`).

### ADR-023 — Reintentos con cola de espera, DLQ y errores no reintentables

**Contexto.** Un mensaje que siempre falla no puede reintentarse para siempre (bucle infinito) ni descartarse (se pierde). Además, dormir el worker entre reintentos lo bloqueaba.

**Alternativas.** (1) Devolver el mensaje a la misma cola (`requeue`). (2) Reintentar con `sleep` dentro del worker. (3) Cola de espera con TTL, máximo de intentos y DLQ.

**Decisión.** Cada cola tiene una `.retry` (el mensaje espera 1 s y luego 2 s, y vuelve solo a la cola principal) y una `.dlq`. Son 3 intentos en total; después, DLQ. Los errores que no se arreglan reintentando (JSON inválido, recurso inexistente, violación de restricción) van directo a la DLQ (`NonRetryableError`). El projection-worker de la central usa 5 intentos.

**Consecuencias.** Ningún mensaje bloquea la cola ni se pierde. Cada mensaje en la DLQ lleva su causa (`x-error-reason`) y sus intentos (`x-attempts`). Trade-off: un mensaje con espera corta puede quedar detrás de uno con espera larga en la cola de espera; nunca se reintenta antes de tiempo.

### ADR-024 — S3 y Batch para el reporte diario

**Contexto.** Consolidar el inventario de todas las bodegas es pesado y no debe hacerse dentro de un request HTTP.

**Alternativas.** (1) Un endpoint que arme el reporte en el request. (2) Un worker siempre encendido. (3) Un proceso batch que se ejecuta y termina.

**Decisión.** Un batch (`services/batch`) que pide a cada bodega su inventario (`GET /internal/inventory`) y sube a S3 un snapshot por bodega, un reporte consolidado y un registro de la ejecución. Las claves tienen la fecha (`reports/AAAA/MM/daily-summary-AAAA-MM-DD.json`).

**Consecuencias.** Es reejecutable: correrlo otra vez el mismo día sobrescribe los mismos archivos. Si una bodega está caída, el reporte sale `COMPLETED_WITH_ERRORS` y la lista. Hoy se ejecuta a mano (`make batch-run`); programarlo es el siguiente paso.

### ADR-025 — Lambda disparada por S3

**Contexto.** Cada reporte que llega a S3 debe validarse y transformarse en un resumen, pero solo una vez al día.

**Alternativas.** (1) Un worker siempre encendido que revise el bucket. (2) Hacerlo dentro del batch. (3) Una Lambda que se active con cada archivo nuevo.

**Decisión.** Lambda `warehouse-report-processor` disparada por `s3:ObjectCreated` en `reports/*.json`: valida, guarda el resumen en `exports/`, registra en CloudWatch y publica el evento (SNS si está configurado; si no, queda registrado en el log).

**Consecuencias.** No hay servidor encendido esperando y AWS la escala solo. Un archivo inválido queda registrado como `validation_failed`.

### ADR-026 — Observabilidad: correlation ID, logs JSON y Prometheus

**Contexto.** En un flujo distribuido (HTTP → API → RabbitMQ → worker → base) no se puede depurar sin seguir una misma operación por todos los componentes.

**Alternativas.** (1) Logs de texto por servicio. (2) Trazas distribuidas con una herramienta externa. (3) Correlation ID propio, logs JSON y métricas Prometheus.

**Decisión.** Cada request trae o recibe un `X-Correlation-ID`, que viaja en el evento y queda guardado en `inventory_movements`, `outbox_events` y `audit_log` (en transferencias es el `transfer_id`). Logs JSON en todos los servicios. Métricas en `/metrics`: requests, latencia, errores, caché y pool de la base en la API; mensajes, reintentos, DLQ y outbox en los workers; colas en RabbitMQ.

**Consecuencias.** Se puede seguir cualquier operación de punta a punta y medir P50/P95/P99. Prometheus corre en local (perfil `observability`); en AWS no se desplegó.

### ADR-027 — PostgreSQL en contenedores e IP privadas fijas en AWS

**Contexto.** Cada bodega necesita su propia base, y la central necesita las direcciones de las bodegas, mientras las bodegas necesitan la de RabbitMQ en la central.

**Alternativas.** (1) Un RDS por bodega. (2) PostgreSQL en contenedor dentro de cada EC2. Para las direcciones: descubrirlas al arrancar, o fijarlas.

**Decisión.** PostgreSQL en contenedor en cada EC2 y sin ECR (cada EC2 construye sus imágenes desde el repositorio). IP privadas fijas: central `10.0.1.10`, bodegas `10.0.1.11` a `10.0.1.13`.

**Consecuencias.** Menos costo y tiempo de despliegue en el Learner Lab, y la misma arquitectura en local y en AWS. A cambio: si una EC2 se recrea, su base se pierde y no hay respaldos automáticos. En producción se pasaría a RDS cambiando solo la `DATABASE_URL`. Las IP fijas evitan una dependencia circular entre las instancias en Terraform.

### ADR-028 — Bucket S3 creado con la AWS CLI desde Terraform

**Contexto.** En el Learner Lab, una política de la organización prohíbe `s3:GetBucketObjectLockConfiguration`. El recurso `aws_s3_bucket` de Terraform la consulta en cada `plan`, `apply` y `destroy`, que fallaban con un error 403.

**Alternativas.** (1) Crear el bucket a mano en la consola. (2) Otro proveedor de Terraform. (3) Crear y borrar el bucket con la AWS CLI desde Terraform (`terraform_data` + `local-exec`).

**Decisión.** Opción 3. Un recurso crea el bucket y lo vacía y borra en `destroy`. Otro verifica en cada `apply` que exista y lo recrea si alguien lo borró por fuera.

**Consecuencias.** `terraform apply` y `destroy` funcionan en el Learner Lab y la infraestructura sigue siendo reconstruible. Requiere la AWS CLI instalada y con credenciales vigentes donde se ejecuta Terraform.

---

## 4. Contratos de eventos

Todos los eventos de las bodegas usan el mismo sobre (`libs/common/warehouse_common/events.py`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `event_id` | texto (`EVT-<uuid>`) | Identificador único; base de la idempotencia |
| `event_type` | texto | Tipo de evento |
| `event_version` | entero | Versión del contrato (hoy 1) |
| `occurred_at` | fecha ISO 8601 (UTC) | Cuándo ocurrió; ordena los eventos en el read model |
| `correlation_id` | texto | Trazabilidad de punta a punta |
| `source` | texto | Bodega que lo emitió (`WH-001`, …) |
| `payload` | objeto | Datos del tipo de evento |

**Enrutamiento:** exchange `warehouse.events` (tipo `topic`, durable). Routing key `warehouse.<bodega>.<tipo>`, por ejemplo `warehouse.WH-001.INVENTORY_UPDATED`. Mensajes persistentes (`delivery_mode=2`), con `message_id = event_id` y `correlation_id` en las propiedades.

| Evento | Lo emite | Payload | Consumidores |
| --- | --- | --- | --- |
| `INVENTORY_MOVEMENT_REGISTERED` | Bodega (movimiento o paso de transferencia) | `warehouse_id`, `product_id`, `movement_id` (movimientos), `movement_type`, `quantity`, `resulting_quantity`, `resulting_reserved` | `audit-worker` |
| `INVENTORY_UPDATED` | Bodega | `warehouse_id`, `product_id`, `sku`, `quantity`, `reserved_quantity` (stock completo, no la diferencia) | `cache-worker`, `audit-worker`, `projection-worker` (central) |
| `REPORT_REQUESTED` | Bodega (`POST /reports`) | `job_id`, `report_type` (`INVENTORY_SNAPSHOT` o `MOVEMENTS_EXPORT`), `warehouse_id` | `report-worker` |
| `TRANSFER_REQUESTED` | Central (`POST /transfers`) | Mensaje simple, fuera del sobre común: `event_type`, `transfer_id`. Routing key `transfer.TRANSFER_REQUESTED` | `transfer-worker` |

**Colas por bodega:** `audit.events.<bodega>.q`, `cache.inventory.<bodega>.q` y `report.jobs.<bodega>.q`, cada una con su `.retry` y su `.dlq`. **Colas de la central:** `transfers.saga.q` y `central.projection.q` (con `central.projection.retry` y `central.projection.dlq`).

**Garantías:** entrega "al menos una vez" (outbox). Los consumidores son idempotentes por `event_id` (`processed_events`) y el read model aplica solo el evento más reciente por bodega y SKU, así que tolera duplicados y desorden.

---

## 5. Pruebas

Con el entorno levantado, `pytest -q` desde la raíz ejecuta 114 tests (el CI también corre lint y build de las imágenes).

### Unitarias y de integración

| Servicio | Tests | Qué cubren |
| --- | ---: | --- |
| `warehouse-api` | 45 | Reglas de inventario (stock nunca negativo, reservas), caché, outbox, reportes, pasos de transferencia idempotentes, métricas. Integración con la API completa (TestClient sobre SQLite) |
| `workers` | 27 | Colas por bodega, reintentos con espera, DLQ, errores no reintentables, report-worker (más la lógica IoT) |
| `central` | 27 | Saga (todos los caminos de fallo y compensación), read model (duplicados y desorden), projection-worker, `GET /warehouses` |
| `batch` | 4 | Snapshot, resumen global y subida a S3 |
| `lambda` | 3 | Validación y transformación del reporte |
| `iot-ingestion`, `iot-simulator` | 8 | Fase 12 (fuera del alcance de este documento) |

La integración contra PostgreSQL real se valida con `scripts/smoke-test.sh` sobre el entorno de Docker.

### Carga (k6, `load-tests/k6/`)

| Prueba | Script | Evidencia |
| --- | --- | --- |
| Carga distinta por bodega (Fase 4) | `phase4-multi-warehouse.js` | `make load-multi` |
| 1 vs 3 réplicas de WH-002 (Fase 5) | `phase5-wh002.js` | `docs/evidencias/fase5/k6-1-replica.txt` y `k6-3-replicas.txt` |
| Read model vs consulta en vivo (Fase 7) | `phase7-cqrs.js` | `docs/evidencias/fase7/load-cqrs.png` |
| Estrés con y sin Redis, 1 y 3 instancias (Fase 11) | `phase11-stress.js` | `docs/evidencias/fase11/` (4 archivos e `informe.txt`) |

Resultado principal (Fase 11, hasta 1.000 usuarios): 1 instancia sin Redis 56 req/s con 6,9 % de errores; con Redis 388 req/s; 3 instancias con Redis 675 req/s, P95 de 1,25 s y 0 % de errores.

### Fallos

| Prueba | Cómo se ejecuta | Resultado esperado | Evidencia |
| --- | --- | --- | --- |
| Bodega caída (Fase 4) | `make fault-wh002` | WH-001 y WH-003 siguen operando | `docs/evidencias/fase4/` |
| Réplica caída (Fase 5) | `make lb-test` | 0 errores con una réplica apagada | `docs/evidencias/fase5/lb-test.png` |
| Saga: 6 experimentos de fallo (Fase 6) | `make saga-test` | 8 de 8 OK | `docs/evidencias/fase6/` |
| Read model con bodega caída (Fase 7) | `make cqrs-test` | Read model responde; consulta en vivo incompleta | `docs/evidencias/fase7/cqrs-test.png` |
| Redis caído (Fases 2 y 10) | Apagar `wh001-redis` y leer inventario | 200 desde PostgreSQL; el cache-worker reintenta 3 veces y manda a la DLQ | Salida de comandos y consola de RabbitMQ |
| RabbitMQ caído (Fase 10) | Apagar `rabbitmq` y registrar un movimiento | 201; el evento queda en `outbox_events` y se publica al volver | Consulta a `outbox_events` antes y después |
| Mensaje inválido y duplicado (Fase 10) | Publicar desde la API de administración de RabbitMQ | JSON inválido directo a la DLQ; duplicado procesado una vez | Colas `.dlq` y conteo en `audit_log` |

---

## 6. Recursos de AWS

Cuenta AWS Academy (Learner Lab), región `us-east-1`. Todo se crea con Terraform.

| Recurso | Detalle |
| --- | --- |
| VPC | `10.0.0.0/16`, con internet gateway y tabla de rutas pública |
| Subred | `10.0.1.0/24`, pública, en la primera zona de disponibilidad |
| Security group central | SSH (tu IP), AMQP 5672 solo desde las bodegas, consola de RabbitMQ 15672 (tu IP), API central 8000 |
| Security group bodegas | SSH (tu IP), frontend 80, API 8000 |
| EC2 central | Ubuntu 22.04, t3.small, IP privada `10.0.1.10`: RabbitMQ, central-api (Swagger en `:8000/docs`), central-db, transfer-worker y projection-worker |
| EC2 WH-001 / WH-002 / WH-003 | Ubuntu 22.04; t3.small, **t3.medium** y t3.small; IP `10.0.1.11` a `.13`: frontend, API, PostgreSQL, Redis y workers |
| S3 | Bucket de reportes: `warehouses/`, `reports/`, `audit/`, `exports/` |
| Lambda | `warehouse-report-processor`, Python 3.12, rol `LabRole`, disparada por `reports/*.json` |
| CloudWatch Logs | `/aws/lambda/warehouse-report-processor` |

Cada EC2 arranca con un `user_data` que instala Docker, clona el repositorio y levanta su Docker Compose (`compose.central.yml` o `compose.node.yml`).

**Diferencias con las tecnologías sugeridas:** no se usan RDS ni ECR (ADR-027).

---

## 7. Terraform

La infraestructura se reconstruye desde cero con Terraform (`terraform/`):

| Archivo | Contenido |
| --- | --- |
| `main.tf` | Red, security groups, EC2, bucket S3, Lambda y su disparador |
| `variables.tf` | Región, red, tamaños de EC2 por bodega, repositorio, credenciales de RabbitMQ, nombre del bucket |
| `outputs.tf` | IP públicas y privadas, URL del Swagger central, consola de RabbitMQ, bucket y nombre de la Lambda |
| `user_data/*.tftpl` | Script de arranque de la central y de las bodegas |
| `terraform.tfvars.example` | Plantilla de valores (el `terraform.tfvars` real no se sube al repositorio) |

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # my_ip_cidr, rabbitmq_password, s3_bucket_name
terraform init
terraform apply
terraform output
terraform destroy                              # borra todo, incluido el bucket
```

**Requisitos:** credenciales vigentes del Learner Lab en `~/.aws/credentials`, AWS CLI instalada (crea el bucket, ADR-028) y el repositorio público en GitHub con los cambios en `main`, porque las EC2 lo clonan al arrancar.

---

## Evaluación conceptual

**Límites de cada dominio.** Cada bodega es dueña de su inventario, en su propia PostgreSQL, y ninguna lee ni escribe la base de otra. La central es dueña de las transferencias y del inventario global; no ejecuta movimientos, solo pide pasos a las bodegas por HTTP. Si todo estuviera en una sola base, una bodega con mucha carga afectaría a todas (ADR-010).

**Modelo de datos.** Por bodega: `products`, `inventory` (stock físico y reservado; disponible = físico − reservado; nunca negativo), `inventory_movements`, `outbox_events`, `processed_events`, `transfer_operations`, `audit_log` y `report_jobs`. En la central: `transfers`, `transfer_history` y `global_inventory`. El SKU es la llave entre bodegas; el `product_id` es local de cada base.

**Decisiones de caché.** Cache-aside con Redis por bodega, TTL de 30 s e invalidación después de cada movimiento. La caché solo acelera lecturas: las validaciones de stock siempre leen PostgreSQL con bloqueo. Si Redis cae, la API sigue funcionando (ADR-020).

**Estrategia de eventos.** Eventos con un sobre común, publicados con outbox en un exchange `topic`, con colas por bodega. Entrega "al menos una vez", con consumidores idempotentes (sección 4, ADR-021 y 022).

**Consistencia.** Fuerte dentro de cada bodega (transacción + `SELECT … FOR UPDATE`): dos salidas concurrentes no dejan stock negativo. Eventual entre bodegas (Saga) y en el read model, que muestra la antigüedad de cada dato. Se descartó 2PC porque bloquea las dos bases y no funciona si una bodega cae.

**Idempotencia.** `event_id` + `processed_events` en los workers; `UNIQUE (transfer_id, step)` en los pasos de la Saga; mismo `transfer_id` = misma transferencia; el read model solo aplica eventos más nuevos; el batch sobrescribe por fecha.

**Saga.** Orquestada por el `transfer-worker`, con el estado en `central-db`: verificar destino → reservar en origen → despachar → recibir. Antes del despacho, un fallo se compensa liberando la reserva; después, solo se avanza y se reintenta la recepción (ADR-015 a 017). Probada con 6 experimentos de fallo.

**CQRS.** Las escrituras van a la base de cada bodega; las consultas globales, al read model `global_inventory`, que el `projection-worker` mantiene con los eventos `INVENTORY_UPDATED`. Comparado con consultar las bodegas en vivo, el read model es más rápido y responde aunque una bodega esté caída, a cambio de consistencia eventual (ADR-018).

**Escalamiento.** Horizontal: WH-002 con 3 réplicas stateless detrás de Nginx. Vertical: EC2 de distinto tamaño por bodega. Y la caché, que descarga la base. Cada bodega escala sin afectar a las demás.

**Observabilidad.** Correlation ID de punta a punta, logs JSON, métricas Prometheus (RPS, P50/P95/P99, errores, hit ratio, colas, reintentos, DLQ, pool de conexiones) y health checks, incluido `GET /warehouses` en la central (ADR-026).

**Resiliencia.** Redis caído → PostgreSQL. RabbitMQ caído → outbox. Worker caído → colas persistentes y Saga que se retoma. Bodega caída → las demás siguen. Duplicados → se ignoran. Errores temporales → 3 intentos con espera. Errores permanentes → DLQ (ADR-022 y 023).

**Uso de AWS.** VPC, 4 EC2 (una por dominio), S3 para el histórico, Lambda por evento y CloudWatch, todo con Terraform. Sin RDS ni ECR para mantener la arquitectura igual en local y en AWS dentro de las limitaciones del Learner Lab (ADR-027 y 028).

---

## Pregunta final

> Si la plataforma tuviera que atender 100 bodegas y cada bodega tuviera una carga diferente, ¿qué componentes escalarían independientemente y por qué?

Escala por separado todo lo que pertenece a una bodega, porque cada bodega es un dominio autónomo que no comparte estado con las demás. Lo compartido escala aparte, según el total de eventos y de consultas globales.

| Componente | Escala según | Por qué puede escalar por separado |
| --- | --- | --- |
| API de cada bodega | Requests de esa bodega | Es stateless: el estado está en su Redis y su PostgreSQL (ADR-014) |
| Redis de cada bodega | Proporción de lecturas | Cada bodega tiene el suyo |
| PostgreSQL de cada bodega | Escrituras de esa bodega | Una base por bodega: no hay una base común que se sature (ADR-010) |
| Workers de cada bodega | Mensajes en sus colas | Colas por bodega (ADR-011) y workers idempotentes |
| RabbitMQ | Eventos de todas las bodegas | Compartido: pasaría a un clúster, repartiendo las colas por bodega |
| Central y read model | Consultas globales | CQRS: no consulta las 100 bodegas en cada request; réplicas de lectura de `central-db` |
| projection-worker y transfer-worker | Eventos y transferencias totales | Varias instancias: el read model tolera duplicados y la Saga usa un lock por transferencia |

Una bodega de alta lectura (800 req/s) escala API y Redis; una de alta actividad (2.000 req/s con escrituras) escala API, base y workers; una de baja actividad (20 a 50 req/s) se queda en una instancia pequeña.

**Soportado por:**

- **Arquitectura:** base, Redis, API y colas por bodega; read model en la central.
- **Métricas:** Fase 11, Redis multiplica por 7 las req/s de una API; 3 réplicas con Redis llegan a 675 req/s sin errores.
- **Pruebas:** con WH-002 caída las demás siguieron operando (Fase 4); una réplica apagada no generó errores (Fase 5); el read model responde con una bodega caída (Fase 7).
- **Decisiones técnicas:** ADR-010, 011, 012, 014 y 018.

Límite: las pruebas se hicieron con 3 bodegas y hasta 1.000 usuarios; con 100 bodegas, los primeros componentes a vigilar serían RabbitMQ y el projection-worker, porque reciben la carga de todas.
