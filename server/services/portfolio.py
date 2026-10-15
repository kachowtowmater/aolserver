"""Stock Portfolios (AOL 4.0 menu, keyword PORTFOLIO): your symbols, live 2026 prices.

zH = add/update a holding (symbol, shares; 0 shares removes it).
"""
from datetime import datetime

from . import content, screens, store
from .util import fmt_time, alert, name_of, request, run_bg


def show(link, rid=None):
    rows_in = store.holdings(name_of(link))

    def work():
        return [(h["symbol"], h["shares"], content.quote(h["symbol"])) for h in rows_in]

    def done(rows):
        lines, total, day = [], 0.0, 0.0
        for sym, shares, q in rows:
            if not q:
                lines.append(f"{sym}\t{shares:g} sh\t(no quote)")
                continue
            value = q["price"] * shares
            total += value
            day += q["change"] * shares
            sign = "+" if q["change"] >= 0 else ""
            lines.append(f"{sym}\t{shares:g} sh\t${q['price']:,.2f}\t{sign}{q['pct']:.2f}%\t${value:,.2f}")
        head = (f"Portfolio value ${total:,.2f}   Today {'+' if day >= 0 else ''}{day:,.2f}   "
                f"{fmt_time(datetime.now(), '%-I:%M %p %b %-d')}") if rows else "Your portfolio is empty."
        text = head + "\r\r" + ("\r".join(lines) if lines else "Click Add Stock to track a symbol.") + \
            "\r\rQuotes delayed.  Not investment advice -- it's 1997 in here."
        link.send_stream(screens.text_window(f"{name_of(link)}'s Portfolio", text, response_id=rid, width=60,
                                             height=12, window="portfolio"))
        link.send_stream(screens.form_window("Add Stock", "Symbol and number of shares (0 removes the symbol).",
                                             [("Symbol:", 10, ""), ("Shares:", 10, "")], "Add Stock", "zH",
                                             window="portfolio_add"))
    run_bg(work, done)


def add(link, stream_id, body):
    sym, shares = (request(body)["texts"] + ["", ""])[:2]
    sym = sym.strip().upper()
    try:
        n = float(shares.strip() or "0")
    except ValueError:
        return alert(link, "Shares must be a number.")
    if not sym:
        return
    if n and not content.quote(sym):
        return alert(link, f"No quote found for {sym}.")
    store.set_holding(name_of(link), sym, n)
    show(link)


TOKENS = {b"zH": add}
AREAS = {"portfolio": show, "portfolios": show, "stock portfolios": show, "my stocks": show}
