import { useEffect, useRef, useState, type FormEvent } from "react";
import { AuthError, fetchMessages, sendChat } from "../api";

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  tools: string[];
};

const SUGGESTIONS = [
  "Who teaches MGT 409?",
  "How many core courses are there?",
  "What are some good AI courses?",
];

type ChatPanelProps = {
  open: boolean;
  onClose: () => void;
  onSignOut: () => void;
};

export function ChatPanel({ open, onClose, onSignOut }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMessages()
      .then((saved) => {
        if (!cancelled) setMessages(saved);
      })
      .catch((error: unknown) => {
        if (error instanceof AuthError) onSignOut();
      });
    return () => {
      cancelled = true;
    };
  }, [onSignOut]);

  useEffect(() => {
    const node = transcriptRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, pending]);

  async function ask(text: string) {
    const message = text.trim();
    if (!message || pending) return;
    setDraft("");
    setMessages((current) => [
      ...current,
      { id: Date.now(), role: "user", text: message, tools: [] },
    ]);
    setPending(true);
    try {
      const result = await sendChat(message);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: result.reply || "No reply came back.",
          tools: result.tools_used,
        },
      ]);
    } catch (error) {
      if (error instanceof AuthError) {
        onSignOut();
        return;
      }
      const detail = error instanceof Error ? error.message : "The assistant failed.";
      setMessages((current) => [
        ...current,
        { id: Date.now() + 1, role: "assistant", text: detail, tools: [] },
      ]);
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  return (
    <>
      {open ? (
        <button type="button" className="backdrop" aria-label="Close assistant" onClick={onClose} />
      ) : null}
      <aside className={open ? "chat open" : "chat"} aria-label="Course assistant">
        <header className="chat-head">
          <div>
            <p className="eyebrow">
              <span className="live" />
              Catalog assistant
            </p>
            <h2>Ask about a course</h2>
          </div>
          <button type="button" className="close-chat" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="transcript" ref={transcriptRef}>
          {messages.length === 0 ? (
            <p className="chat-empty">
              Try a faculty name, a course number, or a topic. Answers cite the tools that ran.
            </p>
          ) : null}
          {messages.map((message) => (
            <div key={message.id} className={`bubble ${message.role}`}>
              <p>{message.text}</p>
              {message.role === "assistant" ? (
                <p className="tools">
                  {message.tools.length > 0
                    ? message.tools.map((tool, index) => (
                        <span key={`${tool}-${index}`} className="tool">
                          {tool}
                        </span>
                      ))
                    : <span className="tool muted-tool">no tools</span>}
                </p>
              ) : null}
            </div>
          ))}
          {pending ? (
            <div className="bubble assistant pending" role="status">
              <span className="spinner" aria-hidden="true" />
              <p>Looking through the catalog…</p>
            </div>
          ) : null}
        </div>
        <div className="suggestions">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={pending}
              onClick={() => void ask(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
        <form className="composer" onSubmit={onSubmit}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask a question"
            aria-label="Message the course assistant"
            disabled={pending}
          />
          <button type="submit" disabled={pending || draft.trim().length === 0}>
            Send
          </button>
        </form>
      </aside>
    </>
  );
}
