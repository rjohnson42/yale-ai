import rawCatalogue from "./products.json" with { type: "json" };

export type SizeStock = {
  size: string;
  quantity: number;
};

export type Product = {
  productId: string;
  name: string;
  garmentType: string;
  description: string;
  colors: string[];
  searchTags: string[];
  imageFilePath: string;
  price: number;
  sizes: SizeStock[];
};

const featuredIds = [
  "2025-yale-vs-harvard-t-shirt",
  "pierson-college-crewneck",
  "basic-hoodie-big-yale",
  "yale-dad-crewneck",
];

export const products = rawCatalogue as Product[];

const byId = new Map(products.map((product) => [product.productId, product]));

export type GarmentFamily = "hoodie" | "crewneck" | "t-shirt" | "quarter-zip" | "jacket";

export const garmentFamilies: { id: GarmentFamily; label: string }[] = [
  { id: "hoodie", label: "Hoodies" },
  { id: "crewneck", label: "Crewnecks" },
  { id: "t-shirt", label: "T-shirts" },
  { id: "quarter-zip", label: "Quarter-zips" },
  { id: "jacket", label: "Jackets" },
];

/** Group the messy catalogue labels into the five families shoppers ask for. */
export function garmentFamily(garmentType: string): GarmentFamily | "other" {
  const text = garmentType.toLowerCase();
  if (text.includes("hoodie") || text.includes("hooded")) return "hoodie";
  if (text.includes("quarter-zip") || text.includes("quarter zip")) return "quarter-zip";
  if (text.includes("t-shirt") || text.includes("t shirt")) return "t-shirt";
  if (text.includes("jacket") || text.includes("bomber")) return "jacket";
  if (text.includes("crewneck") || text.includes("crew-neck") || text.includes("crew neck")) {
    return "crewneck";
  }
  return "other";
}

export function getProduct(productId: string): Product | undefined {
  return byId.get(productId);
}

export function featuredProducts(): Product[] {
  return featuredIds.flatMap((productId) => {
    const product = byId.get(productId);
    return product ? [product] : [];
  });
}

export function formatPrice(price: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(price);
}

/** Database paths look like `products/basic-hoodie-big-yale.jpg`. */
export function imageUrl(product: Product): string {
  return `/media/${product.imageFilePath}`;
}

export function inStockSizes(product: Product): SizeStock[] {
  return product.sizes.filter((size) => size.quantity > 0);
}
