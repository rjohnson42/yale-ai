"""Dash chat UI for the Lecture 3 stock research chatbot (tools + LLM).

Run:  python3 app.py
Open: http://127.0.0.1:8050

Model + tools live in chatbot.py. get_reply(user_text, history) returns
{"text": "...", "tool_events": [{"name": "...", "status": "completed"}, ...]}.
Theme: Yale Blue (#00356B) on a deep navy background.
"""

from __future__ import annotations

import traceback

from dash import ALL, Dash, Input, Output, State, clientside_callback, ctx, dcc, html, no_update

from chatbot import get_reply

SUGGESTIONS = [
    "What's NVDA trading at and how has it done over 3 months?",
    "Compare Apple and Microsoft on P/E and dividend yield",
    "Any notable news on Tesla this week?",
    "How has the S&P 500 (SPY) performed year to date?",
]

app = Dash(__name__, title="Stock Research · Yale AI")

app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --yale: #00356B;
            --yale-2: #286DC0;
            --yale-3: #63AAFF;
            --yale-glow: rgba(99, 170, 255, 0.35);
            --bg-0: #050B16;
            --bg-1: #0A1628;
            --surface: rgba(255, 255, 255, 0.045);
            --surface-2: rgba(255, 255, 255, 0.08);
            --border: rgba(255, 255, 255, 0.10);
            --text: #EEF3FB;
            --muted: #8FA3C2;
            --ok: #3DD68C;
            --err: #FF6B6B;
            --radius: 18px;
        }
        * { box-sizing: border-box; }
        html, body { height: 100%; margin: 0; }
        body {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: var(--text);
            background:
                radial-gradient(1200px 600px at 10% -10%, rgba(40, 109, 192, 0.35), transparent 60%),
                radial-gradient(900px 500px at 100% 110%, rgba(0, 53, 107, 0.55), transparent 60%),
                linear-gradient(180deg, var(--bg-1), var(--bg-0));
            background-attachment: fixed;
            -webkit-font-smoothing: antialiased;
        }
        /* subtle animated grid */
        body::before {
            content: "";
            position: fixed; inset: 0; pointer-events: none; z-index: 0;
            background-image:
                linear-gradient(rgba(99,170,255,0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(99,170,255,0.05) 1px, transparent 1px);
            background-size: 48px 48px;
            mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
        }

        .shell {
            position: relative; z-index: 1;
            max-width: 900px; height: 100vh; margin: 0 auto;
            display: flex; flex-direction: column; padding: 20px 20px 16px;
        }

        /* ---------- header ---------- */
        .topbar {
            display: flex; align-items: center; justify-content: space-between;
            padding: 6px 4px 18px;
        }
        .brand { display: flex; align-items: center; gap: 14px; }
        .logo {
            width: 44px; height: 44px; border-radius: 14px;
            display: grid; place-items: center;
            background: linear-gradient(135deg, var(--yale-2), var(--yale));
            box-shadow: 0 8px 24px -6px var(--yale-glow), inset 0 1px 0 rgba(255,255,255,0.25);
            font-weight: 700; font-size: 20px; letter-spacing: -0.02em; color: white;
        }
        .brand h1 { margin: 0; font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }
        .brand p { margin: 2px 0 0; font-size: 12.5px; color: var(--muted); }
        .status {
            display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted);
            padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px;
            background: var(--surface); font-family: "JetBrains Mono", monospace;
        }
        .status .dot {
            width: 7px; height: 7px; border-radius: 50%; background: var(--ok);
            box-shadow: 0 0 0 0 rgba(61,214,140,0.6); animation: ping 2s infinite;
        }
        @keyframes ping { 70% { box-shadow: 0 0 0 7px rgba(61,214,140,0); } 100% { box-shadow: 0 0 0 0 rgba(61,214,140,0); } }

        /* ---------- chat window ---------- */
        .chat {
            flex: 1; min-height: 0; overflow-y: auto; padding: 18px 14px 8px;
            border: 1px solid var(--border); border-radius: var(--radius);
            background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
            backdrop-filter: blur(14px);
            box-shadow: 0 30px 80px -40px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.06);
            scroll-behavior: smooth;
        }
        .chat::-webkit-scrollbar { width: 8px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 8px; }

        .row { display: flex; gap: 12px; margin: 6px 0 14px; animation: rise .35s cubic-bezier(.2,.8,.2,1) both; }
        .row.user { flex-direction: row-reverse; }
        @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

        .avatar {
            flex: 0 0 34px; width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center;
            font-size: 13px; font-weight: 700; margin-top: 2px;
        }
        .avatar.bot { background: linear-gradient(135deg, var(--yale-2), var(--yale)); color: white; box-shadow: 0 6px 18px -8px var(--yale-glow); }
        .avatar.user { background: var(--surface-2); border: 1px solid var(--border); color: var(--yale-3); }

        .bubble {
            max-width: 78%; padding: 12px 16px; border-radius: 16px; font-size: 14.5px; line-height: 1.55;
            border: 1px solid var(--border);
        }
        .row.bot .bubble { background: var(--surface); border-top-left-radius: 6px; }
        .row.user .bubble {
            background: linear-gradient(135deg, var(--yale-2), var(--yale));
            border-color: rgba(99,170,255,0.35); border-top-right-radius: 6px;
            box-shadow: 0 10px 30px -14px var(--yale-glow);
        }
        .bubble p { margin: 0 0 8px; } .bubble p:last-child { margin-bottom: 0; }
        .bubble h1, .bubble h2, .bubble h3 { margin: 4px 0 8px; font-size: 15px; font-weight: 600; color: var(--yale-3); }
        .bubble ul, .bubble ol { margin: 4px 0 8px; padding-left: 20px; }
        .bubble li { margin: 3px 0; }
        .bubble a { color: var(--yale-3); }
        .bubble code { font-family: "JetBrains Mono", monospace; font-size: 12.5px; background: rgba(0,0,0,0.35); padding: 2px 6px; border-radius: 6px; }
        .bubble table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 13.5px; }
        .bubble th, .bubble td { padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: left; }
        .bubble th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
        .bubble tr:last-child td { border-bottom: none; }
        .bubble strong { color: #fff; }

        .tools { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0 46px; }
        .chip {
            display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; padding: 4px 10px;
            border-radius: 999px; border: 1px solid rgba(99,170,255,0.3); color: var(--yale-3);
            background: rgba(40,109,192,0.12); font-family: "JetBrains Mono", monospace;
        }
        .chip.error { color: var(--err); border-color: rgba(255,107,107,0.35); background: rgba(255,107,107,0.10); }
        .chip .tick { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

        .thinking { display: inline-flex; gap: 5px; align-items: center; padding: 14px 16px; }
        .thinking span { width: 7px; height: 7px; border-radius: 50%; background: var(--yale-3); animation: bounce 1.2s infinite ease-in-out; }
        .thinking span:nth-child(2) { animation-delay: .15s; } .thinking span:nth-child(3) { animation-delay: .3s; }
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); opacity: .35; } 40% { transform: translateY(-5px); opacity: 1; } }

        /* ---------- suggestions ---------- */
        .suggest { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 2px 4px; }
        .suggest button {
            font: inherit; font-size: 12.5px; color: var(--text); cursor: pointer;
            padding: 8px 14px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface);
            transition: all .15s ease;
        }
        .suggest button:hover { border-color: rgba(99,170,255,0.5); background: rgba(40,109,192,0.18); transform: translateY(-1px); }

        /* ---------- composer ---------- */
        .composer {
            display: flex; align-items: flex-end; gap: 10px; margin-top: 10px; padding: 8px 8px 8px 16px;
            border: 1px solid var(--border); border-radius: 20px; background: var(--surface);
            backdrop-filter: blur(14px); transition: border-color .2s, box-shadow .2s;
        }
        .composer:focus-within { border-color: rgba(99,170,255,0.6); box-shadow: 0 0 0 4px rgba(99,170,255,0.12); }
        .composer textarea {
            flex: 1; resize: none; border: none; outline: none; background: transparent; color: var(--text);
            font: inherit; font-size: 14.5px; line-height: 1.5; padding: 8px 0; max-height: 160px;
        }
        .composer textarea::placeholder { color: var(--muted); }
        .send {
            width: 42px; height: 42px; border-radius: 14px; border: none; cursor: pointer; display: grid; place-items: center;
            background: linear-gradient(135deg, var(--yale-2), var(--yale)); color: white;
            box-shadow: 0 8px 20px -8px var(--yale-glow); transition: transform .12s, filter .15s;
        }
        .send:hover { filter: brightness(1.12); transform: translateY(-1px); }
        .send:active { transform: translateY(0) scale(.97); }
        .hint { text-align: center; font-size: 11.5px; color: var(--muted); margin: 8px 0 0; }
        .hint kbd { font-family: "JetBrains Mono", monospace; font-size: 10.5px; padding: 1px 6px; border: 1px solid var(--border); border-radius: 5px; background: var(--surface); }

        @media (max-width: 640px) { .bubble { max-width: 90%; } .status { display: none; } .tools { margin-left: 0; } }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

SEND_ICON = html.Span("↑", style={"fontSize": "20px", "fontWeight": "700", "lineHeight": "1"})

app.layout = html.Div(
    className="shell",
    children=[
        html.Div(
            className="topbar",
            children=[
                html.Div(
                    className="brand",
                    children=[
                        html.Div("Y", className="logo"),
                        html.Div(
                            [
                                html.H1("Stock Research"),
                                html.P("gpt-5.6-luna · Yahoo Finance · live news"),
                            ]
                        ),
                    ],
                ),
                html.Div([html.Span(className="dot"), html.Span("tools online")], className="status"),
            ],
        ),
        dcc.Store(
            id="chat-history",
            data=[
                {
                    "role": "assistant",
                    "content": "Hi. Ask me about any stock: price, valuation, performance, or news. Every number comes straight from Yahoo Finance or a cited source, never from memory.",
                }
            ],
        ),
        dcc.Store(id="pending-request", data=None),
        dcc.Store(id="scroll-sink"),
        dcc.Interval(id="agent-poll", interval=250, n_intervals=0, max_intervals=0, disabled=True),
        html.Div(id="chat-window", className="chat"),
        html.Div(
            id="suggestions",
            className="suggest",
            children=[
                html.Button(s, id={"type": "suggest", "index": i}, n_clicks=0) for i, s in enumerate(SUGGESTIONS)
            ],
        ),
        html.Div(
            className="composer",
            children=[
                dcc.Textarea(id="composer", placeholder="Ask about a ticker, a company, or the market…", rows=1),
                html.Button(SEND_ICON, id="send-button", n_clicks=0, className="send", title="Send"),
            ],
        ),
        html.P(
            [html.Kbd("Enter"), " to send · ", html.Kbd("Shift"), " + ", html.Kbd("Enter"), " for a new line"],
            className="hint",
        ),
    ],
)


def render_messages(history, pending):
    blocks = []
    for msg in history or []:
        is_bot = msg["role"] == "assistant"
        blocks.append(
            html.Div(
                className=f"row {'bot' if is_bot else 'user'}",
                children=[
                    html.Div("Y" if is_bot else "You"[:1], className=f"avatar {'bot' if is_bot else 'user'}"),
                    html.Div(dcc.Markdown(msg["content"], link_target="_blank"), className="bubble"),
                ],
            )
        )
        tools = msg.get("tool_events") or []
        if tools:
            blocks.append(
                html.Div(
                    className="tools",
                    children=[
                        html.Span(
                            [html.Span(className="tick"), t.get("name", "?")],
                            className=f"chip {'error' if t.get('status') == 'error' else ''}",
                        )
                        for t in tools
                    ],
                )
            )
    if pending:
        blocks.append(
            html.Div(
                className="row bot",
                role="status",
                **{"aria-live": "polite"},
                children=[
                    html.Div("Y", className="avatar bot"),
                    html.Div([html.Span(), html.Span(), html.Span()], className="bubble thinking"),
                ],
            )
        )
    return blocks


@app.callback(Output("chat-window", "children"), Input("chat-history", "data"), Input("pending-request", "data"))
def update_chat(history, pending):
    return render_messages(history, pending)


@app.callback(
    Output("chat-history", "data", allow_duplicate=True),
    Output("pending-request", "data"),
    Output("composer", "value"),
    Output("agent-poll", "disabled"),
    Output("agent-poll", "n_intervals"),
    Output("agent-poll", "max_intervals"),
    Output("suggestions", "style"),
    Input("send-button", "n_clicks"),
    Input({"type": "suggest", "index": ALL}, "n_clicks"),
    State("composer", "value"),
    State("chat-history", "data"),
    State("pending-request", "data"),
    prevent_initial_call=True,
)
def submit_message(_, __, text, history, pending):
    trigger = ctx.triggered_id
    if isinstance(trigger, dict) and trigger.get("type") == "suggest":
        text = SUGGESTIONS[trigger["index"]]
    if pending or not text or not text.strip():
        return (no_update,) * 7
    text = text.strip()
    updated = [*(history or []), {"role": "user", "content": text}]
    return updated, {"text": text}, "", False, 0, 1, {"display": "none"}


@app.callback(
    Output("chat-history", "data", allow_duplicate=True),
    Output("pending-request", "data", allow_duplicate=True),
    Output("agent-poll", "disabled", allow_duplicate=True),
    Input("agent-poll", "n_intervals"),
    State("pending-request", "data"),
    State("chat-history", "data"),
    prevent_initial_call=True,
)
def complete_chat_turn(_, pending, history):
    if not pending:
        return no_update, no_update, True
    try:
        print(f"\nchat turn: {pending['text']!r}", flush=True)
        result = get_reply(pending["text"], (history or [])[:-1])
        tools = result.get("tool_events", []) if isinstance(result, dict) else []
        text = result["text"] if isinstance(result, dict) else str(result)
        print("tools this turn: " + (", ".join(t.get("name", "?") for t in tools) or "(none)"), flush=True)
        reply = {"role": "assistant", "content": text, "tool_events": tools}
    except Exception as exc:
        traceback.print_exc()
        detail = str(exc).split("\n")[0][:200]
        reply = {
            "role": "assistant",
            "content": f"Something went wrong. Check .env / Portkey and try again.\n\n`{detail}`",
        }
    return [*(history or []), reply], None, True


# Enter sends; Shift+Enter keeps a newline. Also auto-grow the textarea.
clientside_callback(
    """
    function(n) {
        const el = document.getElementById('composer');
        if (!el || el.dataset.bound) return window.dash_clientside.no_update;
        el.dataset.bound = '1';
        const grow = () => { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; };
        el.addEventListener('input', grow);
        el.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                document.getElementById('send-button').click();
                setTimeout(grow, 0);
            }
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("send-button", "n_clicks"),
    Input("send-button", "n_clicks"),
)

# Keep the newest message in view.
clientside_callback(
    """
    function(children) {
        const el = document.getElementById('chat-window');
        if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
        return null;
    }
    """,
    Output("scroll-sink", "data"),
    Input("chat-window", "children"),
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False, use_reloader=False)
