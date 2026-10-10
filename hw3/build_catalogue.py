"""Build a structured catalogue from Campus Customs product photos.

Metadata comes from filenames. Visual search vectors come from one local
CLIP model, batched, so we never send the catalogue to a vision API.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from models import Catalogue, CatalogueEntry

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PRODUCTS_DIR = DATA_DIR / "products"
OUTPUT_PATH = ROOT / "output" / "catalogue.json"

EMBEDDING_MODEL = "clip-ViT-B-32"
BATCH_SIZE = 32
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Longer keys are listed first only for readability. Matching uses the
# earliest key in the slug, and the longer key when two start together.
GARMENTS: list[tuple[str, str]] = [
    ("sweater-fleece-jacket", "fleece jacket"),
    ("fleece-jacket", "fleece jacket"),
    ("fleece-sweater", "fleece sweater"),
    ("bomber-jacket", "bomber jacket"),
    ("full-zip-hoodie", "full-zip hoodie"),
    ("full-zip-hood", "full-zip hoodie"),
    ("double-knit-hood", "hoodie"),
    ("mockneck", "mockneck"),
    ("1-4-zip", "quarter-zip"),
    ("crewneck", "crewneck"),
    ("creqneck", "crewneck"),
    ("raglan-crew", "crewneck"),
    ("t-shirt", "t-shirt"),
    ("t-felt", "t-shirt"),
    ("hoodie", "hoodie"),
    ("long-sleeve", "long sleeve"),
    ("l-s", "long sleeve"),
]

# This studio photo is a crewneck. The filename leaves the cut out and
# ends in "tennis", which is not what the shirt says.
GARMENT_OVERRIDES = {
    "squash-left-chest-tennis": "crewneck",
}

COLLEGES: list[tuple[str, str]] = [
    ("benjamin-franklin", "Benjamin Franklin College"),
    ("jonathan-edwards", "Jonathan Edwards College"),
    ("grace-hopper", "Grace Hopper College"),
    ("timothy-dwight", "Timothy Dwight College"),
    ("davenport", "Davenport College"),
    ("saybrook", "Saybrook College"),
    ("berkeley", "Berkeley College"),
    ("branford", "Branford College"),
    ("pierson", "Pierson College"),
    ("trumbull", "Trumbull College"),
    ("morse", "Morse College"),
]

SCHOOLS: list[tuple[str, str]] = [
    ("school-of-public-health", "School of Public Health"),
    ("school-of-architecture", "School of Architecture"),
    ("school-of-engineering", "School of Engineering"),
    ("school-of-management", "School of Management"),
    ("school-of-medicine", "School of Medicine"),
    ("school-of-nursing", "School of Nursing"),
    ("school-of-music", "School of Music"),
    ("school-of-art", "School of Art"),
    ("divinity-school", "Divinity School"),
    ("law-school", "Yale Law School"),
    ("forest-school", "The Forest School"),
]

SPORTS: list[tuple[str, str]] = [
    ("track-and-field", "Track and Field"),
    ("track-field", "Track and Field"),
    ("field-hockey", "Field Hockey"),
    ("ice-hockey", "Ice Hockey"),
    ("basketball", "Basketball"),
    ("volleyball", "Volleyball"),
    ("baseball", "Baseball"),
    ("football", "Football"),
    ("swimming", "Swimming"),
    ("lacrosse", "Lacrosse"),
    ("fencing", "Fencing"),
    ("sailing", "Sailing"),
    ("hockey", "Hockey"),
    ("soccer", "Soccer"),
    ("tennis", "Tennis"),
    ("squash", "Squash"),
    ("diving", "Diving"),
    ("golf", "Golf"),
    ("crew", "Crew"),
]

FAMILY: list[tuple[str, str]] = [
    ("grandma", "Grandma"),
    ("grandpa", "Grandpa"),
    ("brother", "Brother"),
    ("cousin", "Cousin"),
    ("uncle", "Uncle"),
    ("aunt", "Aunt"),
    ("mom", "Mom"),
    ("dad", "Dad"),
]

BRANDS: list[tuple[str, str]] = [
    ("brooks-brothers", "Brooks Brothers"),
    ("hype-and-vice", "Hype and Vice"),
    ("champion", "Champion"),
    ("district", "District"),
    ("ua", "Under Armour"),
]

CAMPUS_THEMES = {
    "2025-yale-vs-harvard-t-shirt": "Yale vs Harvard",
    "basic-hoodie-big-yale": "Big Yale",
    "big-yale-tri-blend-t-shirt": "Big Yale",
    "boola-boola-t-shirt": "Boola Boola",
    "dry-zone-long-sleeve": "Yale Bulldogs",
    "poly-twill-crewneck-arched-yale": "Arched Yale",
    "super-heavyweight-crewneck-arched-yale-crest": "Arched Yale Crest",
    "t-felt-y-heavyweight": "Heavyweight Y",
    "yale-bowl-t-shirt": "Yale Bowl",
    "yale-maplehouse-diana-mockneck": "Maplehouse Diana",
}

# Chromatic names only. Near-gray pixels are named in `_nearest_color`
# before this table is used, so navy is not pulled toward black.
COLOR_NAMES: dict[str, tuple[int, int, int]] = {
    "navy": (36, 48, 78),
    "blue": (45, 90, 170),
    "red": (175, 40, 45),
    "maroon": (120, 30, 45),
    "green": (35, 115, 65),
    "yellow": (220, 185, 40),
    "pink": (214, 145, 128),
    "brown": (120, 75, 45),
    "purple": (110, 45, 130),
}


def ensure_data_layout(data_dir: Path) -> None:
    """Turn Windows-style zip names into real folders.

    Some copies of this dataset arrived as flat files named
    ``data\\products\\shirt.jpg`` inside ``data/``. Move those into
    ``data/products/`` (and the same for test images and video).
    """
    for path in list(data_dir.iterdir()):
        if not path.is_file() or "\\" not in path.name:
            continue
        parts = path.name.split("\\")
        relative = parts[1:] if parts[0] == "data" else parts
        dest = data_dir.joinpath(*relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        path.rename(dest)


def list_product_photos(products_dir: Path) -> list[Path]:
    photos = [
        path
        for path in products_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not photos:
        raise SystemExit(
            f"No product photos in {products_dir}. "
            "Expected image files under hw3/data/products."
        )
    return sorted(photos, key=lambda path: path.name)


def _find_key(text: str, key: str) -> int:
    """Index of `key` on hyphen boundaries, or -1.

    A raw substring search would treat the "brother" inside "brothers"
    as the family line.
    """
    start = 0
    while start < len(text):
        pos = text.find(key, start)
        if pos < 0:
            return -1
        before_ok = pos == 0 or text[pos - 1] == "-"
        end = pos + len(key)
        after_ok = end == len(text) or text[end] == "-"
        if before_ok and after_ok:
            return pos
        start = pos + 1
    return -1


def _earliest(text: str, pairs: list[tuple[str, str]]) -> tuple[str, str] | None:
    best_pos = None
    best_len = -1
    best: tuple[str, str] | None = None
    for key, label in pairs:
        pos = _find_key(text, key)
        if pos < 0:
            continue
        if best_pos is None or pos < best_pos or (pos == best_pos and len(key) > best_len):
            best_pos = pos
            best_len = len(key)
            best = (key, label)
    return best


def _mask_garment_words(slug: str) -> str:
    masked = slug
    for key, _label in sorted(GARMENTS, key=lambda item: len(item[0]), reverse=True):
        while True:
            pos = _find_key(masked, key)
            if pos < 0:
                break
            masked = masked[:pos] + ("-" * len(key)) + masked[pos + len(key) :]
    return masked


def garment_type_for(slug: str) -> str:
    if slug in GARMENT_OVERRIDES:
        return GARMENT_OVERRIDES[slug]
    found = _earliest(slug, GARMENTS)
    if found is None:
        raise ValueError(f"No garment type in filename: {slug}")
    return found[1]


def collection_for(slug: str) -> tuple[str, str, str | None]:
    """Return collection, theme, and brand."""
    family = _earliest(slug, FAMILY)
    if family is not None:
        return "family", family[1], None

    college = _earliest(slug, COLLEGES)
    if college is not None:
        return "college", college[1], None

    school = _earliest(slug, SCHOOLS)
    if school is not None:
        return "school", school[1], None

    sport = _earliest(_mask_garment_words(slug), SPORTS)
    if sport is not None:
        return "sport", sport[1], None

    brand = _earliest(slug, BRANDS)
    if brand is not None:
        return "brand", _brand_theme(slug, brand[0]), brand[1]

    theme = CAMPUS_THEMES.get(slug)
    if theme is None:
        raise ValueError(f"No collection theme for filename: {slug}")
    return "campus", theme, None


def _brand_theme(slug: str, brand_key: str) -> str:
    rest = slug[len(brand_key):] if slug.startswith(brand_key) else slug.replace(brand_key, "", 1)
    rest = _mask_garment_words(rest)
    for junk in ("yale", "university", "mens", "vit", "tri-blend"):
        rest = rest.replace(junk, "")
    words = [part for part in rest.split("-") if part and not part.isdigit()]
    if words:
        return " ".join(word.capitalize() for word in words)
    found = _earliest(slug, GARMENTS)
    if found is None:
        return "Yale"
    return found[1].title()


def display_name(slug: str) -> str:
    text = slug.replace("creqneck", "crewneck").replace("1-4-zip", "quarter-zip")
    text = text.replace("t-shirt", "tshirt").replace("-", " ")
    words = []
    for word in text.split():
        if word == "tshirt":
            words.append("T-Shirt")
        elif word in {"ua", "y"}:
            words.append(word.upper())
        elif word == "vs":
            words.append("vs")
        else:
            words.append(word.capitalize())
    return " ".join(words)


def describe(entry: dict[str, str | None]) -> str:
    brand = entry["brand"]
    maker = f" Sold under the {brand} label." if brand else " House line, no licensed brand in the filename."
    return (
        f"{entry['name']} is a {entry['primary_color']} {entry['garment_type']} "
        f"in the {entry['collection']} collection, themed {entry['theme']}."
        + maker
    )


def _nearest_color(rgb: np.ndarray) -> str:
    red, green, blue = (float(rgb[0]), float(rgb[1]), float(rgb[2]))
    peak = max(red, green, blue)
    chroma = peak - min(red, green, blue)
    # Studio shots are mostly neutral fabric. A small hue swing is still gray,
    # except a blue cast on a dark shirt, which is navy rather than black.
    if chroma < 36:
        if blue >= red + 12 and blue >= green + 8 and peak < 110:
            return "navy"
        warm = red >= blue + 10 and red + green > blue * 2.15
        if peak >= 220 and warm:
            return "ivory"
        if peak >= 228:
            return "white"
        if peak >= 170:
            return "light gray"
        if peak >= 105:
            return "gray"
        if peak >= 48:
            return "charcoal"
        return "black"
    best_name = "navy"
    best_distance: float | None = None
    for name, sample in COLOR_NAMES.items():
        distance = (red - sample[0]) ** 2 + (green - sample[1]) ** 2 + (blue - sample[2]) ** 2
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def primary_color(path: Path) -> str:
    """Most common garment color, after dropping a white or black studio backdrop."""
    with Image.open(path) as image:
        small = image.convert("RGB").resize((72, 72))
    pixels = np.asarray(small, dtype=np.int16).reshape(-1, 3)
    low = pixels.min(axis=1)
    high = pixels.max(axis=1)
    garment = pixels[~((low > 242) | (high < 18))]
    if len(garment) < 30:
        garment = pixels
    buckets = (garment // 16) * 16
    _unique, inverse, counts = np.unique(
        buckets, axis=0, return_inverse=True, return_counts=True
    )
    chosen = garment[inverse == int(np.argmax(counts))]
    return _nearest_color(np.median(chosen, axis=0))


def metadata_for(path: Path) -> dict[str, str | None]:
    slug = path.stem
    collection, theme, brand = collection_for(slug)
    garment = garment_type_for(slug)
    name = display_name(slug)
    record: dict[str, str | None] = {
        "product_id": slug,
        "name": name,
        "image_path": path.relative_to(ROOT).as_posix(),
        "garment_type": garment,
        "collection": collection,
        "theme": theme,
        "brand": brand,
        "primary_color": primary_color(path),
    }
    record["description"] = describe(record)
    return record


def _device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def embed_images(paths: list[Path]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    device = _device()
    print(f"model={EMBEDDING_MODEL} device={device} images={len(paths)}", flush=True)
    model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    images: list[Image.Image] = []
    for path in paths:
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    vectors = model.encode(
        images,
        batch_size=BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    for image in images:
        image.close()
    return np.asarray(vectors, dtype=np.float32)


def build_catalogue(photos: list[Path]) -> Catalogue:
    records = [metadata_for(path) for path in photos]
    vectors = embed_images(photos)
    if len(vectors) != len(records):
        raise RuntimeError(
            f"Embedding count {len(vectors)} did not match photo count {len(records)}."
        )
    dim = int(vectors.shape[1])
    entries: list[CatalogueEntry] = []
    for record, vector in zip(records, vectors):
        rounded = [round(float(value), 6) for value in vector]
        entries.append(
            CatalogueEntry(
                product_id=str(record["product_id"]),
                name=str(record["name"]),
                image_path=str(record["image_path"]),
                garment_type=str(record["garment_type"]),
                collection=str(record["collection"]),
                theme=str(record["theme"]),
                brand=record["brand"],
                primary_color=str(record["primary_color"]),
                description=str(record["description"]),
                embedding=rounded,
                embedding_model=EMBEDDING_MODEL,
                embedding_dim=dim,
            )
        )
    return Catalogue(
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=dim,
        normalized=True,
        product_count=len(entries),
        entries=entries,
    )


def main() -> None:
    ensure_data_layout(DATA_DIR)
    photos = list_product_photos(PRODUCTS_DIR)
    catalogue = build_catalogue(photos)
    checked = Catalogue.model_validate(catalogue.model_dump())
    if checked.product_count != len(photos):
        raise RuntimeError("Catalogue validation dropped entries.")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(checked.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {checked.product_count} entries to {OUTPUT_PATH.relative_to(ROOT)} "
        f"with {checked.embedding_model} ({checked.embedding_dim}-d).",
        flush=True,
    )


if __name__ == "__main__":
    main()
