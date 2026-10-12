import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.tsx";
import { ChatWidget } from "./ChatWidget.tsx";

function itemClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link active" : "nav-link";
}

export function Layout() {
  const { user, logout } = useAuth();
  const greeting = user?.first_name || user?.name || "Account";

  return (
    <div className="site">
      <p className="announce">Official Yale gear · 57 Broadway since 1975</p>
      <header className="nav">
        <NavLink to="/" className="brand" end aria-label="Yale Bulldog Blue by Campus Customs, home">
          <img className="brand-logo" src="/brand/yale-bulldog-blue.png" alt="Yale Bulldog Blue" />
        </NavLink>
        <nav className="nav-links" aria-label="Shop">
          <NavLink to="/" className={itemClass} end>
            Home
          </NavLink>
          <NavLink to="/products" className={itemClass}>
            Products
          </NavLink>
          <NavLink to="/about" className={itemClass}>
            About Us
          </NavLink>
          {user ? (
            <>
              <span className="nav-user">Hi, {greeting}</span>
              <button type="button" className="nav-cta nav-logout" onClick={() => void logout()}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" className={itemClass}>
                Log in
              </NavLink>
              <NavLink
                to="/create-account"
                className={({ isActive }) => (isActive ? "nav-cta active" : "nav-cta")}
              >
                Create account
              </NavLink>
            </>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="site-footer">
        <img className="footer-logo" src="/brand/campus-customs-white.png" alt="Campus Customs" />
        <p>57 Broadway, New Haven, CT 06511</p>
      </footer>
      <ChatWidget />
    </div>
  );
}
