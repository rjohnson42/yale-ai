import { Link, useParams } from "react-router-dom";
import { formatPrice, getProduct, imageUrl, inStockSizes } from "../data/catalogue.ts";

export function ProductPage() {
  const { productId } = useParams();
  const product = productId ? getProduct(productId) : undefined;

  if (!product) {
    return (
      <section className="band narrow">
        <h1>We don't carry that one.</h1>
        <p>The link may be old. Everything we do carry is on the rack.</p>
        <Link to="/products">Back to the shop</Link>
      </section>
    );
  }

  const available = inStockSizes(product);
  const colorLabel =
    product.colors.length > 0 ? product.colors.join(", ") : "Not listed";

  return (
    <section className="band">
      <Link className="back-link" to="/products">
        All products
      </Link>
      <article className="product-detail">
        <div className="product-detail-photo">
          <img src={imageUrl(product)} alt={product.name} />
        </div>
        <div className="product-detail-copy">
          <p className="eyebrow">{product.garmentType}</p>
          <h1>{product.name}</h1>
          <p className="price">{formatPrice(product.price)}</p>
          <p className="description">{product.description}</p>
          <dl className="facts">
            <div>
              <dt>Colors</dt>
              <dd>{colorLabel}</dd>
            </div>
            <div>
              <dt>In stock</dt>
              <dd>
                {available.length > 0
                  ? available.map((size) => size.size).join(", ")
                  : "Sold out in every size"}
              </dd>
            </div>
          </dl>
          <h2>Stock by size</h2>
          <ul className="size-list">
            {product.sizes.map((size) => (
              <li key={size.size} className={size.quantity === 0 ? "out" : ""}>
                <span>{size.size}</span>
                <span>{size.quantity === 0 ? "Sold out" : `${size.quantity} left`}</span>
              </li>
            ))}
          </ul>
        </div>
      </article>
    </section>
  );
}
