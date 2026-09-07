# src/inventory_tool.py
import json
from pathlib import Path
from pydantic import BaseModel, Field

INVENTORY_PATH = Path(__file__).parent / "inventory.json"

with open(INVENTORY_PATH) as f:
    INVENTORY = json.load(f)

class CheckAvailability(BaseModel):
    """Check the current price and stock level for a specific TrailPeak product by its SKU."""
    sku: str = Field(..., description="The product SKU, e.g. TP-JKT-001")

def check_availability(sku: str) -> str:
    product = INVENTORY.get(sku.upper())
    if not product:
        return f"No product found with SKU {sku}."
    stock_status = "In stock" if product["stock"] > 0 else "Out of stock"
    return (
        f"{product['name']} (SKU {sku}): ${product['price']:.2f}, "
        f"{stock_status} ({product['stock']} units), "
        f"available sizes: {', '.join(product['sizes'])}"
    )