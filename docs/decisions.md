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
