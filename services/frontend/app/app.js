// La URL es relativa: Nginx hace proxy de /api hacia el contenedor de FastAPI.
const API_BASE = "/api";

const state = {
    products: [],
};

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("product-form").addEventListener("submit", createProduct);
    document.getElementById("movement-form").addEventListener("submit", executeMovement);
    document.getElementById("refresh-stock-btn").addEventListener("click", loadDashboard);
    document.querySelector(".close-modal").addEventListener("click", closeHistory);
    document.getElementById("history-modal").addEventListener("click", (event) => {
        if (event.target.id === "history-modal") closeHistory();
    });

    checkHealth();
    loadDashboard();
});

async function apiFetch(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || `Error HTTP ${response.status}`);
    }
    return data;
}

async function checkHealth() {
    const badge = document.getElementById("health-status");
    try {
        const data = await apiFetch("/health");
        badge.textContent = `ONLINE — ${data.warehouse_id}`;
        badge.className = "status-badge ok";
        document.getElementById("warehouse-label").textContent = data.warehouse_id;
    } catch {
        badge.textContent = "OFFLINE — API desconectada";
        badge.className = "status-badge error";
    }
}

async function loadDashboard() {
    const tbody = document.querySelector("#stock-table tbody");
    tbody.replaceChildren();
    const loadingRow = document.createElement("tr");
    const loadingCell = document.createElement("td");
    loadingCell.colSpan = 7;
    loadingCell.className = "muted";
    loadingCell.textContent = "Cargando inventarios...";
    loadingRow.appendChild(loadingCell);
    tbody.appendChild(loadingRow);

    try {
        const products = await apiFetch("/products");
        state.products = products;
        updateProductSelect(products);

        if (products.length === 0) {
            tbody.replaceChildren();
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 7;
            cell.className = "muted";
            cell.textContent = "No hay productos registrados.";
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        const rows = await Promise.all(
            products.map(async (product) => {
                try {
                    const stock = await apiFetch(`/inventory/${product.id}`);
                    return { product, stock };
                } catch {
                    return {
                        product,
                        stock: {
                            quantity: 0,
                            reserved_quantity: 0,
                            available_quantity: 0,
                        },
                    };
                }
            }),
        );

        tbody.replaceChildren();
        rows.forEach(({ product, stock }) => {
            tbody.appendChild(renderStockRow(product, stock));
        });
    } catch (error) {
        tbody.replaceChildren();
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 7;
        cell.className = "muted";
        cell.textContent = `Error al cargar inventario: ${error.message}`;
        row.appendChild(cell);
        tbody.appendChild(row);
        showToast("Error al cargar la información del inventario", "error");
    }
}

function renderStockRow(product, stock) {
    const row = document.createElement("tr");

    row.appendChild(cellText(product.id));
    row.appendChild(cellText(product.sku, "strong"));
    row.appendChild(cellText(product.name));
    row.appendChild(cellText(stock.quantity, "quantity"));
    row.appendChild(cellText(stock.reserved_quantity, "reserved"));
    row.appendChild(cellText(stock.available_quantity, "available"));

    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "actions";

    const historyButton = document.createElement("span");
    historyButton.className = "action-link";
    historyButton.textContent = "Historial";
    historyButton.addEventListener("click", () => openHistory(product.id, product.name));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "btn-danger";
    deleteButton.textContent = "Eliminar";
    deleteButton.addEventListener("click", () => deleteProduct(product));

    actions.append(historyButton, deleteButton);
    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);

    return row;
}

function cellText(value, className = "") {
    const cell = document.createElement("td");
    cell.textContent = value ?? "-";
    if (className) cell.className = className;
    return cell;
}

function updateProductSelect(products) {
    const select = document.getElementById("move-product-id");
    const currentValue = select.value;
    select.replaceChildren();

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = products.length ? "Seleccione un producto" : "No hay productos";
    select.appendChild(placeholder);

    products.forEach((product) => {
        const option = document.createElement("option");
        option.value = String(product.id);
        option.textContent = `${product.sku} — ${product.name}`;
        select.appendChild(option);
    });

    if (currentValue && products.some((p) => String(p.id) === currentValue)) {
        select.value = currentValue;
    }
}

async function createProduct(event) {
    event.preventDefault();
    const payload = {
        sku: document.getElementById("sku").value.trim(),
        name: document.getElementById("name").value.trim(),
        category: document.getElementById("category").value.trim() || null,
        unit: document.getElementById("unit").value.trim() || "unit",
        description: document.getElementById("description").value.trim() || null,
    };

    try {
        const data = await apiFetch("/products", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        showToast(`Producto ${data.sku} creado`, "ok");
        document.getElementById("product-form").reset();
        await loadDashboard();
    } catch (error) {
        showToast(error.message, "error");
    }
}

async function deleteProduct(product) {
    const confirmed = window.confirm(
        `¿Eliminar ${product.sku} — ${product.name}? También se borrarán su inventario y movimientos.`,
    );
    if (!confirmed) return;

    try {
        await apiFetch(`/products/${product.id}`, { method: "DELETE" });
        showToast(`Producto ${product.sku} eliminado`, "ok");
        await loadDashboard();
    } catch (error) {
        showToast(error.message, "error");
    }
}

async function executeMovement(event) {
    event.preventDefault();
    const productId = Number(document.getElementById("move-product-id").value);
    if (!productId) {
        showToast("Seleccione un producto", "error");
        return;
    }

    const payload = {
        product_id: productId,
        type: document.getElementById("move-type").value,
        quantity: Number(document.getElementById("move-quantity").value),
        reference: document.getElementById("move-reference").value.trim() || null,
    };

    try {
        const data = await apiFetch("/inventory/movements", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        showToast(`Movimiento ${data.type} registrado`, "ok");
        document.getElementById("movement-form").reset();
        await loadDashboard();
    } catch (error) {
        showToast(error.message, "error");
    }
}

async function openHistory(productId, productName) {
    const modal = document.getElementById("history-modal");
    const title = document.getElementById("modal-title");
    const tbody = document.getElementById("history-table-body");

    title.textContent = `Historial — ${productName}`;
    tbody.replaceChildren();
    const loadingRow = document.createElement("tr");
    const loadingCell = document.createElement("td");
    loadingCell.colSpan = 5;
    loadingCell.className = "muted";
    loadingCell.textContent = "Cargando...";
    loadingRow.appendChild(loadingCell);
    tbody.appendChild(loadingRow);
    modal.classList.add("show");

    try {
        const movements = await apiFetch(`/inventory/${productId}/movements`);
        tbody.replaceChildren();

        if (movements.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 5;
            cell.className = "muted";
            cell.textContent = "Sin movimientos registrados.";
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        movements.forEach((movement) => {
            const row = document.createElement("tr");
            row.appendChild(cellText(movement.id));

            const typeCell = document.createElement("td");
            const isIncoming = ["RECEIPT", "TRANSFER_IN", "RETURN", "ADJUSTMENT"].includes(
                movement.type,
            );
            typeCell.textContent = movement.type;
            typeCell.className = isIncoming ? "movement-in" : "movement-out";
            row.appendChild(typeCell);

            row.appendChild(cellText(movement.quantity));
            row.appendChild(cellText(movement.reference || "-"));
            row.appendChild(cellText(new Date(movement.created_at).toLocaleString()));
            tbody.appendChild(row);
        });
    } catch (error) {
        tbody.replaceChildren();
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.className = "muted";
        cell.textContent = `Error al leer los movimientos: ${error.message}`;
        row.appendChild(cell);
        tbody.appendChild(row);
    }
}

function closeHistory() {
    document.getElementById("history-modal").classList.remove("show");
}

function showToast(message, type) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    window.setTimeout(() => {
        toast.className = "toast";
    }, 4000);
}
