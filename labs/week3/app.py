"""Minimal Dash chat shell for a screen-aware PydanticAI agent.

Run:  python app.py
Open: immersive window via desktop.py (browser left, this chat on the right)

Build agent.py and prompts/prompt.md in class.
"""

from __future__ import annotations

import threading
import traceback
import uuid

from dash import Dash, Input, Output, State, clientside_callback, dcc, html, no_update

from agent import run_agent

app = Dash(__name__, title="Vegeta")

# Dash Interval can fire twice for one send; claim each pending id once.
_TURN_LOCK = threading.Lock()
_CLAIMED_TURNS: set[str] = set()

app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Oswald:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #070b16;
            --surface: #10182c;
            --armor: #162445;
            --border: #3d5c9a;
            --text: #f6f3e8;
            --muted: #9eb0d4;
            --gold: #ffd24a;
            --gold-2: #ffe9a0;
            --aura: #3d8bff;
            --lightning: #b9dcff;
            --radius: 12px;
        }
        * { box-sizing: border-box; }
        html, body { height: 100%; margin: 0; }
        body {
            font-family: Inter, -apple-system, "Segoe UI", Roboto, sans-serif;
            color: var(--text);
            background:
                radial-gradient(520px 280px at 50% -10%, rgba(255, 210, 74, 0.28), transparent 60%),
                radial-gradient(700px 420px at 100% 110%, rgba(61, 139, 255, 0.28), transparent 55%),
                radial-gradient(480px 320px at -10% 80%, rgba(80, 140, 255, 0.16), transparent 50%),
                var(--bg);
            -webkit-font-smoothing: antialiased;
        }
        body::before {
            content: "";
            position: fixed; inset: 0; pointer-events: none; z-index: 0;
            background:
                linear-gradient(115deg, transparent 42%, rgba(185, 220, 255, 0.16) 43%, transparent 44.2%),
                linear-gradient(72deg, transparent 62%, rgba(255, 210, 74, 0.12) 63%, transparent 64.4%);
        }
        .shell {
            position: relative; z-index: 1;
            height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 18px 16px 14px;
            gap: 12px;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
        .logo {
            width: 42px; height: 42px; border-radius: 12px; flex: 0 0 42px;
            display: grid; place-items: center;
            background: linear-gradient(160deg, var(--gold-2), var(--gold) 45%, #e09a12);
            color: #1a1404;
            font-family: Oswald, Inter, sans-serif;
            font-weight: 700; font-size: 22px; letter-spacing: 0.02em;
            box-shadow: 0 0 0 2px rgba(61, 139, 255, 0.85), 0 0 22px rgba(61, 139, 255, 0.65);
        }
        .brand h1 {
            margin: 0; font-family: Oswald, Inter, sans-serif;
            font-size: 22px; font-weight: 700; letter-spacing: 0.08em; color: var(--gold);
        }
        .brand p { margin: 2px 0 0; font-size: 12px; color: var(--lightning); }
        .status {
            display: flex; align-items: center; gap: 8px;
            max-width: 46%;
            padding: 6px 10px;
            border: 1px solid var(--border);
            border-radius: 999px;
            background: rgba(16, 24, 44, 0.9);
            color: var(--gold-2);
            font-size: 11.5px;
            line-height: 1.3;
        }
        .status .dot {
            width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px;
            background: var(--lightning);
            box-shadow: 0 0 0 0 rgba(185, 220, 255, 0.7);
            animation: ping 1.4s infinite;
        }
        @keyframes ping {
            70% { box-shadow: 0 0 0 7px rgba(61, 139, 255, 0); }
            100% { box-shadow: 0 0 0 0 rgba(61, 139, 255, 0); }
        }
        .chat {
            flex: 1; min-height: 0; overflow-y: auto;
            padding: 16px 12px 8px;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background:
                linear-gradient(180deg, rgba(22, 36, 69, 0.92), rgba(10, 16, 32, 0.94));
            box-shadow: 0 0 0 1px rgba(255, 210, 74, 0.25), 0 0 28px rgba(61, 139, 255, 0.28);
        }
        .chat::-webkit-scrollbar { width: 8px; }
        .chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 8px; }
        .row { display: flex; gap: 10px; margin: 4px 0 12px; }
        .row.user { flex-direction: row-reverse; }
        .avatar {
            flex: 0 0 30px; width: 30px; height: 30px; border-radius: 10px;
            display: grid; place-items: center; font-size: 12px; font-weight: 700; margin-top: 2px;
        }
        .avatar.bot {
            background: linear-gradient(160deg, var(--gold-2), var(--gold));
            color: #1a1404;
            box-shadow: 0 0 12px rgba(61, 139, 255, 0.8);
        }
        .avatar.user {
            background: var(--armor);
            border: 1px solid var(--border);
            color: var(--lightning);
        }
        .bubble {
            max-width: 82%;
            padding: 10px 14px;
            border-radius: 12px;
            border: 1px solid var(--border);
            font-size: 14.5px;
            line-height: 1.55;
        }
        .row.bot .bubble {
            background: linear-gradient(180deg, #1a2c58, #121c36);
            border-color: rgba(255, 210, 74, 0.45);
            border-top-left-radius: 4px;
            box-shadow: inset 3px 0 0 var(--aura);
        }
        .row.user .bubble {
            background: linear-gradient(135deg, rgba(255, 210, 74, 0.2), rgba(61, 139, 255, 0.16));
            border-color: rgba(255, 210, 74, 0.4);
            border-top-right-radius: 4px;
        }
        .bubble p { margin: 0 0 8px; }
        .bubble p:last-child { margin-bottom: 0; }
        .bubble a { color: var(--gold); }
        .bubble code {
            font-size: 12.5px;
            background: rgba(0, 0, 0, 0.35);
            padding: 1px 5px;
            border-radius: 6px;
        }
        .bubble pre {
            overflow-x: auto;
            background: #0b0b0f;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px;
        }
        .tools {
            display: flex; flex-wrap: wrap; gap: 6px;
            margin: -4px 0 10px 40px;
            padding: 0; list-style: none;
        }
        .row.user + .tools { margin-left: 0; margin-right: 40px; justify-content: flex-end; }
        .tools li {
            font-size: 11.5px;
            color: var(--gold);
            border: 1px solid rgba(255, 210, 74, 0.45);
            background: rgba(61, 139, 255, 0.14);
            border-radius: 999px;
            padding: 3px 10px;
        }
        .pending {
            display: inline-flex; align-items: center; gap: 8px;
            color: var(--muted); padding: 8px 4px 12px;
        }
        .dots { display: inline-flex; gap: 4px; }
        .dots span {
            width: 6px; height: 6px; border-radius: 50%;
            background: var(--gold);
            animation: bounce 1.2s infinite ease-in-out;
        }
        .dots span:nth-child(2) { animation-delay: .15s; }
        .dots span:nth-child(3) { animation-delay: .3s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: translateY(0); opacity: .35; }
            40% { transform: translateY(-4px); opacity: 1; }
        }
        .composer-row {
            display: flex; align-items: flex-end; gap: 10px;
            padding: 8px 8px 8px 14px;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: rgba(16, 24, 44, 0.95);
        }
        .composer-row:focus-within {
            border-color: var(--gold);
            box-shadow: 0 0 0 3px rgba(61, 139, 255, 0.35);
        }
        #composer {
            flex: 1; width: 100%; resize: none; border: none; outline: none;
            background: transparent; color: var(--text);
            font: inherit; font-size: 14.5px; line-height: 1.45;
            min-height: 44px; max-height: 140px; padding: 8px 0;
        }
        #composer::placeholder { color: var(--muted); }
        #send-button {
            border: none; cursor: pointer; color: #1a1404;
            background: linear-gradient(160deg, var(--gold-2), var(--gold));
            box-shadow: 0 0 16px rgba(61, 139, 255, 0.45);
            border-radius: 12px; padding: 0 16px; height: 40px;
            font: inherit; font-weight: 600; font-size: 14px;
        }
        #send-button:hover { filter: brightness(1.08); }
        .hint { margin: 0; text-align: center; font-size: 11.5px; color: var(--muted); }
        @media (max-width: 640px) {
            .status { display: none; }
            .bubble { max-width: 90%; }
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

app.layout = html.Div(
    className="shell",
    children=[
        html.Div(
            className="topbar",
            children=[
                html.Div(
                    className="brand",
                    children=[
                        html.Div("V", className="logo"),
                        html.Div(
                            [
                                html.H1("VEGETA"),
                                html.P("Super Saiyan 2 · Prince of all Saiyans"),
                            ]
                        ),
                    ],
                ),
                html.Div(
                    [html.Span(className="dot"), html.Span(id="screen-status", children="Scouter idle.")],
                    className="status",
                ),
            ],
        ),
        dcc.Store(
            id="chat-history",
            data=[{"role": "assistant", "content": "Hmph. I am Vegeta, Prince of all Saiyans. Ask about the page on the left, if you think you can keep up."}],
        ),
        dcc.Store(id="last-shot", data=None),
        dcc.Store(id="pending-request", data=None),
        dcc.Store(id="scroll-sink", data=None),
        dcc.Interval(id="agent-poll", interval=250, n_intervals=0, max_intervals=0, disabled=True),
        html.Div(id="chat-window", className="chat"),
        html.Div(
            className="composer-row",
            children=[
                dcc.Textarea(id="composer", placeholder="Speak, earthling…"),
                html.Button("Fire", id="send-button", n_clicks=0),
            ],
        ),
        html.P("Enter to fire · Shift+Enter for a new line", className="hint"),
    ],
)


def render_messages(history: list | None, pending: dict | None) -> list:
    blocks = []
    for msg in history or []:
        is_bot = msg["role"] == "assistant"
        blocks.append(
            html.Div(
                className=f"row {'bot' if is_bot else 'user'}",
                children=[
                    html.Div("V" if is_bot else "Y", className=f"avatar {'bot' if is_bot else 'user'}"),
                    html.Div(
                        dcc.Markdown(msg["content"], link_target="_blank"),
                        className="bubble",
                    ),
                ],
            )
        )
        tools = msg.get("tool_events") or []
        if tools:
            blocks.append(
                html.Ul(
                    [html.Li(f"Used: {t.get('name', '?')}") for t in tools],
                    className="tools",
                )
            )
    if pending:
        blocks.append(
            html.Div(
                [
                    html.Span("Vegeta", style={"fontWeight": "600", "color": "#ffd24a"}),
                    html.Span(className="dots", children=[html.Span(), html.Span(), html.Span()]),
                ],
                className="pending",
                role="status",
                **{"aria-live": "polite"},
            )
        )
    return blocks


@app.callback(
    Output("chat-window", "children"),
    Input("chat-history", "data"),
    Input("pending-request", "data"),
)
def update_chat(history, pending):
    return render_messages(history, pending)


@app.callback(Output("screen-status", "children"), Input("last-shot", "data"))
def update_screen_status(last_shot):
    if not last_shot:
        return "Scouter idle."
    when = last_shot.get("captured_at", "?")
    region = last_shot.get("region", "window")
    return f"Scouter: {when} · {region}"


@app.callback(
    Output("chat-history", "data", allow_duplicate=True),
    Output("pending-request", "data"),
    Output("composer", "value"),
    Output("agent-poll", "disabled"),
    Output("agent-poll", "n_intervals"),
    Output("agent-poll", "max_intervals"),
    Input("send-button", "n_clicks"),
    State("composer", "value"),
    State("chat-history", "data"),
    State("pending-request", "data"),
    prevent_initial_call=True,
)
def submit_message(_send, text, history, pending):
    if pending or not text or not text.strip():
        return no_update, no_update, no_update, no_update, no_update, no_update
    message = text.strip()
    updated = [*(history or []), {"role": "user", "content": message}]
    return updated, {"text": message, "id": str(uuid.uuid4())}, "", False, 0, 1


@app.callback(
    Output("chat-history", "data", allow_duplicate=True),
    Output("pending-request", "data", allow_duplicate=True),
    Output("last-shot", "data"),
    Output("agent-poll", "disabled", allow_duplicate=True),
    Input("agent-poll", "n_intervals"),
    State("pending-request", "data"),
    State("chat-history", "data"),
    State("last-shot", "data"),
    prevent_initial_call=True,
)
def complete_agent_turn(n_intervals, pending, history, last_shot):
    if not pending or not n_intervals:
        return no_update, no_update, no_update, True if not pending else no_update

    turn_id = pending.get("id") or str(uuid.uuid4())
    with _TURN_LOCK:
        if turn_id in _CLAIMED_TURNS:
            return no_update, no_update, no_update, True
        _CLAIMED_TURNS.add(turn_id)

    try:
        print(f"\nagent turn: {pending['text']!r}", flush=True)
        result = run_agent(pending["text"])
        tools = result.get("tool_events", [])
        if tools:
            print("tools this turn: " + ", ".join(t.get("name", "?") for t in tools), flush=True)
        reply = {"role": "assistant", "content": result["text"], "tool_events": tools}
        new_shot = result.get("last_shot") or last_shot
    except Exception:
        traceback.print_exc()
        reply = {
            "role": "assistant",
            "content": "Something went wrong. Check PORTKEY_API_KEY in your .env and try again.",
        }
        new_shot = last_shot
    finally:
        with _TURN_LOCK:
            _CLAIMED_TURNS.discard(turn_id)

    return [*(history or []), reply], None, new_shot, True


clientside_callback(
    """
    function(n) {
        const el = document.getElementById('composer');
        if (!el || el.dataset.bound) return window.dash_clientside.no_update;
        el.dataset.bound = '1';
        el.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                document.getElementById('send-button').click();
            }
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("send-button", "n_clicks"),
    Input("send-button", "n_clicks"),
)

clientside_callback(
    """
    function(children, pending) {
        const el = document.getElementById('chat-window');
        if (!el) return window.dash_clientside.no_update;
        const pin = () => { el.scrollTop = el.scrollHeight; };
        pin();
        requestAnimationFrame(pin);
        setTimeout(pin, 50);
        return window.dash_clientside.no_update;
    }
    """,
    Output("scroll-sink", "data"),
    Input("chat-window", "children"),
    Input("pending-request", "data"),
)


if __name__ == "__main__":
    from desktop import run_desktop

    run_desktop()
