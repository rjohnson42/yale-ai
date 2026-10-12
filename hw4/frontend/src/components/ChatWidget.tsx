import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { fetchMessages, sendChat, type SavedChatMessage } from "../api.ts";
import { useAuth } from "../auth.tsx";
import { formatPrice } from "../data/catalogue.ts";

function plainChat(text: string): string {
  return text
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/^[ \t]*[-*][ \t]+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function viewingProduct(pathname: string): string {
  const match = /^\/products\/([^/]+)$/.exec(pathname);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return "";
  }
}

export function ChatWidget() {
  const { user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<SavedChatMessage[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const userId = user?.id ?? null;

  useEffect(() => {
    setMessages([]);
  }, [userId]);

  useEffect(() => {
    if (!user || !open) return;
    let cancelled = false;
    fetchMessages()
      .then((saved) => {
        if (!cancelled) setMessages(saved);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Couldn't load your past chats.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, user]);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages, pending, open]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending) return;
    const optimistic: SavedChatMessage = {
      id: Date.now(),
      role: "user",
      content: text,
      products: [],
      created_at: "",
    };
    setMessages((current) => [...current, optimistic]);
    setDraft("");
    setPending(true);
    setError("");
    try {
      const reply = await sendChat(text, {
        pagePath: location.pathname,
        productId: viewingProduct(location.pathname),
        history: user
          ? []
          : messages.slice(-12).map((item) => ({ role: item.role, content: item.content })),
      });
      setMessages((current) => [...current.filter((item) => item.id !== optimistic.id), optimistic, reply]);
    } catch (reason: unknown) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setDraft(text);
      setError(reason instanceof Error ? reason.message : "The chat hit a snag. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="chat-dock">
      {open ? (
        <section className="chat-panel" aria-label="Ask the shop">
          <header className="chat-head">
            <div>
              <p className="eyebrow">Campus Customs</p>
              <h2>Ask the shop</h2>
            </div>
            <button type="button" className="text-button" onClick={() => setOpen(false)}>
              Close
            </button>
          </header>
          <div className="chat-log" ref={logRef}>
            {messages.length === 0 ? (
              <p className="chat-bubble">
                Looking for something? Name a college, a sport, or a size and I'll check the shelf.
              </p>
            ) : null}
            {messages.map((message) => (
              <div key={message.id} className={message.role === "user" ? "chat-turn mine" : "chat-turn"}>
                <p className={message.role === "user" ? "chat-bubble mine" : "chat-bubble"}>
                  {message.role === "assistant" ? plainChat(message.content) : message.content}
                </p>
                {message.products.length > 0 ? (
                  <div className="chat-cards">
                    {message.products.map((product) => (
                      <Link
                        key={product.product_id}
                        className="chat-card"
                        to={`/products/${product.product_id}`}
                      >
                        <img src={`/media/${product.image_file_path}`} alt="" />
                        <span>
                          <strong>{product.name}</strong>
                          <span>
                            {formatPrice(product.price)}
                            {product.in_stock_sizes.length > 0
                              ? ` · ${product.in_stock_sizes.join(", ")}`
                              : " · Sold out"}
                          </span>
                        </span>
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            {pending ? <p className="chat-bubble">Checking the shelf…</p> : null}
            {error ? <p className="notice error">{error}</p> : null}
            {!user ? (
              <p className="lede">
                <Link to="/login">Log in</Link> to save this chat.
              </p>
            ) : null}
          </div>
          <form className="chat-form" onSubmit={onSubmit}>
            <label className="sr-only" htmlFor="chat-draft">
              Message
            </label>
            <input
              id="chat-draft"
              type="text"
              value={draft}
              placeholder="Pierson crewneck in a medium?"
              disabled={pending}
              onChange={(event) => setDraft(event.target.value)}
            />
            <button type="submit" className="button" disabled={pending || !draft.trim()}>
              Send
            </button>
          </form>
        </section>
      ) : null}
      <button
        type="button"
        className="chat-launcher"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? "Close chat" : "Ask the shop"}
      </button>
    </div>
  );
}
