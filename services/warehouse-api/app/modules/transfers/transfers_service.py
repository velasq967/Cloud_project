import logging
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from warehouse_common.events import EventTypes

from app.cache import cache_client
from app.config import settings
from app.correlation import get_correlation_id
from app.modules.inventory.inventory_repository import InventoryRepository
from app.modules.outbox.service import OutboxService
from app.modules.products.products_repository import ProductRepository
from app.modules.transfers.models import TransferOperationEntity
from app.modules.transfers.schemas import TransferStepRequest, TransferStepResponse

logger = logging.getLogger("warehouse.transfers")

STEPS = ("check", "reserve", "dispatch", "receive", "cancel")


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


class TransferStepService:
    """Pasos de una transferencia vistos desde una bodega.

    Todos son idempotentes: si el paso ya se aplico para ese transfer_id
    se responde lo mismo sin tocar el inventario otra vez.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = InventoryRepository(db)
        self.product_repo = ProductRepository(db)

    def _operation(self, transfer_id: str, step: str):
        return (
            self.db.query(TransferOperationEntity)
            .filter(
                TransferOperationEntity.transfer_id == transfer_id,
                TransferOperationEntity.step == step,
            )
            .first()
        )

    def _response(self, transfer_id, step, result, inventory=None, already_done=False):
        return TransferStepResponse(
            transfer_id=transfer_id,
            step=step,
            warehouse_id=settings.WAREHOUSE_ID,
            result=result,
            already_done=already_done,
            quantity=inventory.quantity if inventory else None,
            reserved_quantity=inventory.reserved_quantity if inventory else None,
        )

    def apply(self, transfer_id: str, step: str, body: TransferStepRequest) -> TransferStepResponse:
        if step not in STEPS:
            raise HTTPException(status_code=404, detail=f"Paso desconocido: {step}")

        product = self.product_repo.get_by_sku(body.sku)
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"El producto {body.sku} no existe en {settings.WAREHOUSE_ID}.",
            )

        if step == "check":
            inventory = self.repo.get_by_product(product.id)
            return self._response(transfer_id, step, "ok", inventory)

        try:
            # el lock de la fila de inventario serializa los pasos sobre el mismo producto,
            # asi dos mensajes duplicados no pueden aplicar el mismo paso a la vez
            inventory = self.repo.get_by_product_for_update(product.id)
            if not inventory:
                raise conflict("El inventario del producto no está inicializado.")

            done = self._operation(transfer_id, step)
            if done:
                self.db.rollback()
                logger.info(
                    "transfer_step_duplicated",
                    extra={"extra_fields": {"transfer_id": transfer_id, "step": step}},
                )
                return self._response(transfer_id, step, done.result, inventory, already_done=True)

            movement_type, result = self._change_stock(transfer_id, step, inventory, body.quantity)

            if movement_type:
                self.repo.register_movement(
                    product_id=product.id,
                    movement_type=movement_type,
                    quantity=body.quantity,
                    reference=transfer_id,
                    correlation_id=get_correlation_id(),
                )
            if result != "already_dispatched":
                self.db.add(
                    TransferOperationEntity(
                        transfer_id=transfer_id,
                        step=step,
                        product_id=product.id,
                        quantity=body.quantity,
                        result=result,
                    )
                )
            self.db.commit()
            self.db.refresh(inventory)
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception("transfer_step_failed")
            raise HTTPException(status_code=500, detail=f"Error en el paso {step}: {exc}")

        if movement_type:
            self._after_commit(product, movement_type, body.quantity, inventory)

        logger.info(
            "transfer_step_applied",
            extra={
                "extra_fields": {
                    "transfer_id": transfer_id,
                    "step": step,
                    "result": result,
                    "quantity": inventory.quantity,
                    "reserved_quantity": inventory.reserved_quantity,
                }
            },
        )

        # para el experimento de timeout: el paso ya quedo guardado pero la respuesta tarda
        if body.delay_seconds and settings.ALLOW_FAULT_INJECTION:
            time.sleep(body.delay_seconds)

        return self._response(transfer_id, step, result, inventory)

    def _change_stock(self, transfer_id, step, inventory, quantity):
        available = inventory.quantity - inventory.reserved_quantity
        cancelled = self._operation(transfer_id, "cancel")

        if step == "reserve":
            if cancelled:
                raise conflict("La transferencia ya fue cancelada en esta bodega.")
            if available < quantity:
                raise conflict(
                    f"Stock disponible insuficiente. Disponible: {available}, solicitado: {quantity}."
                )
            inventory.reserved_quantity += quantity
            return "RESERVATION", "reserved"

        if step == "dispatch":
            if cancelled:
                raise conflict("La transferencia ya fue cancelada en esta bodega.")
            if not self._operation(transfer_id, "reserve"):
                raise conflict("No hay reserva para esta transferencia.")
            inventory.reserved_quantity -= quantity
            inventory.quantity -= quantity
            return "TRANSFER_OUT", "dispatched"

        if step == "receive":
            inventory.quantity += quantity
            return "TRANSFER_IN", "received"

        # cancel: compensacion. Si la mercancia ya salio no se puede cancelar
        if self._operation(transfer_id, "dispatch"):
            return None, "already_dispatched"
        if self._operation(transfer_id, "reserve"):
            inventory.reserved_quantity -= quantity
            return "RELEASE", "released"
        # no habia reserva (ej: timeout antes de que llegara). Se guarda igual para
        # que una reserva que llegue tarde sea rechazada
        return None, "nothing_reserved"

    def _after_commit(self, product, movement_type, quantity, inventory):
        product_id = product.id
        cache_client.delete_inventory(product_id)

        # Igual que en los movimientos normales, los eventos de una
        # transferencia pasan por Outbox para no perderse si RabbitMQ cae.
        outbox = OutboxService(self.db)
        outbox_rows = outbox.enqueue(
            [
                (
                    EventTypes.INVENTORY_MOVEMENT_REGISTERED,
                    {
                        "warehouse_id": settings.WAREHOUSE_ID,
                        "product_id": product_id,
                        "movement_type": movement_type,
                        "quantity": quantity,
                        "resulting_quantity": inventory.quantity,
                        "resulting_reserved": inventory.reserved_quantity,
                    },
                ),
                (
                    EventTypes.INVENTORY_UPDATED,
                    {
                        "warehouse_id": settings.WAREHOUSE_ID,
                        "product_id": product_id,
                        # el sku es la llave común entre bodegas (fase 7)
                        "sku": product.sku,
                        "quantity": inventory.quantity,
                        "reserved_quantity": inventory.reserved_quantity,
                    },
                ),
            ],
            get_correlation_id(),
        )
        outbox_ids = [row.id for row in outbox_rows]
        self.db.commit()
        outbox.publish_now(outbox_ids)
