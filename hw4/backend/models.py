"""Structured types for the Campus Customs merch agent and chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SizeStock(BaseModel):
    size: str
    quantity: int


class ProductCard(BaseModel):
    """A catalogue item the shopper can open. Facts come from the database."""

    product_id: str
    name: str
    price: float
    garment_type: str
    image_file_path: str
    description: str = ""
    colors: list[str] = Field(default_factory=list)
    in_stock_sizes: list[str] = Field(default_factory=list)
    sizes: list[SizeStock] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _legacy_inventory(cls, value: object) -> object:
        if not isinstance(value, dict) or "in_stock_sizes" in value:
            return value
        inventory = value.get("inventory")
        if not isinstance(inventory, list):
            return value
        sizes: list[dict[str, object]] = []
        in_stock: list[str] = []
        for item in inventory:
            if not isinstance(item, dict):
                continue
            size = str(item.get("size", ""))
            quantity = int(item.get("quantity") or 0)
            sizes.append({"size": size, "quantity": quantity})
            if quantity > 0 and size:
                in_stock.append(size)
        return {**value, "sizes": sizes, "in_stock_sizes": in_stock}


class ProductSearchResult(BaseModel):
    query: str
    total_matches: int
    returned: int
    products: list[ProductCard]
    note: str = ""


class CatalogueSearchHit(BaseModel):
    """Enough to pick a product. Price, description, and stock stay on the fact tools."""

    product_id: str
    name: str
    garment_type: str


class CatalogueSearchResult(BaseModel):
    query: str
    total_matches: int
    returned: int
    products: list[CatalogueSearchHit]
    note: str = ""


class DescriptionLookup(BaseModel):
    """catalogue.description and colors for one product. Empty when the row is missing."""

    found: bool
    product_id: str = ""
    name: str = ""
    description: str = ""
    colors: list[str] = Field(default_factory=list)
    note: str = ""


class ShopperDeps(BaseModel):
    """Who is chatting and which page is open. Passed into the agent on every turn.

    Name and email come from the signed-in account. A guest leaves those blank.
    The page fields come from the browser path, and only after the product id
    matches a catalogue row.
    """

    signed_in: bool = False
    name: str = ""
    first_name: str = ""
    email: str = ""
    page_path: str = ""
    viewing_product_id: str = ""
    viewing_product_name: str = ""
    page_brief: str = ""


class PriceLookup(BaseModel):
    """catalogue.price for one product. price_text is that number formatted, not a guess."""

    found: bool
    product_id: str = ""
    name: str = ""
    price: float | None = None
    price_text: str = ""
    note: str = ""


class StockLookup(BaseModel):
    """inventory.quantity for every size. Zero is out of stock and is listed, not dropped."""

    found: bool
    product_id: str = ""
    name: str = ""
    asked_size: str = ""
    asked_quantity: int | None = None
    sizes: list[SizeStock] = Field(default_factory=list)
    out_of_stock_sizes: list[str] = Field(default_factory=list)
    note: str = ""


class ChatReply(BaseModel):
    """What the agent must return after it has used the catalogue tools."""

    reply: str = Field(min_length=1)
    product_ids: list[str] = Field(default_factory=list, max_length=30)


class SavedMessage(BaseModel):
    id: int
    role: str
    content: str
    products: list[ProductCard] = Field(default_factory=list)
    created_at: str


class ChatResponse(BaseModel):
    reply: str
    products: list[ProductCard] = Field(default_factory=list)
    message: SavedMessage
