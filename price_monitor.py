#!/usr/bin/env python3
"""arzan.kz баға бақылаушысы: бағаны оқиды, тарихқа жазады, өзгерсе e-mail жібереді."""
import csv, json, os, re, smtplib, urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

BASE = Path(__file__).parent
CFG, HIST = BASE / "products.json", BASE / "price_history.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic price monitor, MNU)", "Accept-Language": "ru"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def to_price(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d\s\u00a0]*(?:[.,]\d+)?", str(v))
    if not m:
        raise ValueError(f"баға емес: {v!r}")
    return float(re.sub(r"[\s\u00a0]", "", m.group()).replace(",", "."))


def dig(obj, path):
    """a.b[0].c  немесе  offers[store=Magnum].price  (сүзгі: мәтін ішінде кездессе)."""
    for tok in re.findall(r"[^.\[\]]+|\[[^\]]*\]", path):
        if tok.startswith("["):
            q = tok[1:-1]
            if "=" in q:
                k, v = q.split("=", 1)
                obj = next(x for x in obj if v.lower() in str(x.get(k, "")).lower())
            else:
                obj = obj[int(q)]
        else:
            obj = obj[tok]
    return obj


def from_ld_or_meta(html):
    for blk in re.findall(r'<script[^>]+ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(blk)
        except ValueError:
            continue
        for item in (d if isinstance(d, list) else [d]):
            off = item.get("offers") if isinstance(item, dict) else None
            for o in (off if isinstance(off, list) else [off] if off else []):
                if isinstance(o, dict) and o.get("price") is not None:
                    return to_price(o["price"])
    m = re.search(r'(?:product|og):price:amount"\s+content="([\d.,\s]+)"', html)
    return to_price(m.group(1)) if m else None


def extract(p, text):
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if data is not None and p.get("price_path"):
        return to_price(dig(data, p["price_path"]))
    if p.get("regex"):
        m = re.search(p["regex"], text, re.S)
        if m:
            return to_price(m.group(1))
    price = from_ld_or_meta(text)
    if price is None:
        raise ValueError("баға табылмады: api_url+price_path немесе regex көрсетіңіз (README қараңыз)")
    return price


PRICE_KEYS = ("price", "current_price", "currentPrice", "min_price", "minPrice", "cost", "amount", "regular_price")


def walk(o, store, out):
    """Дүкен атауы бар ЕҢ ШАҒЫН жазбадан (бір ұсыныс) бағаны жинайды."""
    found = False
    for v in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else []):
        found |= walk(v, store, out)
    if isinstance(o, dict) and not found:
        dump = json.dumps(o, ensure_ascii=False)
        if store in dump.lower() and len(dump) <= 500:
            for k in PRICE_KEYS:
                if k in o:
                    try:
                        v = to_price(o[k])
                    except Exception:
                        continue
                    if 50 <= v <= 100000:
                        out.append((v, dump[:160]))
                        return True
    return found


def from_text(text, store):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, l in enumerate(lines):
        if store in l.lower():
            for w in lines[i:i + 4] + lines[max(0, i - 2):i]:
                m = re.search(r"(\d[\d\s\u00a0]*(?:[.,]\d+)?)\s*₸", w)
                if m and 50 <= to_price(m.group(1)) <= 100000:
                    out.append((to_price(m.group(1)), " | ".join(lines[max(0, i - 1):i + 3])[:160]))
                    break
    return out


def render(url):
    from playwright.sync_api import sync_playwright
    jsons = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(locale="ru-RU", user_agent=HEADERS["User-Agent"])

        def on_resp(r):
            try:
                if "json" in r.headers.get("content-type", ""):
                    jsons.append((r.url, r.json()))
            except Exception:
                pass
        pg.on("response", on_resp)
        pg.goto(url, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(int(os.getenv("RENDER_WAIT_MS", "4000")))
        text = pg.inner_text("body")
        b.close()
    return text, jsons


def extract_rendered(p):
    store = p.get("store", "magnum").lower()
    text, jsons = render(p["page_url"])
    cands = []
    for _, data in jsons:
        walk(data, store, cands)
    source = "JSON"
    if not cands:
        cands, source = from_text(text, store), "мәтін"
    values = sorted({v for v, _ in cands})
    if len(values) == 1:
        return values[0]
    why = "бірнеше әртүрлі баға табылды" if values else f"«{store}» дүкенінің бағасы табылмады"
    diag = "\n".join(f"    {v}: {d}" for v, d in cands[:6])
    raise ValueError(f"{why} ({source}).\n{diag}\n  Беттегі мәтін: {text[:500]!r}\n  JSON сұраулар: "
                     + ", ".join(u for u, _ in jsons[:8]))


def get_price(p):
    return extract_rendered(p) if p.get("render") else extract(p, fetch(p.get("api_url") or p["page_url"]))


def last_prices():
    last = {}
    if HIST.exists():
        for r in csv.DictReader(HIST.open(encoding="utf-8")):
            last[r["id"]] = float(r["price_kzt"])
    return last


def fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def send(to, subject, body):
    user, pwd = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if os.getenv("DRY_RUN") or not (user and pwd):
        print("--- E-MAIL (жіберілмеді: DRY_RUN немесе SMTP_USER/SMTP_PASS жоқ) ---")
        print(f"To: {to}\nSubject: {subject}\n\n{body}")
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.getenv("MAIL_FROM", user), ", ".join([to] if isinstance(to, str) else to), subject
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return True


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    prev, now = last_prices(), datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rows, changes, errors = [], [], []
    for p in cfg["products"]:
        try:
            price = get_price(p)
        except Exception as e:  # дерек жоқ болса нөлмен алмастырмаймыз
            errors.append(f"{p['name']}: {e}")
            continue
        rows.append([now, p["id"], p["name"], price, p["page_url"]])
        old = prev.get(p["id"])
        if old is not None and price != old:
            d = price - old  # абсолюттік = соңғы − бастапқы; % = d / бастапқы × 100
            changes.append(f"{p['name']}: {fmt(old)} → {fmt(price)} ₸ ({'+' if d > 0 else '−'}{fmt(abs(d))} ₸, "
                           f"{'+' if d > 0 else '−'}{fmt(abs(d / old * 100))}%)\n  {p['page_url']}")
    new = not HIST.exists()
    with HIST.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "id", "name", "price_kzt", "url"])
        w.writerows(rows)
    print(f"{now}: {len(rows)} баға жазылды, {len(changes)} өзгеріс, {len(errors)} қате")
    if changes or errors:
        body = f"Тексеру уақыты: {now}\n\n"
        if changes:
            body += "БАҒА ӨЗГЕРДІ:\n" + "\n".join(changes) + "\n\n"
        if errors:
            body += "ҚАТЕЛЕР (баға оқылмады):\n" + "\n".join(errors) + "\n"
        head = f"[arzan.kz] Баға өзгерді ({len(changes)})" if changes else "[arzan.kz] Бақылау қатесі"
        send(cfg["recipient"], head, body)


if __name__ == "__main__":
    main()
