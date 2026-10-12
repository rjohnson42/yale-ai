import { Link } from "react-router-dom";
import { formatPrice, imageUrl, type Product } from "../data/catalogue.ts";

type ProductCardProps = {
  product: Product;
};

export function ProductCard({ product }: ProductCardProps) {
  return (
    <Link className="product-card" to={`/products/${product.productId}`}>
      <span className="product-card-photo">
        <img src={imageUrl(product)} alt={product.name} />
      </span>
      <span className="product-card-body">
        <span className="eyebrow">{product.garmentType}</span>
        <span className="product-card-name">{product.name}</span>
        <span className="product-card-copy">{product.description}</span>
        <span className="product-card-price">{formatPrice(product.price)}</span>
      </span>
    </Link>
  );
}
