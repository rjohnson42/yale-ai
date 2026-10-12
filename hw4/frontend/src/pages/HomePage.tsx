import { Link } from "react-router-dom";
import { ProductCard } from "../components/ProductCard.tsx";
import { featuredProducts, formatPrice, imageUrl } from "../data/catalogue.ts";

const highlights = [
  {
    title: "College crests",
    copy: "Every residential college, Pierson to Grace Hopper. Crewnecks, quarter-zips, tees.",
    photo: "/lifestyle/campus-steps.jpg",
  },
  {
    title: "Sport marks",
    copy: "Hockey, crew, squash, sailing. Your team on the left chest.",
    photo: "/lifestyle/navy-zip.jpg",
  },
  {
    title: "Family pieces",
    copy: "Mom, Dad, Grandpa, Aunt. Same navy as the one who got in.",
    photo: "/lifestyle/friends.jpg",
  },
];

export function HomePage() {
  const featured = featuredProducts();
  const hero = featured[2] ?? featured[0];

  return (
    <>
      <section className="hero">
        <img className="hero-backdrop" src="/lifestyle/campus-walk.jpg" alt="" />
        <div className="hero-copy">
          <p className="eyebrow light">57 Broadway · New Haven</p>
          <h1>Bulldog blue, straight from Broadway.</h1>
          <p>
            Hoodies, crewnecks, and game-day tees from New Haven's oldest Yale
            shop. If it's listed here, it's on our shelf.
          </p>
          <Link className="button light" to="/products">
            Shop the rack
          </Link>
        </div>
        {hero ? (
          <Link className="hero-photo" to={`/products/${hero.productId}`} aria-label={hero.name}>
            <img src={imageUrl(hero)} alt="" />
            <span className="hero-photo-caption">
              <strong>{hero.name}</strong>
              <span>{formatPrice(hero.price)}</span>
            </span>
          </Link>
        ) : null}
      </section>

      <section className="band">
        <div className="highlights">
          {highlights.map((item) => (
            <article key={item.title}>
              <img src={item.photo} alt="" loading="lazy" />
              <div className="highlight-copy">
                <h2>{item.title}</h2>
                <p>{item.copy}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="band">
        <div className="section-head">
          <h2>On the rack</h2>
          <Link to="/products">Shop all</Link>
        </div>
        <div className="product-grid">
          {featured.map((product) => (
            <ProductCard key={product.productId} product={product} />
          ))}
        </div>
      </section>
    </>
  );
}
