from pydantic import BaseModel, Field
from typing import List
from openai import pydantic_function_tool

class CalculateTotal(BaseModel):
    """Sum a list of item prices into a subtotal. Use this after checking
    individual product prices via CheckAvailability, when the user asks
    for a combined total across multiple items."""
    prices: List[float] = Field(..., description="List of individual item prices to sum")

def calculate_total(prices: List[float]) -> str:
    return f"Subtotal: ${sum(prices):.2f}"

TOOL_SCHEMA = pydantic_function_tool(CalculateTotal)
TOOL_FUNCTION = {"CalculateTotal": calculate_total}