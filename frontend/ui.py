"""Shared UI layer for the Pinakes frontend.

Presentation only: nothing here calls the API. Pages keep their own api_get / api_post
helpers, their session_state keys and their endpoints.

Usage at the top of every page:

    import ui
    ui.setup("search", "Search", "Subtitle shown under the title.")

All design tokens live in assets/style.css. Every piece of text that comes from the API
goes through esc() before it is placed in HTML.
"""

from __future__ import annotations

import html
import re
import zlib
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"
TONES = ("lav", "pink", "orange", "blue")

# key, page file (relative to Home.py), label, Material icon
NAV = [
    ("home", "Home.py", "Home", "dashboard"),
    ("search", "pages/1_Search.py", "Search", "search"),
    ("browse", "pages/2_Browse.py", "Browse", "menu_book"),
    ("popular", "pages/3_Popular.py", "Most read", "local_fire_department"),
    ("graph", "pages/4_Graph.py", "Graph", "hub"),
    ("events", "pages/5_Events.py", "Events", "event_note"),
    ("monitoring", "pages/6_Monitoring.py", "Monitoring", "monitoring"),
]

_LOGO = (
    '<div class="pk-logo"><svg width="38" height="38" viewBox="0 0 40 40" aria-label="Pinakes">'
    '<rect x="3" y="3" width="21" height="21" rx="7" fill="#171526"/>'
    '<rect x="16" y="16" width="21" height="21" rx="7" fill="#F2A7D8"/>'
    '<rect x="16" y="16" width="8" height="8" fill="#BDB6F2"/></svg></div>'
)

_HERO_ART = (
    '<div class="pk-hero-art"><svg viewBox="0 0 320 190" fill="none" stroke="#171526" '
    'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="70" y="142" width="170" height="26" rx="7" fill="#F4B56F"/>'
    '<rect x="86" y="116" width="150" height="26" rx="7" fill="#F2A7D8"/>'
    '<rect x="62" y="90" width="162" height="26" rx="7" fill="#FFFFFF"/>'
    '<rect x="98" y="64" width="122" height="26" rx="7" fill="#AFC8F5"/>'
    '<path d="M96 155h16M104 129h16M80 103h16M116 77h16"/>'
    '<path d="M150 64c0-22 14-34 34-34" /><path d="M184 30l-8-7M184 30l-9 6"/>'
    '<path d="M232 118l34-34M266 84l22 26M266 84l6-42"/>'
    '<circle cx="232" cy="118" r="8" fill="#FFFFFF"/><circle cx="266" cy="84" r="10" fill="#F2A7D8"/>'
    '<circle cx="288" cy="110" r="7" fill="#F4B56F"/><circle cx="272" cy="42" r="7" fill="#FFFFFF"/>'
    '<path d="M40 60l4 9 9 4-9 4-4 9-4-9-9-4 9-4z" fill="#FFFFFF" stroke-width="2"/>'
    '<path d="M300 150l3 6 6 3-6 3-3 6-3-6-6-3 6-3z" fill="#FFFFFF" stroke-width="2"/>'
    "</svg></div>"
)


class Raw(str):
    """A string that is already HTML (skips escaping in table cells)."""


# --------------------------------------------------------------------------- helpers


def esc(value) -> str:
    """Escape for HTML. '$' is escaped too, or Streamlit's markdown reads it as LaTeX."""
    text = " ".join(("" if value is None else str(value)).split())  # no blank line can end an HTML block
    return html.escape(text).replace("$", "&#36;")


_NON_EM_TAG = re.compile(r"<(?!/?em>)[^>]*>")


def safe_highlight(fragment) -> str:
    """Search highlights come from the API already escaped, with <em> as the only tag.
    Strip any other tag anyway (defence in depth)."""
    text = " ".join(str(fragment).split())
    return _NON_EM_TAG.sub("", text).replace("$", "&#36;")


def tone_for(key) -> str:
    """Stable accent colour for a genre / id."""
    return TONES[zlib.crc32(str(key).encode("utf-8")) % len(TONES)]


def fmt_year(year) -> str:
    if year is None or year == "":
        return ""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return str(year)
    return f"{-y} BCE" if y < 0 else str(y)


def show(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_link(path: str, **kwargs) -> None:
    """st.page_link, but without crashing when the page cannot be resolved
    (this happens when a page is run on its own, e.g. in tests)."""
    try:
        st.page_link(path, **kwargs)
    except Exception:
        st.markdown(kwargs.get("label", path))


def box(key: str | None = None, **kwargs):
    """A container with a CSS hook (class st-key-pk_<key>) when Streamlit supports keys."""
    if key:
        try:
            return st.container(key=f"pk_{key}", **kwargs)
        except TypeError:  # Streamlit < 1.39
            pass
    return st.container(**kwargs)


def card():
    """White rounded surface."""
    return st.container(border=True)


# --------------------------------------------------------------------------- shell


def setup(active: str, title: str, subtitle: str = "", eyebrow: str = "Pinakes 2.0") -> None:
    """Page config, stylesheet, icon navigation and page header. Call first in every page."""
    st.set_page_config(
        page_title=f"{title} · Pinakes" if active != "home" else "Pinakes 2.0",
        page_icon="🏛️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    # The active item is also styled by key, because aria-current is not set in every Streamlit version.
    css += (
        f'.st-key-pk_nav_{active} a {{ background: var(--text) !important; color: #fff !important; '
        "box-shadow: 0 8px 18px rgba(23,21,38,.25); }"
    )
    show(f"<style>{css}</style>")

    with st.sidebar:
        show(_LOGO)
        for key, path, label, icon in NAV:
            with box(f"nav_{key}"):
                page_link(path, label=label, icon=f":material/{icon}:", help=label)

    page_header(title, subtitle, eyebrow)


def page_header(title: str, subtitle: str = "", eyebrow: str = "Pinakes 2.0") -> None:
    sub = f'<p class="pk-subtitle">{esc(subtitle)}</p>' if subtitle else ""
    show(
        f'<div class="pk-header"><div class="pk-eyebrow">{esc(eyebrow)}</div>'
        f'<h1 class="pk-title">{esc(title)}</h1>{sub}</div>'
    )


def section_title(title: str, hint: str = "") -> None:
    h = f'<span class="pk-section-hint">{esc(hint)}</span>' if hint else ""
    show(f'<div class="pk-section"><span class="pk-section-title">{esc(title)}</span>{h}</div>')


# --------------------------------------------------------------------------- components


def chip(text, tone: str = "") -> str:
    cls = f" pk-chip--{tone}" if tone else ""
    return f'<span class="pk-chip{cls}">{esc(text)}</span>'


def chips(items, tone: str = "") -> str:
    inner = "".join(chip(i, tone) for i in items if i not in (None, ""))
    return f'<div class="pk-chips">{inner}</div>' if inner else ""


def cover(title, genre: str = "", size: str = "wide") -> str:
    """Typographic book cover. The catalog has no cover images, so none is invented:
    colour comes from the genre, text from the title."""
    g = f'<span class="pk-cover-genre">{esc(genre)}</span>' if genre else "<span></span>"
    return (
        f'<div class="pk-cover pk-cover--{size} pk-tone-{tone_for(genre or title)}">'
        f'{g}<span class="pk-cover-title">{esc(title)}</span></div>'
    )


def stat_card(
    label: str,
    value=None,
    *,
    title: str | None = None,
    hint: str = "",
    tone: str = "lav",
    pct: float | None = None,
) -> str:
    v = f'<div class="pk-stat-value">{esc(value)}</div>' if value is not None else ""
    t = f'<div class="pk-stat-title">{esc(title)}</div>' if title else ""
    bar = ""
    if pct is not None:
        bar = f'<div class="pk-bar"><span style="width:{max(0, min(100, float(pct))):.0f}%"></span></div>'
    h = f'<div class="pk-stat-hint">{esc(hint)}</div>' if hint else ""
    return f'<div class="pk-stat pk-tone-{tone}"><div class="pk-stat-label">{esc(label)}</div>{v}{t}{bar}{h}</div>'


def rank_rows(items: list[dict], numbered: bool = True, start: int = 1) -> str:
    """items: {label, sub, value, ratio (0..1)} -> leaderboard rows."""
    rows = []
    for i, it in enumerate(items, start):
        n_cls = f" pk-rank-n--{i}" if i <= 3 else ""
        sub = f'<div class="pk-rank-sub">{esc(it.get("sub", ""))}</div>' if it.get("sub") else ""
        ratio = max(0.0, min(1.0, float(it.get("ratio", 0)))) * 100
        badge = f'<div class="pk-rank-n{n_cls}">{i}</div>' if numbered else ""
        rows.append(
            f'<div class="pk-rank-row">{badge}'
            f'<div class="pk-rank-main"><div class="pk-rank-label">{esc(it["label"])}</div>{sub}'
            f'<div class="pk-bar"><span style="width:{ratio:.0f}%"></span></div></div>'
            f'<div class="pk-rank-value">{esc(it["value"])}</div></div>'
        )
    return f'<div class="pk-rank">{"".join(rows)}</div>'


def table(headers: list[str], rows: list[list]) -> str:
    """Plain HTML table. Cells are escaped unless wrapped in Raw()."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c if isinstance(c, Raw) else esc(c)}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f'<div class="pk-table-wrap"><table class="pk-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def steps(links: list[tuple]) -> str:
    """links: (source name, target name, relation type) -> list of 'A -> B (type)' lines."""
    lines = "".join(
        f'<div class="pk-step"><b>{esc(s)}</b><span>→</span><b>{esc(t)}</b><em>{esc(k)}</em></div>'
        for s, t, k in links
    )
    return f'<div class="pk-steps">{lines}</div>'


def empty_state(title: str, text: str = "") -> None:
    t = f'<p class="pk-empty-text">{esc(text)}</p>' if text else ""
    show(f'<div class="pk-empty"><div class="pk-empty-mark"></div><div class="pk-empty-title">{esc(title)}</div>{t}</div>')


def status(ok: bool, message: str) -> str:
    cls = "ok" if ok else "bad"
    return f'<div class="pk-status pk-status--{cls}"><span class="pk-dot"></span><span>{esc(message)}</span></div>'


def hero(title: str, text: str, cta_page: str, cta_label: str, meta: list[str] | None = None) -> None:
    """Lavender banner with a call-to-action page link and an illustration."""
    with box("hero"):
        left, right = st.columns([1.35, 1], vertical_alignment="center")
        with left:
            show(
                f'<div class="pk-hero-title">{esc(title)}</div><p class="pk-hero-text">{esc(text)}</p>'
                + (chips(meta) if meta else "")
            )
            page_link(cta_page, label=cta_label)
        with right:
            show(_HERO_ART)


def work_detail(work: dict, notice: str | None = None) -> None:
    """Panel for an opened work (the document returned by GET /catalog/works/{id})."""
    authors = work.get("authors") or []
    names = ", ".join(a.get("name", "") for a in authors)
    meta = chips(
        [work.get("genre"), fmt_year(work.get("year")), work.get("language")],
        tone="lav",
    )
    parts = [
        '<div class="pk-detail"><div class="pk-detail-top">',
        cover(work.get("title", ""), work.get("genre", ""), "book"),
        f'<div><div class="pk-detail-title">{esc(work.get("title"))}</div>'
        f'<div class="pk-detail-authors">{esc(names)}</div>{meta}</div></div>',
    ]
    bios = [a for a in authors if a.get("bio")]
    if bios:
        parts.append('<div class="pk-detail-label">About the author</div>')
        parts += [f'<p class="pk-bio"><b>{esc(a.get("name"))}</b> — {esc(a["bio"])}</p>' for a in bios]
    if work.get("incipit"):
        parts.append('<div class="pk-detail-label">First line</div>')
        parts.append(f'<div class="pk-quote">{esc(work["incipit"])}</div>')
    if work.get("subjects"):
        parts.append('<div class="pk-detail-label">Subjects</div>')
        parts.append(chips(work["subjects"]))
    parts.append("</div>")
    with card():
        show("".join(parts))
        if notice:
            st.warning(notice)
