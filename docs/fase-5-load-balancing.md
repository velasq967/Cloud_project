# Fase 5 - Load balancing y escalamiento

## Qué se hizo

WH-002 (la bodega de alta carga) ahora tiene 3 réplicas de la API detrás de un Nginx. Las tres usan el mismo Redis y la misma PostgreSQL de WH-002.

```text
            localhost:8002
                 |
           Nginx (wh002-lb)
                 |
     +-----------+-----------+
     |           |           |
wh002-api-1 wh002-api-2 wh002-api-3
     |           |           |
     +-----------+-----------+
                 |
          wh002-redis (compartido)
                 |
           wh002-db (compartida)
```

- Nginx reparte con round robin (`services/load-balancer/nginx.conf`).
- Cada respuesta trae el header `X-Instance-Id` con el nombre de la réplica que la atendió. Así se ve el balanceo.
- Si una réplica se apaga, Nginx la saca del pool y reintenta el request en otra (`proxy_next_upstream`). Cuando vuelve, la agrega sola.
- Cada réplica tiene un límite de 1 CPU (`cpus: 1.0`), como si fueran máquinas separadas.
- WH-001 y WH-003 siguen con una sola API, porque su carga no lo necesita.

Las decisiones están en `docs/decisions.md` (ADR-013 y ADR-014).

## Cómo correrlo

```bash
make down-multi
make up-multi
make ps-multi     # deben salir wh002-api-1, wh002-api-2, wh002-api-3 y wh002-lb
```

Ver el reparto a mano:

```bash
for i in 1 2 3 4 5 6; do curl -s -D - -o /dev/null localhost:8002/health | grep -i x-instance-id; done
```

Debe ir rotando: `wh002-api-1`, `wh002-api-2`, `wh002-api-3`, ...

## Experimento 1: una instancia

```bash
make wh002-1                 # apaga api-2 y api-3
RATE=200 make load-lb
```

## Experimento 2: tres instancias

```bash
make wh002-3                 # prende api-2 y api-3
RATE=200 make load-lb
```

Si con 200 req/s no se nota diferencia, subir la tasa (`RATE=400`, `RATE=800`) y repetir los dos experimentos con el mismo valor.

| Experimento | Réplicas | req/s pedido | req/s logrado | Latencia promedio (ms) | p95 (ms) | % error |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1 | | | | | |
| 2 | 3 | | | | | |

Reparto en el experimento 2 (sale en el resumen de k6 como `requests_por_instancia`):

| Réplica | Requests |
|---|---:|
| wh002-api-1 | |
| wh002-api-2 | |
| wh002-api-3 | |

## Experimento 3: apagar una instancia

```bash
make lb-test
```

En Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\lb-test.ps1`

El script:
1. manda 9 requests y muestra qué réplica atendió cada uno;
2. durante 20 segundos manda requests seguidos, apaga `wh002-api-2` en el segundo 5 y la vuelve a prender en el 14;
3. cuenta cuántos requests fallaron (deben ser 0) y muestra que `wh002-api-2` vuelve a recibir tráfico.

Resultado obtenido:

> (captura de `make lb-test`)

## Preguntas

**¿Qué ocurre si Redis es local de cada instancia?**
Cada réplica tendría su propia caché. Un mismo producto podría estar guardado con valores distintos en cada una, y la respuesta dependería de a qué réplica te mande el balanceador.

**¿Por qué puede ser problemático?**
Porque cuando hay un movimiento solo se limpia la caché de la réplica que lo atendió (y la del cache-worker). Las otras dos siguen devolviendo el stock viejo hasta que venza el TTL. Por ejemplo, la réplica 1 dice que hay 100 unidades y la réplica 2 dice 70: el usuario ve números distintos al recargar. Además, cada réplica tendría que llenar su caché desde cero, así que hay más consultas a PostgreSQL.

**¿Dónde debería vivir el estado compartido?**
Fuera de las réplicas, en servicios que todas usan: PostgreSQL para los datos (inventario, movimientos) y Redis para la caché. En este proyecto cada bodega tiene los suyos y las réplicas de WH-002 comparten los de WH-002.

**¿Qué significa que una API sea stateless?**
Que no guarda nada importante en su memoria entre un request y otro. Cada request trae todo lo que necesita y la API lee y escribe en la base o en Redis. Por eso cualquier réplica puede atender cualquier request, se pueden agregar o quitar réplicas sin perder datos, y si una se cae no se pierde nada.

## AWS

En AWS el Nginx se reemplazaría por un Application Load Balancer (ALB) con un target group que use `GET /health` como health check y las réplicas de WH-002 como targets. La idea es la misma: el ALB solo manda tráfico a las réplicas sanas.
