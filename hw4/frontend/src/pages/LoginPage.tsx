import { type FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth.tsx";

export function LoginPage() {
  const { user, login } = useAuth();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError("");
    try {
      await login(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "That email and password don't match.");
      setPending(false);
    }
  }

  return (
    <section className="band account-band">
      <img className="account-photo" src="/lifestyle/campus-steps.jpg" alt="" />
      <form className="account-card" onSubmit={onSubmit}>
        <p className="eyebrow">Welcome back</p>
        <h1>Log in</h1>
        <p className="lede">Your saved chats are right where you left them.</p>
        <label>
          Email
          <input type="email" name="email" autoComplete="email" required />
        </label>
        <label>
          Password
          <input type="password" name="password" autoComplete="current-password" required />
        </label>
        <button className="button" type="submit" disabled={pending}>
          {pending ? "Checking…" : "Log in"}
        </button>
        {error ? <p className="notice error">{error}</p> : null}
        <p className="lede">
          New here? <Link to="/create-account">Make an account</Link>
        </p>
      </form>
    </section>
  );
}
