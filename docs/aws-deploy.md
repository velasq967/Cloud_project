# Despliegue AWS — Fase 1

> Cuenta: **AWS Academy Learner Lab**.
> Región sugerida: `us-east-1`.
> El paso a paso detallado, con capturas y comandos, está en la carpeta externa `manuales-proyecto/02-aws-paso-a-paso.md`.

## Arquitectura

```text
Internet
   |
   v
EC2 Ubuntu (Docker Compose)
   |-- frontend (Nginx :80)
   |-- api (FastAPI :8000)
   |
   v
RDS PostgreSQL (privado)
```

## Servicios usados

| Servicio | Uso |
|---|---|
| EC2 | Ejecutar Docker Compose |
| ECR | Guardar imágenes de API y frontend |
| RDS | PostgreSQL administrado |
| S3 | Bucket preparado para Fase 8 |
| CloudWatch | Logs (opcional en Fase 1) |

## Consideraciones de AWS Academy

- No se crean usuarios IAM ni presupuestos: se usa la sesión del laboratorio.
- Las credenciales AWS se obtienen en **AWS Details → AWS CLI** y expiran al terminar la sesión.
- La instancia EC2 usa el rol `LabInstanceProfile` (o el rol predefinido del laboratorio).
- El key pair suele ser `vockey`; descargar `labsuser.pem` desde AWS Details.
- Si ECR no está disponible en tu laboratorio, se puede construir la imagen directamente en EC2 y documentar el trade-off.
- Apagar/detener recursos al terminar para no consumir el presupuesto del laboratorio.

## Orden de despliegue

1. Verificar credenciales y región.
2. Crear bucket S3 (opcional en Fase 1).
3. Crear repositorios ECR `warehouse-api` y `warehouse-frontend`.
4. Construir y subir imágenes.
5. Crear RDS PostgreSQL privado.
6. Crear Security Groups:
   - EC2: SSH 22 desde tu IP, HTTP 80 desde Internet.
   - RDS: 5432 solo desde el Security Group de EC2.
7. Crear EC2 Ubuntu con Docker y `LabInstanceProfile`.
8. Ejecutar `db/init.sql` y `db/seed.sql` contra RDS desde EC2.
9. Crear `.env` en EC2 y levantar `docker-compose.prod.yml`.
10. Probar `http://<IP_PUBLICA>`.
11. Documentar evidencias y limpiar recursos.

## Archivos relevantes

- `docker-compose.prod.yml`
- `db/init.sql`
- `db/seed.sql`
- `.env.example` (sección de producción)
