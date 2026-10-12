import { type FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth.tsx";

export function CreateAccountPage() {
  const { user, register } = useAuth();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirmPassword") ?? "");
    if (password !== confirm) {
      setError("Those passwords don't match.");
      return;
    }
    setPending(true);
    setError("");
    try {
      await register({
        first_name: String(form.get("firstName") ?? ""),
        last_name: String(form.get("lastName") ?? ""),
        email: String(form.get("email") ?? ""),
        password,
        confirm_password: confirm,
      });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Couldn't create your account. Try again.");
      setPending(false);
    }
  }

  return (
    <section className="band account-band">
      <img className="account-photo" src="/lifestyle/navy-zip.jpg" alt="" />
      <form className="account-card" onSubmit={onSubmit}>
        <p className="eyebrow">New here</p>
        <h1>Create account</h1>
        <p className="lede">Takes a minute. The shop chat will remember you next time.</p>
        <div className="split-fields">
          <label>
            First name
            <input type="text" name="firstName" autoComplete="given-name" required />
          </label>
          <label>
            Last name
            <input type="text" name="lastName" autoComplete="family-name" required />
          </label>
        </div>
        <label>
          Email
          <input type="email" name="email" autoComplete="email" required />
        </label>
        <label>
          Password
          <input
            type="password"
            name="password"
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            name="confirmPassword"
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <button className="button" type="submit" disabled={pending}>
          {pending ? "Creating…" : "Create account"}
        </button>
        {error ? <p className="notice error">{error}</p> : null}
        <p className="lede">
          Been here before? <Link to="/login">Log in</Link>
        </p>
      </form>
    </section>
  );
}
