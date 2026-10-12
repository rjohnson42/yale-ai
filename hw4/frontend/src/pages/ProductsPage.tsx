import { useMemo, useState } from "react";
import { ProductCard } from "../components/ProductCard.tsx";
import { garmentFamilies, garmentFamily, products, type GarmentFamily } from "../data/catalogue.ts";

function matchesQuery(product: (typeof products)[number], query: string): boolean {
  const words = query.toLowerCase().match(/[a-z0-9]+/g)?.filter((word) => word.length > 1) ?? [];
  if (words.length === 0) return true;
  const blob = [
    product.name,
    product.garmentType,
    product.description,
    product.colors.join(" "),
    product.searchTags.join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return words.every((word) => blob.includes(word) || (word.endsWith("s") && blob.includes(word.slice(0, -1))));
}

export function ProductsPage() {
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState<GarmentFamily | "all">("all");
  const counts = useMemo(() => {
    const tally = new Map<GarmentFamily, number>();
    for (const product of products) {
      const group = garmentFamily(product.garmentType);
      if (group !== "other") tally.set(group, (tally.get(group) ?? 0) + 1);
    }
    return tally;
  }, []);
  const visible = products.filter((product) => {
    if (family !== "all" && garmentFamily(product.garmentType) !== family) return false;
    return matchesQuery(product, query);
  });

  return (
    <section className="band">
      <div className="section-head">
        <div>
          <p className="eyebrow">Product Catalogue</p>
          <h1>Shop Yale</h1>
        </div>
        <p className="count">
          {visible.length} {visible.length === 1 ? "item" : "items"}
        </p>
      </div>
      <div className="filters">
        <label className="filter-search">
          <span className="sr-only">Search the catalogue</span>
          <input
            type="search"
            value={query}
            placeholder="Search your college, sport, or style"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="chips" role="group" aria-label="Garment type">
          <button
            type="button"
            className={family === "all" ? "chip active" : "chip"}
            aria-pressed={family === "all"}
            onClick={() => setFamily("all")}
          >
            All
          </button>
          {garmentFamilies.map((item) => (
            <button
              key={item.id}
              type="button"
              className={family === item.id ? "chip active" : "chip"}
              aria-pressed={family === item.id}
              onClick={() => setFamily(item.id)}
            >
              {item.label}
              <span className="chip-count">{counts.get(item.id) ?? 0}</span>
            </button>
          ))}
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="empty-catalogue">
          No luck with that one.
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setQuery("");
              setFamily("all");
            }}
          >
            Clear filters
          </button>
        </p>
      ) : (
        <div className="product-grid">
          {visible.map((product) => (
            <ProductCard key={product.productId} product={product} />
          ))}
        </div>
      )}
    </section>
  );
}
