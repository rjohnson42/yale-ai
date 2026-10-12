import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout.tsx";
import { AboutPage } from "./pages/AboutPage.tsx";
import { CreateAccountPage } from "./pages/CreateAccountPage.tsx";
import { HomePage } from "./pages/HomePage.tsx";
import { LoginPage } from "./pages/LoginPage.tsx";
import { ProductPage } from "./pages/ProductPage.tsx";
import { ProductsPage } from "./pages/ProductsPage.tsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="products/:productId" element={<ProductPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="create-account" element={<CreateAccountPage />} />
      </Route>
    </Routes>
  );
}
