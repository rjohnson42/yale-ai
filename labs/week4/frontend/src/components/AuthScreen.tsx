import { useState, type FormEvent } from "react";
import { login, register } from "../api";
import type { User } from "../api";

type AuthScreenProps = {
  onSignedIn: (user: User) => void;
};

export function AuthScreen({ onSignedIn }: AuthScreenProps) {
  const [mode, setMode] = useState<"signin" | "create">("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setError("");
    setPending(true);
    try {
      const user =
        mode === "create"
          ? await register(email, password, name)
          : await login(email, password);
      onSignedIn(user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="gate">
      <div className="accent-bar" />
      <header className="topbar">
        <a className="brand" href="https://som.yale.edu/" target="_blank" rel="noreferrer">
          <img src="/yale-som-logo.svg" alt="Yale School of Management" />
        </a>
      </header>
      <main className="gate-main">
        <form className="auth-card" onSubmit={(event) => void onSubmit(event)}>
          <p className="eyebrow">Yale SOM</p>
          <h1>{mode === "create" ? "Create an account" : "Sign in"}</h1>
          <p className="auth-lead">
            The catalog and your questions stay with this account.
          </p>
          <div className="mode-switch" role="tablist" aria-label="Account">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "signin"}
              className={mode === "signin" ? "on" : ""}
              onClick={() => {
                setMode("signin");
                setError("");
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "create"}
              className={mode === "create" ? "on" : ""}
              onClick={() => {
                setMode("create");
                setError("");
              }}
            >
              Create account
            </button>
          </div>
          {mode === "create" ? (
            <label className="field">
              <span>Name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                placeholder="Your name"
              />
            </label>
          ) : null}
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              placeholder="you@yale.edu"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "create" ? "new-password" : "current-password"}
              required
              minLength={mode === "create" ? 8 : 1}
              placeholder={mode === "create" ? "At least 8 characters" : "Password"}
            />
          </label>
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="submit" type="submit" disabled={pending}>
            {pending ? "Please wait…" : mode === "create" ? "Create account" : "Sign in"}
          </button>
        </form>
      </main>
    </div>
  );
}
