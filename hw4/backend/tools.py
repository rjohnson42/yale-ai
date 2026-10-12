"""Catalogue tools. These read inventory and product rows. They never touch passwords."""

from __future__ import annotations

import json
import re
import sqlite3

from db import connect
from models import (
    CatalogueSearchHit,
    CatalogueSearchResult,
    DescriptionLookup,
    PriceLookup,
    ProductCard,
    ProductSearchResult,
    SizeStock,
    StockLookup,
)

_WORD = re.compile(r"[a-z0-9]+")
_MAX_RESULTS = 8
_CHAT_RESULTS = 30


def _loads(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _sizes(connection: sqlite3.Connection, product_id: str) -> list[SizeStock]:
    order = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4, "XXL": 5}
    rows = connection.execute(
        "SELECT size, quantity FROM inventory WHERE product_id = ?",
        (product_id,),
    ).fetchall()
    sizes = [SizeStock(size=str(row["size"]), quantity=int(row["quantity"])) for row in rows]
    sizes.sort(key=lambda item: order.get(item.size, 99))
    return sizes


def _card(row: sqlite3.Row, sizes: list[SizeStock]) -> ProductCard:
    colors = _loads(str(row["colors"]))
    return ProductCard(
        product_id=str(row["product_id"]),
        name=str(row["name"]),
        price=float(row["price"]),
        garment_type=str(row["garment_type"]),
        image_file_path=str(row["image_file_path"]),
        description=str(row["description"]),
        colors=colors,
        in_stock_sizes=[item.size for item in sizes if item.quantity > 0],
        sizes=sizes,
    )


def _word_hits(blob: str, word: str) -> bool:
    if word in blob:
        return True
    if len(word) > 3 and word.endswith("s") and word[:-1] in blob:
        return True
    return False


def _blob(row: sqlite3.Row) -> str:
    parts = [
        str(row["name"]),
        str(row["garment_type"]),
        str(row["description"]),
        " ".join(_loads(str(row["colors"]))),
        " ".join(_loads(str(row["search_tags"]))),
    ]
    return " ".join(parts).lower()


def search_catalogue(
    query: str = "",
    garment_type: str = "",
    color: str = "",
    max_price: float | None = None,
    size: str = "",
    limit: int | None = None,
) -> ProductSearchResult:
    """Find catalogue rows that match the shopper's words, type, color, price, or size."""
    cap = _MAX_RESULTS if limit is None else max(1, min(int(limit), _CHAT_RESULTS))
    words = [word for word in _WORD.findall(query.lower()) if len(word) > 1]
    garment = garment_type.strip().lower()
    wanted_color = color.strip().lower()
    wanted_size = size.strip().upper()
    matched: list[ProductCard] = []
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT product_id, name, garment_type, description, colors,
                   search_tags, image_file_path, price
            FROM catalogue
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        for row in rows:
            blob = _blob(row)
            if words and not all(_word_hits(blob, word) for word in words):
                continue
            if garment and garment not in str(row["garment_type"]).lower():
                continue
            colors = " ".join(_loads(str(row["colors"]))).lower()
            if wanted_color and wanted_color not in colors and wanted_color not in blob:
                continue
            if max_price is not None and float(row["price"]) > max_price:
                continue
            sizes = _sizes(connection, str(row["product_id"]))
            if wanted_size:
                stock = next((item for item in sizes if item.size == wanted_size), None)
                if stock is None or stock.quantity <= 0:
                    continue
            matched.append(_card(row, sizes))
    note = ""
    if not matched:
        note = "No catalogue rows matched. Say so. Do not invent a product."
    elif not words and not garment and not wanted_color and max_price is None and not wanted_size:
        note = "No filter was set, so these are the first rows in name order, not a recommendation."
    return ProductSearchResult(
        query=query.strip(),
        total_matches=len(matched),
        returned=min(len(matched), cap),
        products=matched[:cap],
        note=note,
    )


def get_catalogue_product(product_id: str) -> ProductCard | None:
    """One product with its size quantities, or None if the id is not in the catalogue."""
    with connect() as connection:
        row = connection.execute(
            """
            SELECT product_id, name, garment_type, description, colors,
                   search_tags, image_file_path, price
            FROM catalogue
            WHERE product_id = ?
            """,
            (product_id.strip(),),
        ).fetchone()
        if row is None:
            return None
        return _card(row, _sizes(connection, str(row["product_id"])))


def search_for_agent(
    query: str = "",
    garment_type: str = "",
    color: str = "",
    max_price: float | None = None,
    size: str = "",
) -> CatalogueSearchResult:
    """Same match as search_catalogue, without description, price, or quantities."""
    if not any(
        (
            query.strip(),
            garment_type.strip(),
            color.strip(),
            size.strip(),
            max_price is not None,
        )
    ):
        return CatalogueSearchResult(
            query="",
            total_matches=0,
            returned=0,
            products=[],
            note="No filter was set. Pass garment_type or a query. Do not invent products.",
        )
    found = search_catalogue(
        query=query,
        garment_type=garment_type,
        color=color,
        max_price=max_price,
        size=size,
        limit=_CHAT_RESULTS,
    )
    return CatalogueSearchResult(
        query=found.query,
        total_matches=found.total_matches,
        returned=found.returned,
        products=[
            CatalogueSearchHit(
                product_id=card.product_id,
                name=card.name,
                garment_type=card.garment_type,
            )
            for card in found.products
        ],
        note=found.note,
    )


_SIZE_ORDER = ("XS", "S", "M", "L", "XL", "XXL")
_SIZE_ALIASES = {
    "XS": "XS",
    "EXTRA SMALL": "XS",
    "XSMALL": "XS",
    "S": "S",
    "SMALL": "S",
    "M": "M",
    "MEDIUM": "M",
    "MED": "M",
    "L": "L",
    "LARGE": "L",
    "XL": "XL",
    "EXTRA LARGE": "XL",
    "XLARGE": "XL",
    "XXL": "XXL",
    "EXTRA EXTRA LARGE": "XXL",
    "2XL": "XXL",
}


def _catalogue_row(connection: sqlite3.Connection, product_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT product_id, name, garment_type, description, colors,
               search_tags, image_file_path, price
        FROM catalogue
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()


def _matching_rows(connection: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    words = [word for word in _WORD.findall(query.lower()) if len(word) > 1]
    rows = connection.execute(
        """
        SELECT product_id, name, garment_type, description, colors,
               search_tags, image_file_path, price
        FROM catalogue
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    if not words:
        return []
    return [row for row in rows if all(word in _blob(row) for word in words)]


def _resolve(
    connection: sqlite3.Connection, product_id: str, query: str
) -> tuple[sqlite3.Row | None, str]:
    wanted_id = product_id.strip()
    if wanted_id:
        row = _catalogue_row(connection, wanted_id)
        if row is None:
            return None, f"No catalogue row has product_id {wanted_id}. Say it is not in the catalogue."
        return row, ""
    text = query.strip()
    if not text:
        return None, "Pass a product_id or the product name from the shopper."
    matches = _matching_rows(connection, text)
    if not matches:
        return None, "No catalogue rows matched. Say it is not in the catalogue. Do not invent one."
    if len(matches) > 1:
        shown = matches[:8]
        names = ", ".join(f"{row['name']} ({row['product_id']})" for row in shown)
        extra = "" if len(matches) <= 8 else f" {len(matches)} matched."
        return None, (
            "More than one product matched."
            + extra
            + " Ask which one, or call again with product_id. Do not pick a price or a stock count. "
            + names
        )
    return matches[0], ""


def _normalize_size(size: str) -> str:
    return _SIZE_ALIASES.get(size.strip().upper(), "")


def get_product_description(product_id: str = "", query: str = "") -> DescriptionLookup:
    """catalogue.description for one product. Does not read inventory or users."""
    with connect() as connection:
        row, note = _resolve(connection, product_id, query)
    if row is None:
        return DescriptionLookup(found=False, note=note)
    description = str(row["description"]).strip()
    placeholder = ""
    lowered = description.lower()
    if "vision blocked" in lowered or "filename-based stub" in lowered:
        placeholder = " The catalogue text is a placeholder. Do not invent a description."
    colors = _loads(str(row["colors"]))
    return DescriptionLookup(
        found=True,
        product_id=str(row["product_id"]),
        name=str(row["name"]),
        description=description,
        colors=colors,
        note=(
            "description is the catalogue sentence. colors is the catalogue color list. "
            "If the shopper asked for a color that is not in colors, say it is not offered. "
            "Do not add a color, a fabric, a fit, or a graphic the fields do not mention."
            + placeholder
        ),
    )


def get_product_price(product_id: str = "", query: str = "") -> PriceLookup:
    """catalogue.price for one product, as stored."""
    with connect() as connection:
        row, note = _resolve(connection, product_id, query)
    if row is None:
        return PriceLookup(found=False, note=note)
    price = float(row["price"])
    return PriceLookup(
        found=True,
        product_id=str(row["product_id"]),
        name=str(row["name"]),
        price=price,
        price_text=f"${price:.2f}",
        note="Quote price_text. It is catalogue.price. Do not round it or substitute another number.",
    )


def get_product_stock(product_id: str = "", query: str = "", size: str = "") -> StockLookup:
    """inventory.quantity for every size. Quantity 0 is out of stock."""
    asked = _normalize_size(size) if size.strip() else ""
    with connect() as connection:
        row, note = _resolve(connection, product_id, query)
        if row is None:
            return StockLookup(found=False, note=note)
        sizes = _sizes(connection, str(row["product_id"]))
    by_size = {item.size: item.quantity for item in sizes}
    for label in _SIZE_ORDER:
        if label not in by_size:
            sizes.append(SizeStock(size=label, quantity=0))
    sizes.sort(key=lambda item: _SIZE_ORDER.index(item.size) if item.size in _SIZE_ORDER else 99)
    out = [item.size for item in sizes if item.quantity <= 0]
    asked_quantity = next((item.quantity for item in sizes if item.size == asked), None) if asked else None
    if size.strip() and not asked:
        size_note = f" {size.strip()} is not a catalogue size. Sizes are XS, S, M, L, XL, XXL."
    elif asked and asked_quantity == 0:
        size_note = f" {asked} is out of stock (quantity 0). Say that clearly."
    elif asked and asked_quantity is not None:
        size_note = f" {asked} has {asked_quantity} in stock."
    else:
        size_note = ""
    counts = ", ".join(f"{item.size} {item.quantity}" for item in sizes)
    stock_note = (
        "Quantities are units on hand from inventory. "
        + counts
        + ". Out of stock: "
        + (", ".join(out) if out else "none")
        + ". A quantity of 0 means that size is out of stock."
        + size_note
    )
    return StockLookup(
        found=True,
        product_id=str(row["product_id"]),
        name=str(row["name"]),
        asked_size=asked,
        asked_quantity=asked_quantity,
        sizes=sizes,
        out_of_stock_sizes=out,
        note=stock_note,
    )


def cards_for(product_ids: list[str]) -> list[ProductCard]:
    """Keep ids that exist, in the caller's order, without duplicates."""
    cards: list[ProductCard] = []
    seen: set[str] = set()
    for product_id in product_ids:
        if product_id in seen:
            continue
        card = get_catalogue_product(product_id)
        if card is None:
            continue
        seen.add(product_id)
        cards.append(card)
        if len(cards) == _CHAT_RESULTS:
            break
    return cards
