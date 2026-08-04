# 옵션 분석 JSON·스냅샷·히스토리·전망 메모를 합쳐 자립형 HTML 대시보드를 생성하는 스크립트.
import html as html_mod
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from explain import TEXT, gamma_words, tip

BASE = Path(__file__).parent

# 종목별 주소 — 대시보드 상단에서 서로 오갈 수 있게 한다.
# 웹(깃허브 페이지)에서는 SITE_BASE 환경변수가 있으면 같은 폴더의 파일로 연결한다.
_BASE_URL = os.environ.get("SITE_BASE", "").rstrip("/")
_TICKERS = [("QQQ", "나스닥100"), ("NVDA", "엔비디아"), ("TSLA", "테슬라"),
            ("AMZN", "아마존"), ("GOOGL", "알파벳A"), ("SOXX", "반도체"),
            ("PLTR", "팔란티어"), ("CRWV", "코어위브"), ("IREN", "아이렌"),
            ("IONQ", "아이온큐"), ("TEM", "템퍼스AI"), ("EWY", "한국")]
SITES = [(tk, name, f"{_BASE_URL}/{tk}.html" if _BASE_URL else f"{tk}.html")
         for tk, name in _TICKERS]


def build_switcher(cur):
    tabs = ""
    for tk, name, url in SITES:
        if tk == cur:
            tabs += f'<span class="tab on">{tk} <em>{name}</em></span>'
        else:
            tabs += f'<a class="tab" href="{url}" target="_top">{tk} <em>{name}</em></a>'
    return f'<nav class="switch">{tabs}</nav>'


def note(key):
    """섹션 제목 아래에 붙는 해설 블록."""
    t = TEXT.get(key)
    if not t:
        return ""
    cav = f'<div class="n-cav">⚠ {esc(t["caveat"])}</div>' if t.get("caveat") else ""
    return (f'<div class="note-box"><p class="n-head">{esc(t["headline"])}</p>'
            f'<p class="n-body">{esc(t["body"])}</p>'
            f'<div class="n-rows"><div><span class="n-ar up">↑</span>{esc(t["high"])}</div>'
            f'<div><span class="n-ar dn">↓</span>{esc(t["low"])}</div></div>{cav}</div>')


def esc(s):
    return html_mod.escape(str(s))


def fmt(v, nd=2):
    if v is None:
        return "-"
    return f"{v:,.{nd}f}".rstrip("0").rstrip(".") if nd else f"{v:,.0f}"


def md_to_html(md):
    # 전망 메모용 초소형 마크다운 변환기 (제목·굵게·목록·링크·문단만)
    out, in_list = [], False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        t = esc(line)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
        t = re.sub(r"\[(.+?)\]\((https?://.+?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
        if t.startswith("# "):
            out.append(f"<h3>{t[2:]}</h3>")
        elif t.startswith("## "):
            out.append(f"<h4>{t[3:]}</h4>")
        elif re.match(r"^\d+\. ", t):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\d+\. ", "", t)
            out.append(f"<li>{item}</li>")
        elif t.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{t[2:]}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{t}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def build_ladder(a):
    spot = a["spot"]
    rows = [{"price": spot, "kind": "현물", "note": "지금 가격" + ("" if a.get("spot_is_live") else " (어제 종가)")}]
    if a.get("call_wall"):
        oi = next((x["oi"] for x in a["top_call_oi"] if x["strike"] == a["call_wall"]), None)
        rows.append({"price": a["call_wall"], "kind": "옵션",
                     "note": f"위쪽에서 오를 때 버는 보험이 제일 두꺼운 곳 · {fmt(oi, 0)}개 (콜월)"})
    if a.get("put_wall"):
        oi = next((x["oi"] for x in a["top_put_oi"] if x["strike"] == a["put_wall"]), None)
        rows.append({"price": a["put_wall"], "kind": "옵션",
                     "note": f"아래쪽에서 내릴 때 버는 보험이 제일 두꺼운 곳 · {fmt(oi, 0)}개 (풋월)"})
    if a.get("gamma_flip"):
        rows.append({"price": a["gamma_flip"], "kind": "옵션",
                     "note": "성격이 바뀌는 갈림길 · 위는 가격이 묶이고, 아래는 크게 움직임 (감마 플립)"})
    mp = a["max_pain"].get(a["nearest_expiry"])
    if mp:
        rows.append({"price": mp, "kind": "옵션",
                     "note": f"{a['nearest_expiry']} 만기에 옵션 산 사람들이 가장 많이 잃는 값 (맥스페인)"})
    for name, v in a.get("ma", {}).items():
        rows.append({"price": v, "kind": "이평", "note": f"최근 {name[2:]}일 평균 가격"})
    for s in a.get("supports", []):
        rows.append({"price": s["price"], "kind": "기술", "note": f"과거에 {s['touches']}번 부딪히고 올라온 자리"})
    for r in a.get("resistances", []):
        rows.append({"price": r["price"], "kind": "기술", "note": f"과거에 {r['touches']}번 부딪히고 내려온 자리"})
    rows.append({"price": a["high_52w"], "kind": "기술", "note": "최근 1년 중 가장 높았던 값"})
    rows.sort(key=lambda r: -r["price"])

    trs = []
    for r in rows:
        d = (r["price"] - spot) / spot * 100
        dist = "기준" if r["kind"] == "현물" else f"{d:+.1f}%"
        cls = ' class="spot-row"' if r["kind"] == "현물" else ""
        chip = f'<span class="chip chip-{ {"현물": "spot", "옵션": "opt", "이평": "ma", "기술": "tech"}[r["kind"]] }">{r["kind"]}</span>'
        trs.append(f'<tr{cls}><td class="num">{fmt(r["price"])}</td><td>{chip}</td>'
                   f'<td class="note">{esc(r["note"])}</td><td class="num dist">{dist}</td></tr>')
    return ('<table class="ladder"><thead><tr><th>가격</th><th>구분</th><th>의미</th><th>현물대비</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>')


def build_oi_chart(a, snap):
    spot = a["spot"]
    band = snap[(snap["strike"] >= spot * 0.92) & (snap["strike"] <= spot * 1.08)]
    g = band.groupby(["strike", "type"])["oi"].sum().unstack(fill_value=0)
    for c in ("C", "P"):
        if c not in g:
            g[c] = 0
    g["total"] = g["C"] + g["P"]
    g = g.sort_values("total", ascending=False).head(26).sort_index(ascending=False)
    if not len(g):
        return "<p class='muted'>표시할 OI 데이터가 없습니다.</p>"

    W, CX, HALF, ROW, BAR = 640, 320, 250, 19, 12
    H = ROW * len(g) + 34
    mx = max(g["C"].max(), g["P"].max()) or 1
    sc = lambda v: v / mx * HALF
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="행사가별 미결제약정">']
    parts.append(f'<line x1="{CX}" y1="18" x2="{CX}" y2="{H - 16}" class="axisline"/>')
    y = 20
    spot_y = None
    strikes = list(g.index)
    for i, (k, r) in enumerate(g.iterrows()):
        pw = sc(r["P"])
        cw = sc(r["C"])
        is_pw, is_cw = k == a.get("put_wall"), k == a.get("call_wall")
        parts.append(f'<rect x="{CX - 24 - pw:.1f}" y="{y}" width="{pw:.1f}" height="{BAR}" rx="3" '
                     f'class="bar-put{" wall" if is_pw else ""}" data-tip="행사가 {fmt(k)} · 풋 OI {fmt(r["P"], 0)}계약"/>')
        parts.append(f'<rect x="{CX + 24}" y="{y}" width="{cw:.1f}" height="{BAR}" rx="3" '
                     f'class="bar-call{" wall" if is_cw else ""}" data-tip="행사가 {fmt(k)} · 콜 OI {fmt(r["C"], 0)}계약"/>')
        parts.append(f'<text x="{CX}" y="{y + 10}" class="klabel" text-anchor="middle">{fmt(k, 0)}</text>')
        if is_pw:
            parts.append(f'<text x="{CX - 28 - pw:.1f}" y="{y + 10}" class="wall-label put" text-anchor="end">풋월</text>')
        if is_cw:
            parts.append(f'<text x="{CX + 28 + cw:.1f}" y="{y + 10}" class="wall-label call">콜월</text>')
        if spot_y is None and i + 1 < len(strikes) and strikes[i] >= spot >= strikes[i + 1]:
            spot_y = y + ROW - 3
        y += ROW
    if spot_y:
        parts.append(f'<line x1="30" y1="{spot_y}" x2="{W - 30}" y2="{spot_y}" class="spotline"/>')
        parts.append(f'<text x="{W - 30}" y="{spot_y - 4}" class="spot-label" text-anchor="end">현물 {fmt(spot)}</text>')
    parts.append(f'<text x="{CX - 24}" y="{H - 3}" class="axis" text-anchor="end">← 풋 OI</text>')
    parts.append(f'<text x="{CX + 24}" y="{H - 3}" class="axis">콜 OI →</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_gex_curve(a):
    """가격을 옮겨가며 '그 가격이면 증권사가 뭘 하나'를 곡선 하나로 보여준다."""
    cur = a.get("gex_curve") or []
    if len(cur) < 10:
        return "<p class='muted'>곡선 데이터가 없습니다.</p>"
    spot, flip = a["spot"], a.get("gamma_flip")
    xs_v = [c["price"] for c in cur]
    ys_v = [c["gex_bn"] for c in cur]
    lo, hi = min(xs_v), max(xs_v)
    amp = max(abs(min(ys_v)), abs(max(ys_v))) or 1

    W, H, L, R, T, B = 720, 260, 20, 20, 26, 46
    zero = T + (H - T - B) / 2
    half = (H - T - B) / 2 - 6
    X = lambda p: L + (p - lo) / (hi - lo) * (W - L - R)
    Y = lambda v: zero - (v / amp) * half

    pts = " ".join(f"{X(c['price']):.1f},{Y(c['gex_bn']):.1f}" for c in cur)
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="가격별 증권사 행동 곡선">']
    # 위쪽(반대로 받아줌) / 아래쪽(같이 감) 배경
    p.append(f'<rect x="{L}" y="{T}" width="{W-L-R}" height="{zero-T:.1f}" fill="var(--call)" opacity="0.07"/>')
    p.append(f'<rect x="{L}" y="{zero:.1f}" width="{W-L-R}" height="{H-B-zero:.1f}" fill="var(--put)" opacity="0.07"/>')
    p.append(f'<text x="{L+8}" y="{T+15}" class="zone-lab call">↑ 변동성을 줄이는 구간 (오르면 팔고, 내리면 사줌)</text>')
    p.append(f'<text x="{L+8}" y="{H-B-6:.0f}" class="zone-lab put">↓ 변동성을 키우는 구간 (오르면 같이 사고, 내리면 같이 팜)</text>')
    p.append(f'<line x1="{L}" y1="{zero:.1f}" x2="{W-R}" y2="{zero:.1f}" class="axisline"/>')
    p.append(f'<polyline points="{pts}" class="price-line" fill="none" stroke-width="2.5"/>')

    for v, lab, cls in ((spot, f"지금 {fmt(spot)}", "spotline"), (flip, f"갈림길 {fmt(flip)}", "flipline")):
        if v and lo <= v <= hi:
            p.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{H-B}" class="{cls}"/>')
            anc = "end" if cls == "spotline" else "start"
            dx = -5 if anc == "end" else 5
            p.append(f'<text x="{X(v)+dx:.1f}" y="{H-B+15:.0f}" class="{cls}-label" text-anchor="{anc}">{lab}</text>')
    for pr in (lo, (lo + hi) / 2, hi):
        p.append(f'<text x="{X(pr):.1f}" y="{H-6}" class="axis" text-anchor="middle">{fmt(pr,0)}</text>')
    p.append("</svg>")

    now = next((c["gex_bn"] for c in cur if abs(c["price"] - spot) == min(abs(x["price"] - spot) for x in cur)), 0)
    side = ("아래쪽" if now < 0 else "위쪽")
    act = ("변동성을 키우는" if now < 0 else "변동성을 줄이는")
    return ("".join(p) +
            f'<p class="muted" style="margin-top:8px">가로축은 <strong>주가</strong>, 세로축은 '
            '<strong>그 가격이 되면 증권사가 변동성을 키우는지 줄이는지</strong>입니다. '
            f'지금 {fmt(spot)}달러는 선의 <strong>{side}</strong>이라 <strong>{act} 구간</strong>입니다. '
            '곡선이 가운데 선을 넘는 지점이 성격이 바뀌는 갈림길입니다.</p>')


def build_gex_chart(a):
    spot = a["spot"]
    raw = {float(k): v for k, v in a.get("gex_by_strike_bn", {}).items()}
    bucket = {}
    for k, v in raw.items():
        if spot * 0.92 <= k <= spot * 1.08:
            b = round(k / 5) * 5
            bucket[b] = bucket.get(b, 0) + v
    ks = sorted(bucket)
    if not ks:
        return "<p class='muted'>GEX 데이터가 없습니다.</p>"
    W, H, L, R, T, B = 720, 250, 46, 14, 16, 34
    pw = W - L - R
    n = len(ks)
    bw = min(22, pw / n - 3)
    mx = max(abs(v) for v in bucket.values()) or 1
    zero_y = T + (H - T - B) / 2
    sc = lambda v: v / mx * (H - T - B) / 2 * 0.92
    xpos = lambda i: L + (i + 0.5) * pw / n
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="행사가별 감마 노출">']
    parts.append(f'<line x1="{L}" y1="{zero_y}" x2="{W - R}" y2="{zero_y}" class="axisline"/>')
    for i, k in enumerate(ks):
        v = bucket[k]
        h = abs(sc(v))
        ytop = zero_y - h if v >= 0 else zero_y
        cls = "bar-call" if v >= 0 else "bar-put"
        act = "변동성 줄임" if v >= 0 else "변동성 키움"
        parts.append(f'<rect x="{xpos(i) - bw / 2:.1f}" y="{ytop:.1f}" width="{bw:.1f}" height="{max(h, 0.5):.1f}" rx="3" '
                     f'class="{cls}" data-tip="{fmt(k, 0)}달러 부근 · 증권사 {act} · 크기 {abs(v):.2f}"/>')
        if i % 2 == 0:
            parts.append(f'<text x="{xpos(i):.1f}" y="{H - 16}" class="axis" text-anchor="middle">{fmt(k, 0)}</text>')
    for lv, lbl, cls in ((spot, f"현물 {fmt(spot)}", "spotline"), (a.get("gamma_flip"), f"감마 플립 {fmt(a.get('gamma_flip'))}", "flipline")):
        if lv and ks[0] <= lv <= ks[-1]:
            x = L + (lv - ks[0]) / (ks[-1] - ks[0]) * ((n - 1) / n) * pw + 0.5 * pw / n
            parts.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H - B}" class="{cls}"/>')
            anchor = "end" if cls == "spotline" else "start"
            parts.append(f'<text x="{x + (4 if anchor == "start" else -4):.1f}" y="{T + 10}" class="{cls}-label" text-anchor="{anchor}">{lbl}</text>')
    parts.append(f'<text x="{L - 6}" y="{zero_y + 4}" class="axis" text-anchor="end">0</text>')
    parts.append(f'<text x="{L - 6}" y="{T + 10}" class="axis" text-anchor="end">+{mx:.1f}B</text>')
    parts.append(f'<text x="{L - 6}" y="{H - B - 2}" class="axis" text-anchor="end">-{mx:.1f}B</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_price_chart(a, px):
    closes = px["Close"].tolist()
    dates = px["Date"].tolist()
    spot = a["spot"]
    levels = []
    mp = a["max_pain"].get(a["nearest_expiry"])
    for v, lbl, cls in ((a.get("call_wall"), "위 보험벽", "lv-call"), (a.get("put_wall"), "아래 보험벽", "lv-put"),
                        (a.get("gamma_flip"), "갈림길", "lv-flip"), (mp, "손해최대", "lv-mp")):
        if v:
            levels.append((v, lbl, cls))
    lo = min(min(closes), min(v for v, _, _ in levels)) * 0.995
    hi = max(max(closes), max(v for v, _, _ in levels)) * 1.005
    W, H, L, R, T, B = 720, 300, 46, 132, 14, 26
    xs = lambda i: L + i / (len(closes) - 1) * (W - L - R)
    ys = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(closes))
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="최근 90일 가격과 옵션 레벨">']
    for frac in (0.25, 0.5, 0.75):
        gy = T + frac * (H - T - B)
        gv = hi - frac * (hi - lo)
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{L - 6}" y="{gy + 4:.1f}" class="axis" text-anchor="end">{fmt(gv, 0)}</text>')
    parts.append(f'<polygon points="{xs(0):.1f},{ys(lo):.1f} {pts} {xs(len(closes) - 1):.1f},{ys(lo):.1f}" class="price-area"/>')
    parts.append(f'<polyline points="{pts}" class="price-line" fill="none"/>')
    used_y = []
    for v, lbl, cls in sorted(levels, key=lambda x: -x[0]):
        yv = ys(v)
        parts.append(f'<line x1="{L}" y1="{yv:.1f}" x2="{W - R}" y2="{yv:.1f}" class="{cls}" data-tip="{lbl} {fmt(v)}"/>')
        ly = yv + 4
        while any(abs(ly - u) < 13 for u in used_y):
            ly += 13
        used_y.append(ly)
        parts.append(f'<text x="{W - R + 5}" y="{ly:.1f}" class="{cls}-t">{lbl} {fmt(v)}</text>')
    lx, lyv = xs(len(closes) - 1), ys(spot)
    parts.append(f'<circle cx="{lx:.1f}" cy="{lyv:.1f}" r="4" class="price-dot"/>')
    parts.append(f'<text x="{lx - 8:.1f}" y="{lyv - 9:.1f}" class="spot-label" text-anchor="end">{fmt(spot)}</text>')
    for i in (0, len(dates) // 2, len(dates) - 1):
        anchor = "start" if i == 0 else ("end" if i == len(dates) - 1 else "middle")
        parts.append(f'<text x="{xs(i):.1f}" y="{H - 8}" class="axis" text-anchor="{anchor}">{dates[i][5:]}</text>')
    parts.append("</svg>")
    return ("\n".join(parts) +
            '<p class="muted" style="margin-top:6px">오른쪽 이름표 — '
            '<strong>위 보험벽</strong>·<strong>아래 보험벽</strong>은 보험이 제일 두껍게 깔린 가격, '
            '<strong>갈림길</strong>은 증권사 성격이 바뀌는 값, '
            '<strong>손해최대</strong>는 옵션 산 사람이 가장 많이 잃는 값입니다.</p>')


def build_history_read(hist_df, days=20):
    """보험벽이 최근 어느 쪽으로 옮겨갔는지 문장으로 풀어준다."""
    d = hist_df.tail(days).dropna(subset=["put_wall", "call_wall"])
    if len(d) < 5:
        return ""
    first, last = d.iloc[0], d.iloc[-1]
    parts = []
    for key, name in (("put_wall", "아래 보험벽"), ("call_wall", "위 보험벽")):
        a, b = float(first[key]), float(last[key])
        if b > a:
            parts.append(f"<strong>{name}</strong>은 {fmt(a)} → {fmt(b)}로 <strong>올라갔습니다</strong>")
        elif b < a:
            parts.append(f"<strong>{name}</strong>은 {fmt(a)} → {fmt(b)}로 <strong>내려갔습니다</strong>")
        else:
            parts.append(f"<strong>{name}</strong>은 {fmt(a)}에서 <strong>그대로</strong>입니다")
    ps, cs = float(last["put_wall"]) - float(first["put_wall"]), float(last["call_wall"]) - float(first["call_wall"])
    if ps > 0 and cs > 0:
        read = "둘 다 위로 올라갔습니다. 사람들이 대비하는 가격대 자체가 높아졌다는 뜻입니다."
    elif ps < 0 and cs < 0:
        read = "둘 다 아래로 내려갔습니다. 사람들이 더 낮은 가격을 염두에 두고 있다는 뜻입니다."
    elif ps < 0 and cs > 0:
        read = "위아래로 벌어졌습니다. 더 넓은 범위를 열어두고 있다는 뜻입니다."
    else:
        read = "위아래가 좁혀졌습니다. 좁은 범위를 예상하고 있다는 뜻입니다."
    return (f'<div class="callout"><strong>최근 {len(d)}거래일 동안</strong><br>'
            f'{parts[0]}. {parts[1]}. {read}</div>')

def build_history_chart(hist_df):
    series = [("spot", "주가", "hs-spot"), ("put_wall", "아래 보험벽", "hs-put"),
              ("call_wall", "위 보험벽", "hs-call"), ("max_pain_near", "손해최대", "hs-mp")]
    df = hist_df.tail(60).reset_index(drop=True)
    vals = [v for key, _, _ in series for v in df[key].dropna().tolist() if key in df]
    if not vals:
        return "<p class='muted'>히스토리가 없습니다.</p>"
    lo, hi = min(vals) * 0.99, max(vals) * 1.01
    W, H, L, R, T, B = 720, 240, 46, 80, 14, 26
    n = max(len(df), 2)
    xs = lambda i: L + i / (n - 1) * (W - L - R)
    ys = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="주요 레벨 일별 추이">']
    for frac in (0.25, 0.5, 0.75):
        gy = T + frac * (H - T - B)
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{L - 6}" y="{gy + 4:.1f}" class="axis" text-anchor="end">{fmt(hi - frac * (hi - lo), 0)}</text>')
    for key, lbl, cls in series:
        if key not in df:
            continue
        pts = [(i, v) for i, v in enumerate(df[key].tolist()) if pd.notna(v)]
        if len(pts) >= 2:
            parts.append(f'<polyline points="{" ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in pts)}" class="{cls}" fill="none"/>')
        for i, v in pts:
            parts.append(f'<circle cx="{xs(i):.1f}" cy="{ys(v):.1f}" r="3.5" class="{cls}-dot" '
                         f'data-tip="{df["date"][i]} · {lbl} {fmt(v)}"/>')
        if pts:
            parts.append(f'<text x="{xs(pts[-1][0]) + 8:.1f}" y="{ys(pts[-1][1]) + 4:.1f}" class="{cls}-t">{lbl}</text>')
    for i in (0, len(df) - 1):
        parts.append(f'<text x="{xs(i):.1f}" y="{H - 8}" class="axis" text-anchor="{"start" if i == 0 else "end"}">{df["date"][i][5:]}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_oi_change(a):
    # 전일 스냅샷과 비교해 만기 소멸·신규 유입·청산을 집계
    snaps = sorted((BASE / "data" / "snapshots").glob(f"{a['ticker']}_*.csv"))
    if len(snaps) < 2:
        return "<p class='muted'>전일 스냅샷이 아직 없어 다음 수집부터 표시됩니다.</p>"
    cur = pd.read_csv(snaps[-1])
    prev = pd.read_csv(snaps[-2])
    prev_date = snaps[-2].stem.split("_", 1)[1]

    gone = sorted(set(prev["expiry"]) - set(cur["expiry"]))
    born = sorted(set(cur["expiry"]) - set(prev["expiry"]))
    expired = prev[prev["expiry"].isin(gone)]
    exp_p = int(expired[expired["type"] == "P"]["oi"].sum())
    exp_c = int(expired[expired["type"] == "C"]["oi"].sum())

    common = set(prev["expiry"]) & set(cur["expiry"])
    parts = [f'<p class="desc" style="margin:0 0 10px">비교 기준: {prev_date} → {a["date"]}. '
             f'만기 소멸 {len(gone)}개(풋 {fmt(exp_p, 0)}·콜 {fmt(exp_c, 0)}계약 소멸), 신규 상장 만기 {len(born)}개.</p>']
    rows_html = {"P": "", "C": ""}
    for t in ("P", "C"):
        c = cur[(cur["expiry"].isin(common)) & (cur["type"] == t)].groupby("strike")["oi"].sum()
        p = prev[(prev["expiry"].isin(common)) & (prev["type"] == t)].groupby("strike")["oi"].sum()
        diff = c.sub(p, fill_value=0).astype(int)
        diff = diff[diff != 0]
        total = int(diff.sum())
        top_in = diff.sort_values(ascending=False).head(5)
        top_out = diff.sort_values().head(5)
        trs = ""
        for label, series in (("유입", top_in), ("이탈", top_out)):
            for k, v in series.items():
                if (label == "유입" and v <= 0) or (label == "이탈" and v >= 0):
                    continue
                cls = "up" if v > 0 else "down"
                trs += (f'<tr><td>{label}</td><td class="num">{fmt(k)}</td>'
                        f'<td class="num {cls}" style="color:var(--{ "up" if v > 0 else "down" })">{v:+,}</td></tr>')
        name = "풋" if t == "P" else "콜"
        rows_html[t] = (f'<div><h3 style="font-size:.9rem;margin:0 0 6px">{name} · 순증감 {total:+,}계약</h3>'
                        '<table class="ladder"><thead><tr><th>구분</th><th>행사가</th><th>OI 증감</th></tr></thead>'
                        f'<tbody>{trs or "<tr><td colspan=3 class=note>변화 없음</td></tr>"}</tbody></table></div>')
    parts.append(f'<div class="duo">{rows_html["P"]}{rows_html["C"]}</div>')
    parts.append('<p class="muted">OI는 순잔량이라 증감의 위치·크기만 보이고 매수·매도 주체는 알 수 없습니다. '
                 '만기가 남았는데 줄었으면 청산, 늘었으면 신규 진입입니다.</p>')
    return "\n".join(parts)


def build_zone_map(a, snap):
    """갈림길을 기준으로 두 구간을 색으로 나누고, 돈이 몰린 자리를 자석으로 표시한다."""
    spot, flip = a["spot"], a.get("gamma_flip")
    lo, hi = spot * 0.93, spot * 1.07
    if flip:
        lo, hi = min(lo, flip * 0.985), max(hi, flip * 1.015)
    W, H, L, R, T = 720, 168, 16, 16, 20
    band_y, band_h = T + 34, 30
    xs = lambda p: L + (p - lo) / (hi - lo) * (W - L - R)

    band = snap[(snap["oi"] > 0) & (snap["strike"] >= lo) & (snap["strike"] <= hi)]
    oi = band.groupby("strike")["oi"].sum().sort_values(ascending=False)
    mags = [(float(k), int(v)) for k, v in oi.head(5).items()]
    mx = max((v for _, v in mags), default=1)

    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="가격 구간 지도">']
    fx = xs(flip) if flip else xs(spot)
    # 두 구간을 색으로 칠한다
    p.append(f'<rect x="{L}" y="{band_y}" width="{max(0,fx-L):.1f}" height="{band_h}" rx="4" '
             f'fill="var(--put)" opacity="0.16" data-tip="이 아래에서는 증권사가 오르면 같이 사고 내리면 같이 팔아 움직임을 키웁니다"/>')
    p.append(f'<rect x="{fx:.1f}" y="{band_y}" width="{max(0,W-R-fx):.1f}" height="{band_h}" rx="4" '
             f'fill="var(--call)" opacity="0.16" data-tip="이 위에서는 증권사가 더 오르면 팔고 더 내리면 사줘서 움직임을 눌러줍니다"/>')
    p.append(f'<text x="{(L+fx)/2:.1f}" y="{band_y+19:.0f}" class="zone-lab put" text-anchor="middle">변동성을 키우는 구간</text>')
    p.append(f'<text x="{(fx+W-R)/2:.1f}" y="{band_y+19:.0f}" class="zone-lab call" text-anchor="middle">변동성을 줄이는 구간</text>')
    if flip:
        p.append(f'<line x1="{fx:.1f}" y1="{band_y-8}" x2="{fx:.1f}" y2="{band_y+band_h+8}" class="flipline"/>')
        p.append(f'<text x="{fx:.1f}" y="{band_y-12}" class="flip-lab" text-anchor="middle">갈림길 {fmt(flip)}</text>')

    # 자석 = 계약이 많이 쌓인 가격
    my = band_y + band_h + 34
    p.append(f'<line x1="{L}" y1="{my}" x2="{W-R}" y2="{my}" class="grid"/>')
    for k, v in mags:
        if not (lo <= k <= hi):
            continue
        r = 5 + (v / mx) * 12
        strength = "가장 셈" if v >= mx * 0.9 else ("셈" if v >= mx * 0.55 else "보통")
        p.append(f'<circle cx="{xs(k):.1f}" cy="{my}" r="{r:.1f}" class="magnet" '
                 f'data-tip="{fmt(k)}달러 · 계약 {v:,}개 · 자석 세기 {strength}"/>')
        p.append(f'<text x="{xs(k):.1f}" y="{my+r+13:.0f}" class="mag-lab" text-anchor="middle">{fmt(k,0)}</text>')

    # 지금 가격
    p.append(f'<line x1="{xs(spot):.1f}" y1="{band_y-8}" x2="{xs(spot):.1f}" y2="{my+8}" class="spotline"/>')
    p.append(f'<text x="{xs(spot):.1f}" y="{T+8}" class="spot-label" text-anchor="middle">지금 {fmt(spot)}</text>')
    p.append("</svg>")

    side = "변동성을 키우는" if (flip and spot < flip) else "변동성을 줄이는"
    rows = "".join(
        f'<tr><td class="num">{fmt(k)}</td><td class="num">{v:,}개</td>'
        f'<td class="num dist">{(k-spot)/spot*100:+.1f}%</td>'
        f'<td>{"●●●" if v >= mx*0.9 else ("●●" if v >= mx*0.55 else "●")}</td></tr>' for k, v in mags)
    return ("".join(p) +
            f'<p class="muted" style="margin-top:10px">지금 {fmt(spot)}달러는 <strong>{side} 구간</strong>에 있습니다. '
            '동그라미는 계약이 많이 쌓인 가격입니다. 클수록 많이 쌓였다는 뜻입니다.</p>'
            '<table class="ladder" style="margin-top:8px"><thead><tr><th>가격</th><th>쌓인 계약</th>'
            f'<th>지금에서</th><th>세기</th></tr></thead><tbody>{rows}</tbody></table>'
            '<p class="muted">자석이라고 부르지만, 1년치로 채점해보니 실제로 가격을 끌어당기는 힘은 '
            '확인되지 않았습니다. "돈이 여기 몰려 있다"는 위치 표시로만 보세요.</p>')


def build_flow_read(ticker, px, days=3):
    """최근 며칠 흐름과 주가 움직임을 나란히 놓고 문장으로 풀어준다."""
    p = BASE / "data" / "history" / f"{ticker}_flows.csv"
    if not p.exists():
        return ""
    f = pd.read_csv(p)
    if len(f) < days + 5:
        return ""
    close = dict(zip(px["Date"], px["Close"]))
    recent = f.tail(days)
    base = f.tail(30).head(27)  # 비교 기준 = 그 이전 구간

    trs = ""
    for r in recent.itertuples():
        c0, c1 = close.get(r.prev_date), close.get(r.date)
        chg = f"{(c1/c0-1)*100:+.2f}%" if c0 and c1 else "-"
        cls = "up" if (c0 and c1 and c1 >= c0) else "down"
        trs += (f'<tr><td class="num">{r.date[5:].replace("-", "/")}</td>'
                f'<td class="num {cls}" style="color:var(--{cls})">{chg}</td>'
                f'<td class="num">{r.call_in:,}</td><td class="num">{r.call_out:,}</td>'
                f'<td class="num" style="color:var(--call)">{r.call_net:+,}</td>'
                f'<td class="num">{r.put_in:,}</td><td class="num">{r.put_out:,}</td>'
                f'<td class="num" style="color:var(--put)">{r.put_net:+,}</td></tr>')

    cn, pn = int(recent["call_net"].sum()), int(recent["put_net"].sum())
    d0, d1 = close.get(recent["prev_date"].iloc[0]), close.get(recent["date"].iloc[-1])
    move = (d1 / d0 - 1) * 100 if d0 and d1 else 0
    up = move >= 0
    call_side = cn > pn

    if up and call_side:
        read = ("주가가 오르는 동안 <strong>오를 때 버는 쪽(콜)에 돈이 더 붙었습니다.</strong> "
                "오르는 흐름을 따라간 모습입니다.")
    elif up and not call_side:
        read = ("주가는 올랐는데 <strong>내릴 때 버는 쪽(풋)에 돈이 더 붙었습니다.</strong> "
                "오르는 중에도 대비를 늘린 모습입니다.")
    elif not up and call_side:
        read = ("주가가 빠지는 동안 오히려 <strong>오를 때 버는 쪽(콜)에 돈이 더 붙었습니다.</strong> "
                "싸졌을 때 사두려는 돈이거나, 반등을 노린 돈으로 보입니다.")
    else:
        read = ("주가가 빠지는 동안 <strong>내릴 때 버는 쪽(풋)에 돈이 더 붙었습니다.</strong> "
                "떨어지는 걸 보고 대비를 더 늘린 모습입니다.")

    extra = ""
    for side, name, color in (("put", "풋", "var(--put)"), ("call", "콜", "var(--call)")):
        med = base[f"{side}_out"].median() or 1
        last = recent.iloc[-1]
        if last[f"{side}_out"] > med * 2.2:
            extra += (f' 그리고 마지막 날 <strong style="color:{color}">{name} 계약이 평소의 '
                      f'{last[f"{side}_out"]/med:.1f}배</strong>나 빠져나갔습니다. '
                      '걸어놨던 사람들이 한꺼번에 정리했다는 뜻입니다.')

    return (f'<div class="callout"><strong>최근 {days}거래일 읽기 — 주가 {move:+.2f}%</strong><br>'
            f'{read}{extra} 이 기간 새로 걸린 계약은 콜 {cn:+,}개, 풋 {pn:+,}개입니다.</div>'
            '<table class="ladder"><thead><tr><th>날짜</th><th>주가</th>'
            '<th>콜 들어옴</th><th>콜 나감</th><th>콜 순증</th>'
            '<th>풋 들어옴</th><th>풋 나감</th><th>풋 순증</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
            '<p class="muted">"순증"은 들어온 것에서 나간 것을 뺀 값입니다. '
            '한쪽에 돈이 몰렸다고 그쪽으로 간다는 뜻은 아닙니다. 산 건지 판 건지는 알 수 없기 때문입니다.</p>')


def build_flows(ticker, days=45):
    p = BASE / "data" / "history" / f"{ticker}_flows.csv"
    if not p.exists():
        return "<p class='muted'>흐름 데이터가 아직 없습니다.</p>"
    f = pd.read_csv(p).tail(days).reset_index(drop=True)
    if len(f) < 5:
        return "<p class='muted'>흐름 데이터가 아직 부족합니다.</p>"

    n = len(f)
    W, PH, L, R = 720, 132, 52, 12
    mx = max(f["call_in"].max(), f["call_out"].max(), f["put_in"].max(), f["put_out"].max()) or 1
    bw = min(11, (W - L - R) / n - 2)
    xs = lambda i: L + (i + 0.5) * (W - L - R) / n

    def panel(kind, label, color):
        H = PH
        zero = H / 2
        half = (H / 2) - 14
        parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{label} 일별 유입·이탈">']
        parts.append(f'<line x1="{L}" y1="{zero}" x2="{W-R}" y2="{zero}" class="axisline"/>')
        parts.append(f'<text x="{L-6}" y="{zero-4:.0f}" class="axis" text-anchor="end">들어옴</text>')
        parts.append(f'<text x="{L-6}" y="{zero+12:.0f}" class="axis" text-anchor="end">빠져나감</text>')
        for i, r in f.iterrows():
            vin, vout = r[f"{kind}_in"], r[f"{kind}_out"]
            hin, hout = vin / mx * half, vout / mx * half
            tip = (f'{r["date"]} · {label} 새로 들어온 계약 {int(vin):,} / '
                   f'빠져나간 계약 {int(vout):,} / 순 {int(vin-vout):+,}')
            parts.append(f'<rect x="{xs(i)-bw/2:.1f}" y="{zero-hin:.1f}" width="{bw:.1f}" '
                         f'height="{max(hin,0.6):.1f}" rx="2" fill="{color}" data-tip="{tip}"/>')
            parts.append(f'<rect x="{xs(i)-bw/2:.1f}" y="{zero:.1f}" width="{bw:.1f}" '
                         f'height="{max(hout,0.6):.1f}" rx="2" fill="{color}" opacity="0.42" data-tip="{tip}"/>')
        for i in (0, n // 2, n - 1):
            anc = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            parts.append(f'<text x="{xs(i):.1f}" y="{H-2}" class="axis" text-anchor="{anc}">{f["date"][i][5:]}</text>')
        parts.append("</svg>")
        return "".join(parts)

    last5 = f.tail(5)
    cn, pn = int(last5["call_net"].sum()), int(last5["put_net"].sum())
    side = "콜(오를 때 버는 쪽)" if cn > pn else "풋(내릴 때 버는 쪽)"
    summary = (f'<div class="callout"><strong>최근 5거래일 새로 걸린 돈</strong> — '
               f'콜 {cn:+,}계약, 풋 {pn:+,}계약. <strong>{side}</strong>으로 더 몰렸습니다. '
               '위로 솟은 막대가 새로 들어온 계약, 아래로 내려간 흐린 막대가 빠져나간 계약입니다.</div>')
    return (summary
            + f'<h3 style="font-size:.9rem;margin:14px 0 4px;color:var(--call)">콜 — 오를 때 돈 버는 쪽</h3>'
            + panel("call", "콜", "var(--call)")
            + f'<h3 style="font-size:.9rem;margin:18px 0 4px;color:var(--put)">풋 — 내릴 때 돈 버는 쪽</h3>'
            + panel("put", "풋", "var(--put)")
            + '<p class="muted">만기가 되어 사라진 계약은 뺐습니다. 만기 소멸은 누가 판 게 아니라 계약이 수명을 다한 것이라 '
              '흐름으로 세면 안 되기 때문입니다. 막대에 마우스를 올리면 그날 숫자가 나옵니다.</p>')


def build_backtest():
    p = BASE / "data" / "analytics" / "QQQ_backtest.json"
    if not p.exists():
        return None
    b = json.loads(p.read_text(encoding="utf-8"))
    g = b.get("감마국면_다음날변동폭") or {}
    neg, pos = g.get("마이너스감마"), g.get("플러스감마")
    mp = b.get("맥스페인") or {}
    pw, cw = b["풋월"], b["콜월"]

    def verdict(edge, n):
        if n < 20:
            return ("표본부족", "var(--muted)")
        if edge >= 8:
            return ("근거 있음", "var(--good)")
        if edge <= -5:
            return ("근거 없음", "var(--crit)")
        return ("차이 없음", "var(--serious)")

    rows = []
    m = b.get("OI밀집_같은거리비교") or {}
    for label, key in (("OI가 몰린 자리가 정말 잘 버티나 (풋)", "풋_같은거리비교"),
                       ("OI가 몰린 자리가 정말 잘 막나 (콜)", "콜_같은거리비교")):
        d = m.get(key)
        if not d:
            continue
        v, c = verdict(d["우위%p"], d["OI상위_표본"])
        rows.append((label, f'{d["OI상위_유지율%"]}%', f'{d["OI하위_유지율%"]}%',
                     f'{d["우위%p"]:+.1f}%p', f'{d["OI상위_표본"]:,}건', v, c))
    v, c = verdict(pw["우위%p"], pw["touch"])
    rows.append(("아래쪽 두꺼운 곳에서 정말 반등하나", f'{pw["방어율%"]}%', f'{pw["대조군_방어율%"]}%',
                 f'{pw["우위%p"]:+.1f}%p', f'{pw["touch"]}회', v, c))
    v, c = verdict(cw["우위%p"], cw["touch"])
    rows.append(("위쪽 두꺼운 곳에서 정말 막히나", f'{cw["저항율%"]}%', f'{cw["대조군_저항율%"]}%',
                 f'{cw["우위%p"]:+.1f}%p', f'{cw["touch"]}회', v, c))
    if mp:
        edge = mp["현물기준선_평균오차%"] - mp["맥스페인_평균오차%"]
        v, c = verdict(edge * 10, mp["n"])
        rows.append(("손해 제일 큰 값이 만기 가격을 맞히나", f'오차 {mp["맥스페인_평균오차%"]}%',
                     f'오차 {mp["현물기준선_평균오차%"]}%', f'{edge:+.2f}%p', f'{mp["n"]}회', v, c))
    if neg and pos:
        edge = (neg["중앙값"] - pos["중앙값"]) / max(0.01, pos["중앙값"]) * 100
        v, c = verdict(edge, neg["n"])
        rows.append(("갈림길 아래면 정말 더 흔들리나", f'{neg["중앙값"]}%', f'{pos["중앙값"]}%',
                     f'{neg["중앙값"]/max(0.01,pos["중앙값"]):.1f}배', f'{neg["n"]}일', v, c))

    trs = "".join(
        f'<tr><td>{esc(t)}</td><td class="num">{esc(a1)}</td><td class="num">{esc(a2)}</td>'
        f'<td class="num">{esc(d)}</td><td class="num">{esc(n)}</td>'
        f'<td><span class="chip" style="color:{col};border-color:{col}">{v}</span></td></tr>'
        for t, a1, a2, d, n, v, col in rows)

    return (f'<p class="desc" style="margin:0 0 10px">검증 기간 {b["기간"]} · 표본 {b["표본일수"]}일. '
            '실제 과거 데이터로 각 지표가 맞았는지 채점한 것입니다.</p>'
            '<table class="ladder"><thead><tr><th>검증한 주장</th><th>지표</th><th>대조군</th>'
            '<th>차이</th><th>표본</th><th>판정</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
            '<p class="muted">맨 위 두 줄이 가장 공정한 비교입니다. 현물에서 같은 거리에 있는 행사가들만 모아 '
            'OI 상위 4분의 1과 하위 4분의 1로 갈라, 가격이 닿았을 때 되돌아왔는지를 비교했습니다. '
            '거리 조건이 같으니 차이가 있다면 그건 OI 밀집 때문입니다. 아래 두 줄은 벽에서 1% 벗어난 자리를, '
            '맥스페인은 "그냥 오늘 가격 그대로 쓰기"를 대조군으로 삼았습니다. '
            '대조군을 못 이기면 그 지표엔 예측력이 없다는 뜻입니다. 한 종목·1년 결과라 확정은 아니지만, '
            '벽을 "여기서 반등한다"가 아니라 "돈이 여기 몰려 있다"로만 읽어야 할 근거로는 충분합니다.</p>')


def build_occ(a):
    o = a.get("occ")
    if not o:
        return "<p class='muted'>OCC 데이터를 가져오지 못했습니다.</p>"
    rows = [("고객 (개인·기관 주문)", o["customer_total"], o["call_customer"], o["put_customer"], o["customer_pcr"], "cust"),
            ("증권사 자기매매", o["firm_total"], o["call_firm"], o["put_firm"], o["firm_pcr"], "firm"),
            ("마켓메이커", o["mm_total"], o["call_market_maker"], o["put_market_maker"],
             round(o["put_market_maker"] / max(1, o["call_market_maker"]), 3), "mm")]
    total = sum(r[1] for r in rows) or 1
    bars, trs = "", ""
    colors = {"cust": "var(--call)", "firm": "var(--mp)", "mm": "var(--muted)"}
    for label, tot, c, p, pcr, key in rows:
        share = tot / total * 100
        bars += (f'<div class="occ-seg" style="width:{share:.2f}%;background:{colors[key]}" '
                 f'data-tip="{label} · {tot:,}계약 ({share:.1f}%)"></div>')
        trs += (f'<tr><td>{esc(label)}</td><td class="num">{tot:,}</td><td class="num">{share:.1f}%</td>'
                f'<td class="num">{c:,}</td><td class="num">{p:,}</td><td class="num">{pcr:.2f}</td></tr>')
    stale = (' <strong style="color:var(--serious)">(전일 데이터 — 당일분 미공표)</strong>'
             if o.get("stale") else "")
    lean = ("내릴 때 버는 쪽(풋)" if o["firm_pcr"] > o["customer_pcr"] else "오를 때 버는 쪽(콜)")
    gap = abs(o["firm_pcr"] - o["customer_pcr"])
    strength = "훨씬" if gap > 0.3 else ("조금" if gap > 0.1 else "거의 비슷하게")
    fs = o["firm_share"] * 100
    read = (f'<div class="callout"><strong>이 표 읽는 법</strong><br>'
            f'거래의 절반 이상은 <strong>중개상</strong>입니다. 이들은 손님 반대편을 받아주는 역할이라 '
            '방향 신호로 읽지 않습니다. 봐야 할 건 나머지 둘입니다.<br>'
            f'<strong>증권사가 자기 돈으로 건 거래는 전체의 {fs:.1f}%</strong>뿐이지만, '
            f'이쪽은 남의 주문이 아니라 자기 판단입니다. 어제 이들은 손님들보다 '
            f'<strong>{lean}으로 {strength}</strong> 기울었습니다 '
            f'(증권사 {o["firm_pcr"]:.2f} vs 손님 {o["customer_pcr"]:.2f}).<br>'
            '자기 돈 거는 쪽이 손님과 다른 방향을 보면 눈여겨볼 만합니다. '
            '다만 이것도 산 건지 판 건지는 나오지 않습니다.</div>')
    return (read + f'<p class="desc" style="margin:0 0 10px">기준일 {o["as_of"]}{stale} · 전 거래소 합산.</p>'
            f'<div class="occ-bar">{bars}</div>'
            '<div class="legend" style="margin-top:8px">'
            '<span><span class="sw" style="background:var(--call)"></span>고객</span>'
            '<span><span class="sw" style="background:var(--mp)"></span>증권사 자기매매</span>'
            '<span><span class="sw" style="background:var(--muted)"></span>마켓메이커</span></div>'
            '<table class="ladder" style="margin-top:10px"><thead><tr><th>주체</th><th>합계</th><th>비중</th>'
            '<th>콜</th><th>풋</th><th>풋/콜</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
            f'<p class="muted">증권사 자기매매(자기 돈을 거는 쪽)의 풋/콜은 {o["firm_pcr"]:.2f}, '
            f'고객은 {o["customer_pcr"]:.2f} — 증권사가 고객보다 {lean}으로 기울어 있습니다. '
            '마켓메이커는 상대를 받아주는 쪽이라 방향 신호로 읽지 않습니다. '
            '매수·매도 방향과 신규·청산 구분은 이 데이터에 없습니다.</p>')


def build_expiry_gex(a):
    rows = a.get("expiry_gex") or []
    if not rows:
        return "<p class='muted'>만기별 데이터가 없습니다.</p>"
    rows = rows[:12]
    mx = max(abs(r["gex_bn"]) for r in rows) or 1
    op = a.get("opex_biggest") or {}
    trs = ""
    for r in rows:
        w = abs(r["gex_bn"]) / mx * 100
        color = "var(--call)" if r["gex_bn"] >= 0 else "var(--put)"
        big = ' style="font-weight:700"' if r["expiry"] == op.get("expiry") else ""
        act = "변동성 줄임" if r["gex_bn"] >= 0 else "변동성 키움"
        trs += (f'<tr{big}><td class="num">{r["expiry"]}</td><td class="num">{r["dte"]}일 뒤</td>'
                f'<td>{act}</td><td class="num">{r["oi"]:,}개</td>'
                f'<td style="width:36%"><div class="minibar" style="width:{w:.1f}%;background:{color}" '
                f'data-tip="{r["expiry"]} · 쌓인 계약 {r["oi"]:,}개 · 전체의 {r["share"]*100:.1f}%"></div></td></tr>')
    warn = ""
    if op:
        when = ("오늘 밤" if op["dte"] <= 1 else
                ("이번 주" if op["dte"] <= 5 else
                 ("다음 주" if op["dte"] <= 12 else f'{op["dte"]}일 뒤')))
        size = ("아주 큰" if op["share"] >= 0.35 else ("큰" if op["share"] >= 0.2 else "보통 크기의"))
        warn = (f'<div class="callout"><strong>이 표 읽는 법</strong><br>'
                f'가장 큰 만기는 <strong>{op["expiry"]}, {when}</strong>입니다. '
                f'전체의 {op["share"]*100:.0f}%인 {op["oi"]:,}개 계약이 이날 한꺼번에 사라집니다. '
                f'{size} 만기입니다.<br>'
                '만기가 지나면 그 계약들 때문에 증권사가 하던 매매도 같이 없어집니다. '
                '값을 붙잡고 있던 것이든 밀고 있던 것이든, 그 힘이 사라지는 겁니다. '
                '그래서 큰 만기 직후에는 그 전과 다른 움직임이 나오기 쉽습니다. '
                '어느 방향으로 갈지는 이 표가 말해주지 않습니다.</div>')
    return (warn + '<table class="ladder"><thead><tr><th>만기 날짜</th><th>남은 날</th>'
            '<th>그 만기의 증권사 성격</th><th>쌓인 계약</th><th>규모</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>')


def build_term_structure(a):
    term = a.get("iv_term") or []
    em = a.get("expected_move") or []
    if len(term) < 2:
        return "<p class='muted'>만기별 IV 데이터가 부족합니다.</p>"
    W, H, L, R, T, B = 700, 210, 46, 20, 16, 34
    xs_max = max(t["dte"] for t in term) or 1
    ivs = [t["iv"] for t in term]
    lo, hi = min(ivs) * 0.96, max(ivs) * 1.04
    xs = lambda d: L + (d / xs_max) * (W - L - R)
    ys = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="만기별 내재변동성 곡선">']
    for frac in (0.25, 0.5, 0.75):
        gy = T + frac * (H - T - B)
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W-R}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{L-6}" y="{gy+4:.1f}" class="axis" text-anchor="end">{(hi-frac*(hi-lo))*100:.0f}%</text>')
    pts = " ".join(f"{xs(t['dte']):.1f},{ys(t['iv']):.1f}" for t in term)
    parts.append(f'<polyline points="{pts}" class="price-line" fill="none"/>')
    for t in term:
        parts.append(f'<circle cx="{xs(t["dte"]):.1f}" cy="{ys(t["iv"]):.1f}" r="4" class="price-dot" '
                     f'data-tip="{t["expiry"]} (D-{t["dte"]}) · IV {t["iv"]*100:.1f}%"/>')
    for t in (term[0], term[-1]):
        parts.append(f'<text x="{xs(t["dte"]):.1f}" y="{H-8}" class="axis" text-anchor="middle">D-{t["dte"]}</text>')
    parts.append("</svg>")

    bw = a.get("iv_backwardation")
    if bw is None:
        note = ""
    elif bw > 0.01:
        note = (f'<div class="callout"><strong>백워데이션 (+{bw*100:.1f}%p)</strong> — 단기 변동성이 장기보다 비쌉니다. '
                '시장이 임박한 사건을 두려워하고 있다는 뜻이고, 동시에 단기 보호막 값이 이미 비싸다는 뜻이기도 합니다.</div>')
    else:
        note = (f'<div class="callout"><strong>콘탱고 ({bw*100:+.1f}%p)</strong> — 단기가 장기보다 싼 평상시 형태입니다. '
                '임박한 충격을 특별히 걱정하지 않는 상태입니다.</div>')

    trs = "".join(f'<tr><td class="num">{e["expiry"]}</td><td class="num">D-{e["dte"]}</td>'
                  f'<td class="num">±{e["move"]:.2f}</td><td class="num">±{e["pct"]:.2f}%</td></tr>' for e in em)
    tbl = ('<h3 style="font-size:.9rem;margin:16px 0 6px">만기별 기대변동폭</h3>'
           '<table class="ladder"><thead><tr><th>만기</th><th>남은일</th><th>±달러</th><th>±%</th></tr></thead>'
           f'<tbody>{trs}</tbody></table>'
           '<p class="muted">옵션 값이 말하는 도달 범위입니다. 10번 중 6~7번은 이 안에서 끝납니다. '
           '보험이 두껍게 깔린 자리가 이 범위 밖이면, 그 만기 안에는 거기까지 가기 어렵다는 뜻입니다.</p>')
    return note + "".join(parts) + tbl


def build_unusual(a):
    # 특이 거래 탐지: 간밤 거래량이 기존 OI 대비 과도한 계약 (Vol/OI 근사)
    snaps = sorted((BASE / "data" / "snapshots").glob(f"{a['ticker']}_*.csv"))
    cur = pd.read_csv(snaps[-1])
    spot = a["spot"]
    f = cur[(cur["volume"] >= 5000) & (cur["oi"] >= 500) & (cur["volume"] >= 1.5 * cur["oi"])].copy()
    if not len(f):
        return "<p class='muted'>기준(거래량 5,000+ 그리고 기존 OI의 1.5배 이상)을 넘는 특이 거래가 없습니다.</p>"
    f["ratio"] = f["volume"] / f["oi"].clip(lower=1)
    f = f.sort_values("volume", ascending=False).head(10)
    trs = ""
    for _, r in f.iterrows():
        name = "풋" if r["type"] == "P" else "콜"
        color = "var(--put)" if r["type"] == "P" else "var(--call)"
        dist = (r["strike"] - spot) / spot * 100
        trs += (f'<tr><td style="color:{color};font-weight:650">{name}</td><td class="num">{fmt(r["strike"])}</td>'
                f'<td class="num">{r["expiry"]}</td><td class="num">{int(r["volume"]):,}</td>'
                f'<td class="num">{int(r["oi"]):,}</td><td class="num">{r["ratio"]:.1f}x</td>'
                f'<td class="num dist">{dist:+.1f}%</td></tr>')
    # 자동 해석: 콜·풋 어느 쪽이 몇 건인지, 어느 가격대에 몰렸는지
    nc = int((f["type"] == "C").sum())
    npu = len(f) - nc
    near = f[abs(f["strike"] - spot) / spot <= 0.01]
    top = f.iloc[0]
    tname = "오를 때 버는 보험(콜)" if top["type"] == "C" else "내릴 때 버는 보험(풋)"
    side = ("오를 때 버는 쪽(콜)" if nc > npu else ("내릴 때 버는 쪽(풋)" if npu > nc else "양쪽 비슷하게"))
    where = ("지금 가격 바로 근처" if len(near) >= len(f) * 0.5 else "지금 가격에서 떨어진 곳까지 넓게")
    vdate = a.get("volume_date", a["date"])
    when = ("<strong>오늘 지금까지</strong> 거래된 양" if a.get("volume_is_live")
            else f"<strong>{vdate} 하루 동안</strong> 거래된 양")
    lag = ""
    if vdate != a["date"]:
        lag = (f' 여기서 거래량은 {when.replace("<strong>", "").replace("</strong>", "")}이고, '
               f'비교 대상인 계약 수는 {a["date"]} 마감분입니다. '
               f'<strong>즉 "어제까지 깔린 지도 위에서 그 뒤에 어디가 뜨거웠나"를 보는 것입니다.</strong> '
               '거래량은 실시간으로 들어오지만 계약 수는 하루 한 번만 갱신되기 때문입니다.')
    read = (f'<div class="callout"><strong>이 표 읽는 법</strong><br>'
            f'평소보다 유난히 많이 거래된 자리가 {len(f)}곳입니다. '
            f'그중 {nc}곳이 콜, {npu}곳이 풋이라 <strong>{side}</strong>에 더 몰렸습니다. '
            f'위치는 {where} 퍼져 있습니다. '
            f'가장 뜨거운 곳은 <strong>{fmt(top["strike"])}달러 {tname}</strong>으로, '
            f'원래 깔려 있던 것의 <strong>{top["ratio"]:.0f}배</strong>가 거래됐습니다. '
            '이 정도면 원래 있던 사람들끼리 주고받은 걸로는 설명이 안 됩니다. 새 돈이 들어온 자리로 봅니다.'
            + lag + '</div>')
    return (read + '<table class="ladder"><thead><tr><th>종류</th><th>가격</th><th>만기</th>'
            f'<th>{"오늘 거래" if a.get("volume_is_live") else vdate[5:] + " 거래"}</th>'
            '<th>원래 있던 계약</th><th>배수</th><th>지금에서</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
            '<p class="muted">주의 — 많이 거래됐다는 것만 알 뿐, <strong>산 건지 판 건지는 알 수 없습니다.</strong> '
            '진짜 자리를 잡았는지는 다음 날 계약 수가 늘었는지로 확인해야 합니다.</p>')


def build_oi_table(a):
    rows = ""
    for i in range(max(len(a["top_put_oi"]), len(a["top_call_oi"]))):
        p = a["top_put_oi"][i] if i < len(a["top_put_oi"]) else None
        c = a["top_call_oi"][i] if i < len(a["top_call_oi"]) else None
        rows += (f'<tr><td class="num">{fmt(p["strike"]) if p else "-"}</td><td class="num">{fmt(p["oi"], 0) if p else "-"}</td>'
                 f'<td class="num">{fmt(c["strike"]) if c else "-"}</td><td class="num">{fmt(c["oi"], 0) if c else "-"}</td></tr>')
    return ('<details><summary>OI 상위 행사가 표로 보기</summary><table class="ladder"><thead>'
            '<tr><th>풋 행사가</th><th>풋 OI</th><th>콜 행사가</th><th>콜 OI</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></details>')


CSS_JS = """
<style>
:root{color-scheme:light;
 --page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);
 --call:#2a78d6;--put:#e34948;--flip:#4a3aa7;--mp:#eda100;
 --good:#0ca30c;--serious:#ec835a;--crit:#d03b3b;--down:#d03b3b;--up:#006300;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
 --call:#3987e5;--put:#e66767;--flip:#9085e9;--mp:#c98500;--up:#0ca30c;}}
:root[data-theme="dark"]{color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
 --call:#3987e5;--put:#e66767;--flip:#9085e9;--mp:#c98500;--up:#0ca30c;}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif;line-height:1.55}
.wrap{max-width:1060px;margin:0 auto;padding:20px 20px 60px}
.switch{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap}
.tab{display:inline-flex;align-items:baseline;gap:6px;text-decoration:none;
 border:1px solid var(--border);border-radius:999px;padding:7px 15px;
 font-size:.88rem;font-weight:650;color:var(--ink2);background:var(--surface)}
.tab em{font-style:normal;font-weight:400;font-size:.78rem;color:var(--muted)}
.tab:hover{border-color:var(--call);color:var(--call)}
.tab.on{background:var(--ink);color:var(--page);border-color:var(--ink)}
.tab.on em{color:var(--page);opacity:.7}
.tab:focus-visible{outline:2px solid var(--call);outline-offset:2px}
header h1{font-size:1.45rem;margin:0 0 2px;letter-spacing:-.01em}
header .sub{color:var(--ink2);font-size:.88rem}
header .asof{margin-top:10px;font-size:.83rem;color:var(--ink2);background:var(--surface);
 border:1px solid var(--border);border-radius:10px;padding:11px 14px;line-height:1.6;
 display:flex;flex-direction:column;gap:5px}
header .asof strong{color:var(--ink)}
.asof-row{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.asof-tag{flex:none;font-size:.7rem;font-weight:700;border-radius:5px;padding:2px 8px;
 border:1px solid var(--border);letter-spacing:.02em}
.asof-tag.live{color:var(--good);border-color:var(--good)}
.asof-tag.day{color:var(--mp);border-color:var(--mp)}
.asof-when{margin-top:3px;padding-top:7px;border-top:1px solid var(--grid);
 font-size:.8rem;color:var(--muted)}
.asof-when strong{color:var(--ink2)}
.zone-lab{font-size:11px;font-weight:700}
.zone-lab.put{fill:var(--put)}.zone-lab.call{fill:var(--call)}
.flip-lab{font-size:10.5px;font-weight:700;fill:var(--flip)}
.magnet{fill:var(--mp);opacity:.72;stroke:var(--surface);stroke-width:2}
.mag-lab{font-size:10px;fill:var(--muted);font-variant-numeric:tabular-nums}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 12px;
 font-size:.8rem;font-weight:600;border:1px solid var(--border)}
.pill .dot{width:8px;height:8px;border-radius:50%}
.pill.neg{color:var(--serious)}.pill.neg .dot{background:var(--serious)}
.pill.pos{color:var(--good)}.pill.pos .dot{background:var(--good)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:20px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.byline{font-size:.72rem;font-weight:600;color:var(--muted);border:1px solid var(--border);
 border-radius:5px;padding:2px 8px;margin-left:6px;vertical-align:2px}
.tile.wide{grid-column:span 2}
@media (max-width:520px){.tile.wide{grid-column:span 1}}
.tile .k{font-size:.72rem;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.tile .v{font-size:1.32rem;font-weight:650;margin-top:2px}
.tile .s{font-size:.76rem;color:var(--ink2)}
.tile .v.down{color:var(--down)}.tile .v.up{color:var(--up)}
section{margin-top:30px}
section>h2{font-size:1.02rem;margin:0 0 4px}
section>.desc{color:var(--ink2);font-size:.85rem;margin:0 0 12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;overflow-x:auto}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:880px){.duo{grid-template-columns:1fr}}
svg{width:100%;height:auto;display:block}
svg text{font-family:inherit}
.axis,.klabel{font-size:10.5px;fill:var(--muted)}
.klabel{font-variant-numeric:tabular-nums}
.grid{stroke:var(--grid);stroke-width:1}
.axisline{stroke:var(--axis);stroke-width:1.5}
.bar-put{fill:var(--put)}.bar-call{fill:var(--call)}
.bar-put.wall,.bar-call.wall{stroke:var(--ink);stroke-width:1}
[data-tip]:hover{opacity:.8;cursor:default}
.wall-label{font-size:10.5px;font-weight:700}
.wall-label.put{fill:var(--put)}.wall-label.call{fill:var(--call)}
.spotline{stroke:var(--ink);stroke-width:1.2;stroke-dasharray:5 4}
.spot-label,.spotline-label{font-size:11px;font-weight:700;fill:var(--ink)}
.flipline{stroke:var(--flip);stroke-width:1.2;stroke-dasharray:5 4}
.flipline-label{font-size:11px;font-weight:700;fill:var(--flip)}
.price-line{stroke:var(--call);stroke-width:2}
.price-area{fill:var(--call);opacity:.08}
.price-dot{fill:var(--call)}
.lv-call{stroke:var(--call);stroke-width:1.3;stroke-dasharray:6 4}
.lv-put{stroke:var(--put);stroke-width:1.3;stroke-dasharray:6 4}
.lv-flip{stroke:var(--flip);stroke-width:1.3;stroke-dasharray:2 4}
.lv-mp{stroke:var(--mp);stroke-width:1.3;stroke-dasharray:2 4}
.lv-call-t{fill:var(--call)}.lv-put-t{fill:var(--put)}.lv-flip-t{fill:var(--flip)}.lv-mp-t{fill:var(--mp)}
.lv-call-t,.lv-put-t,.lv-flip-t,.lv-mp-t{font-size:10.5px;font-weight:650}
.hs-spot{stroke:var(--ink);stroke-width:2}.hs-spot-dot{fill:var(--ink)}.hs-spot-t{fill:var(--ink)}
.hs-put{stroke:var(--put);stroke-width:2}.hs-put-dot{fill:var(--put)}.hs-put-t{fill:var(--put)}
.hs-call{stroke:var(--call);stroke-width:2}.hs-call-dot{fill:var(--call)}.hs-call-t{fill:var(--call)}
.hs-mp{stroke:var(--mp);stroke-width:2}.hs-mp-dot{fill:var(--mp)}.hs-mp-t{fill:var(--mp)}
.hs-spot-t,.hs-put-t,.hs-call-t,.hs-mp-t{font-size:10.5px;font-weight:650}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.8rem;color:var(--ink2);margin-bottom:8px}
.legend .sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
table.ladder{width:100%;border-collapse:collapse;font-size:.86rem}
table.ladder th{text-align:left;color:var(--muted);font-size:.72rem;letter-spacing:.04em;
 border-bottom:1px solid var(--grid);padding:6px 8px}
table.ladder td{padding:6px 8px;border-bottom:1px solid var(--grid)}
table.ladder tr:last-child td{border-bottom:none}
td.num,th.num{font-variant-numeric:tabular-nums}
td.note{color:var(--ink2);font-size:.8rem}
td.dist{color:var(--muted)}
tr.spot-row td{background:color-mix(in srgb,var(--call) 10%,transparent);font-weight:700}
.chip{display:inline-block;font-size:.7rem;font-weight:600;border-radius:5px;padding:1px 7px;border:1px solid var(--border)}
.chip-opt{color:var(--call);border-color:var(--call)}
.chip-tech{color:var(--ink2)}.chip-ma{color:var(--muted)}
.chip-spot{background:var(--ink);color:var(--page);border-color:var(--ink)}
.prose h3{font-size:1rem;margin:18px 0 6px}
.prose h4{font-size:.9rem;margin:16px 0 6px}
.prose p,.prose li{font-size:.9rem;color:var(--ink2)}
.prose strong{color:var(--ink)}
.prose a{color:var(--call)}
.muted{color:var(--muted);font-size:.82rem}
footer{margin-top:36px;padding-top:14px;border-top:1px solid var(--grid);color:var(--muted);font-size:.78rem}
#tip{position:fixed;z-index:9;pointer-events:none;opacity:0;transition:opacity .12s;
 background:var(--ink);color:var(--page);font-size:.78rem;padding:5px 9px;border-radius:7px;max-width:260px}
details summary{cursor:pointer;color:var(--ink2);font-size:.84rem;margin-top:10px}
.occ-bar{display:flex;height:26px;border-radius:6px;overflow:hidden;gap:2px}
.occ-seg{height:100%}
.minibar{height:11px;border-radius:3px;min-width:2px}
.callout{border-left:3px solid var(--mp);background:color-mix(in srgb,var(--mp) 8%,transparent);
 padding:10px 12px;border-radius:0 8px 8px 0;font-size:.86rem;color:var(--ink2);margin:0 0 12px}
.callout strong{color:var(--ink)}
.intro{background:var(--surface);border:1px solid var(--border);border-radius:12px;
 padding:16px 18px;margin:18px 0 0;display:flex;flex-direction:column;gap:8px}
.intro p{margin:0;font-size:.9rem;color:var(--ink2);line-height:1.6}
.intro strong{color:var(--ink)}
.intro em{font-style:normal;font-weight:650;color:var(--ink)}
.zones{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px}
.zones li{font-size:.87rem;color:var(--ink2);line-height:1.6;display:flex;gap:8px;align-items:flex-start}
.zb{flex:none;width:10px;height:10px;border-radius:3px;margin-top:6px}
.zb.put{background:var(--put)}.zb.call{background:var(--call)}
.alert{display:flex;gap:12px;align-items:flex-start;border-radius:12px;padding:14px 16px;margin-top:14px;
 border:1px solid var(--border)}
.alert.danger{background:color-mix(in srgb,var(--crit) 11%,transparent);border-color:var(--crit)}
.alert.calm{background:color-mix(in srgb,var(--good) 10%,transparent);border-color:var(--good)}
.al-ic{flex:none;font-size:1.3rem;line-height:1.2}
.alert.danger .al-ic{color:var(--crit)}.alert.calm .al-ic{color:var(--good)}
.al-t{font-size:1rem;font-weight:700;color:var(--ink);margin-bottom:4px}
.al-b{font-size:.86rem;color:var(--ink2);line-height:1.65}
.al-b strong{color:var(--ink)}
.note-box{border-left:3px solid var(--border);padding:0 0 0 12px;margin:0 0 14px;
 display:flex;flex-direction:column;gap:5px}
.n-head{margin:0;font-size:.88rem;font-weight:650;color:var(--ink)}
.n-body{margin:0;font-size:.84rem;color:var(--ink2);line-height:1.6}
.n-rows{display:flex;flex-direction:column;gap:3px;font-size:.82rem;color:var(--ink2)}
.n-ar{display:inline-block;width:16px;font-weight:700}
.n-ar.up{color:var(--up)}.n-ar.dn{color:var(--down)}
.n-cav{font-size:.8rem;color:var(--muted);margin-top:2px}
.tile{cursor:help}
.tile-help{background:var(--surface);border:1px solid var(--border);border-radius:10px;
 padding:10px 14px;margin-top:10px}
.tile-help>summary{margin:0;font-weight:600;color:var(--ink)}
.tile-help[open]>summary{margin-bottom:12px}
.th-item{margin:0 0 14px}
.th-item:last-child{margin-bottom:2px}
.th-name{font-size:.8rem;font-weight:700;color:var(--ink);
 letter-spacing:.02em;margin:0 0 4px}
.th-item .note-box{margin:0}
/* 매일 안 보는 것들은 이 안으로 접어둔다 */
.more{margin:34px 0 10px;border:1px solid var(--border);border-radius:12px;
 background:var(--surface);padding:14px 18px}
.more>summary{margin:0;font-weight:700;font-size:1rem;color:var(--ink)}
.more[open]>summary{margin-bottom:6px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.more-body>section:first-child{margin-top:14px}
.asof-fold{margin-top:10px}
.asof-fold>summary{margin:0}
</style>
"""

TIP_JS = """
<script>
(function(){
 var tip=document.getElementById('tip');
 var hoverOK=window.matchMedia&&window.matchMedia('(hover: hover) and (pointer: fine)').matches;
 if(!hoverOK){tip.remove();return;}          // 폰·태블릿에서는 떠 있는 설명을 아예 쓰지 않는다
 function hide(){tip.style.opacity=0;}
 document.querySelectorAll('[data-tip]').forEach(function(el){
  el.addEventListener('mousemove',function(e){
   tip.textContent=el.dataset.tip;tip.style.opacity=1;
   tip.style.left=Math.min(e.clientX+12,window.innerWidth-280)+'px';
   tip.style.top=Math.min(e.clientY+14,window.innerHeight-90)+'px';});
  el.addEventListener('mouseleave',hide);
 });
 window.addEventListener('scroll',hide,{passive:true});
 window.addEventListener('blur',hide);
 document.addEventListener('touchstart',hide,{passive:true});
})();
</script>
"""


def generate(ticker):
    a = json.loads((BASE / "data" / "analytics" / f"{ticker}_latest.json").read_text(encoding="utf-8"))
    snap = pd.read_csv(BASE / "data" / "snapshots" / f"{ticker}_{a['date']}.csv")
    px = pd.read_csv(BASE / "data" / "history" / f"{ticker}_price90.csv")
    hist = pd.read_csv(BASE / "data" / "history" / f"{ticker}_history.csv")
    opath = BASE / "outlook" / f"{ticker}_{a['date']}.md"
    if not opath.exists():
        cands = sorted((BASE / "outlook").glob(f"{ticker}_*.md"))
        opath = cands[-1] if cands else None
    # 전망은 사람이 쓰는 부분이라 언제 쓴 건지 반드시 표시한다
    outlook_badge = ""
    if opath:
        wrote = opath.stem.split("_", 1)[1]
        try:
            age = (datetime.strptime(a["date"], "%Y-%m-%d") - datetime.strptime(wrote, "%Y-%m-%d")).days
        except ValueError:
            age = 0
        if age >= 3:
            outlook_badge = (f'<div class="callout" style="border-left-color:var(--crit)">'
                             f'<strong>{wrote}에 쓴 글입니다 ({age}일 지남).</strong> '
                             '위쪽 숫자와 그래프는 오늘 것으로 자동 갱신되지만, '
                             '이 전망 글은 사람이 써야 해서 최신이 아닙니다. 흐름 참고용으로만 보세요.</div>')
        else:
            outlook_badge = f'<p class="muted" style="margin:0 0 10px">{wrote} 기준으로 쓴 글입니다.</p>'
        outlook = outlook_badge + md_to_html(opath.read_text(encoding="utf-8"))
    else:
        outlook = "<p class='muted'>전망 메모가 아직 없습니다.</p>"

    # 화면을 시황·해석·옵션 세 덩이로 나누므로 전망 글도 둘로 자른다.
    # 첫 '##' 제목(= <h4>)이 경계다. 앞은 지금 상황, 뒤는 앞으로 벌어질 일.
    _cut = outlook.find("<h4>")
    outlook_now = outlook[:_cut] if _cut > 0 else outlook
    outlook_next = outlook[_cut:] if _cut > 0 else ""

    spot = a["spot"]
    closes = px["Close"].tolist()
    chg = a.get("chg_pct")
    if chg is None:
        chg = (closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 else 0
    # 구간 판정은 갈림길 위치가 아니라 '지금 감마의 부호'로 한다.
    # 가격이 크게 움직이면 갈림길이 화면 범위 밖으로 나가 못 잡히는데,
    # 그때 임의로 한쪽으로 표시하면 가장 중요한 지표가 거꾸로 나온다.
    gex_now = a.get("gex_total_bn", 0) or 0
    neg_gamma = gex_now < 0
    flip = a.get("gamma_flip")
    curve = [abs(c["gex_bn"]) for c in (a.get("gex_curve") or [])]
    borderline = bool(curve and abs(gex_now) < max(curve) * 0.2)
    gw = gamma_words(neg_gamma)
    regime_pill = (f'<span class="pill {"neg" if neg_gamma else "pos"}"><span class="dot"></span>'
                   f'증권사는 지금 {gw["short"]}</span>')
    mp = a["max_pain"].get(a["nearest_expiry"])
    move_pct = a["straddle_move"] / spot * 100

    neg_g = neg_gamma
    intro = f"""
<div class="intro">
 <p><strong>이 페이지가 뭐냐면.</strong> 옵션은 주가가 오르거나 내릴 때 돈을 받는 <em>보험</em>입니다.
 <span style="color:var(--call);font-weight:650">콜</span>은 오를 때 버는 보험,
 <span style="color:var(--put);font-weight:650">풋</span>은 내릴 때 버는 보험이에요.
 이 페이지는 <strong>지금 사람들이 어느 가격에, 어느 쪽으로 보험을 걸어놨는지</strong>를 보여줍니다.</p>
 <p><strong>증권사가 하는 일.</strong> 보험을 팔아준 증권사는 손해를 막으려고 주식을 사고팝니다.
 그 방향이 두 가지입니다. 값이 오를 때 <em>같이 사주면</em> 값이 더 오르고, 반대로 <em>팔아버리면</em> 더 못 오릅니다.
 이 규모가 워낙 커서 그날 시장이 얼마나 흔들릴지가 여기서 갈립니다.</p>
 <p><strong>증권사가 하는 일은 두 가지로 갈립니다.</strong>{' 지금 갈리는 지점은 ' + fmt(flip) + '달러입니다.' if flip else ''}</p>
 <ul class="zones">
  <li><span class="zb put"></span><strong>변동성을 키우는 구간.</strong>
   증권사가 오르면 같이 사고, 내리면 같이 팝니다. 같이 밀어주니 <strong>움직임이 커집니다.</strong></li>
  <li><span class="zb call"></span><strong>변동성을 줄이는 구간.</strong>
   증권사가 더 오르면 팔고, 더 내리면 사줍니다. 가려는 쪽을 막으니 <strong>가격이 묶입니다.</strong></li>
 </ul>
 <p><strong>오늘 한 줄.</strong> {a['ticker']}는 {fmt(spot)}달러({chg:+.2f}%)로
 <strong>{gw['name']}</strong>에 있습니다. {gw['effect']}
 다만 <strong>오를지 내릴지는 알려주지 않습니다.</strong> 얼마나 흔들릴지만 알려줍니다.</p>
 <p class="muted">각 칸과 그래프 옆에 "이게 뭐냐면" 설명을 같이 적어뒀습니다.
 요약 칸 설명은 바로 아래 "눌러서 펼치기"를 누르면 나옵니다.</p>
</div>"""

    # 1년치 검증을 통과한 유일한 신호라, 위험 구간이면 맨 위에 크게 띄운다
    if flip:
        gap = abs(spot - flip) / spot * 100
        where = (f'지금 {fmt(spot)}달러는 갈림길({fmt(flip)}) '
                 f'<strong>{"아래" if neg_gamma else "위"}</strong>입니다.')
        edge = (f' 다만 갈림길과 {gap:.1f}%밖에 차이가 안 나서 곧 성격이 바뀔 수 있습니다.'
                if gap < 0.7 else '')
    else:
        where = (f'지금 {fmt(spot)}달러 기준으로 계산한 결과입니다. '
                 '가격이 크게 움직여서 성격이 바뀌는 갈림길은 화면 범위 밖에 있습니다.')
        edge = ''
    if borderline:
        edge += ' 지금은 경계에 가까운 상태라 작은 움직임에도 성격이 뒤집힐 수 있습니다.'

    if neg_gamma:
        alert = (f'<div class="alert danger"><div class="al-ic">⚠</div><div>'
                 f'<div class="al-t">오늘은 크게 움직이기 쉬운 날입니다</div>'
                 f'<div class="al-b">{where} 이 구간에서는 증권사가 오르면 같이 사고 내리면 같이 팔아, '
                 f'움직임이 <strong>한번 시작되면 더 커집니다</strong>. '
                 f'1년치로 채점했을 때 이 구간의 다음날 움직임이 반대 구간의 <strong>2배</strong>였습니다. '
                 f'이 페이지에서 <strong>검증을 통과한 유일한 신호</strong>라 크게 띄웁니다.{edge}</div></div></div>')
    else:
        alert = (f'<div class="alert calm"><div class="al-ic">✓</div><div>'
                 f'<div class="al-t">오늘은 비교적 얌전할 가능성이 큽니다</div>'
                 f'<div class="al-b">{where} 이 구간에서는 증권사가 더 오르면 팔고 더 내리면 사줘서 '
                 f'<strong>가격이 한쪽으로 멀리 가기 어렵습니다</strong>. '
                 f'1년치 검증에서 이 구간의 다음날 움직임이 반대 구간의 <strong>절반</strong>이었습니다.{edge}</div></div></div>')

    T = lambda k: f'data-tip="{esc(tip(k))}"'
    TILE_KEYS = [("price", "지금 가격"), ("walls", "보험이 제일 많이 깔린 곳"),
                 ("gamma_tile", "증권사가 어떻게 사고파나"), ("expected_move", "내일까지 흔들릴 폭"),
                 ("iv_vs_hv", "보험료 비싼 정도"), ("pcr", "내릴 쪽 vs 오를 쪽"),
                 ("zero_dte", "당일치기 비중"), ("max_pain", "만기 자석 가격")]
    tile_help = "".join(note(k) and f'<div class="th-item"><div class="th-name">{esc(nm)}</div>{note(k)}</div>'
                        for k, nm in TILE_KEYS)
    # 맨 위에는 매일 보는 네 칸만 둔다. 나머지 네 칸은 '더 보기' 안으로 내린다.
    tiles = f"""
<div class="tiles">
 <div class="tile" {T('price')}><div class="k">지금 가격</div><div class="v {'down' if chg < 0 else 'up'}">{fmt(spot)}</div><div class="s">{chg:+.2f}% · 어제보다</div></div>
 <div class="tile wide" {T('gamma_tile')}><div class="k">지금 어느 구간인가</div><div class="v {'down' if neg_g else 'up'}" style="font-size:1.12rem">{gw['act']}</div><div class="s">증권사가 {gw['how']}{' · 갈림길 ' + fmt(flip) if flip else ' · 갈림길은 범위 밖'}{' · 경계 근처' if borderline else ''}</div></div>
 <div class="tile wide" {T('expected_move')}><div class="k">{a['nearest_expiry'][5:].replace('-', '/')}까지 갈 만한 범위</div><div class="v" style="font-size:1.16rem">{fmt(spot - a['straddle_move'])} ~ {fmt(spot + a['straddle_move'])}</div><div class="s">지금 {fmt(spot)} · 3번 중 2번은 이 안에서 끝납니다</div></div>
 <div class="tile" {T('walls')}><div class="k">보험이 제일 두꺼운 곳</div><div class="v">{fmt(a['put_wall'], 0)} / {fmt(a['call_wall'], 0)}</div><div class="s">아래쪽 / 위쪽</div></div>
</div>"""
    tiles_more = f"""
<div class="tiles">
 <div class="tile" {T('iv_vs_hv')}><div class="k">보험료 비싼 정도</div><div class="v">{a['atm_iv'] * 100:.1f}%</div><div class="s">실제 흔들림은 {(a.get('hv21') or 0)*100:.1f}%</div></div>
 <div class="tile" {T('pcr')}><div class="k">내릴 쪽 vs 오를 쪽</div><div class="v">{a['pcr_oi']:.2f}</div><div class="s">1보다 크면 내릴 쪽이 많음 · 풋콜비율</div></div>
 <div class="tile" {T('zero_dte')}><div class="k">당일치기 비중</div><div class="v">{(a.get('volume_mix', {}).get('0-1일', 0))*100:.0f}%</div><div class="s">오늘 안에 끝나는 계약 · 0DTE</div></div>
 <div class="tile" {T('max_pain')}><div class="k">옵션 산 사람이 제일 손해 보는 값</div><div class="v">{fmt(mp, 0)}</div><div class="s">{a['nearest_expiry']} 만기 기준</div></div>
</div>
<details class="tile-help"><summary>위 칸들이 각각 무슨 뜻인지 (눌러서 펼치기)</summary>
{tile_help}
</details>"""

    legend_pc = ('<div class="legend"><span><span class="sw" style="background:var(--put)"></span>풋</span>'
                 '<span><span class="sw" style="background:var(--call)"></span>콜</span></div>')
    legend_hist = (
        '<div class="legend"><span><span class="sw" style="background:var(--ink)"></span>주가</span>'
        '<span><span class="sw" style="background:var(--put)"></span>아래 보험벽</span>'
        '<span><span class="sw" style="background:var(--call)"></span>위 보험벽</span>'
        '<span><span class="sw" style="background:var(--mp)"></span>손해최대</span></div>'
        '<p class="muted" style="margin:0 0 10px">각 선이 뜻하는 것 — '
        '<strong>아래 보험벽</strong>은 지금 가격 <em>아래쪽</em>에서 내릴 때 버는 보험(풋)이 제일 두껍게 깔린 가격, '
        '<strong>위 보험벽</strong>은 <em>위쪽</em>에서 오를 때 버는 보험(콜)이 제일 두꺼운 가격입니다. '
        '<strong>손해최대</strong>는 가장 가까운 만기에 <em>옵션을 산 사람들 전체가 가장 많이 잃는 가격</em>입니다. '
        '셋 다 달러 값이고, 주가와 같은 눈금 위에 그려집니다.</p>')
    hist_note = ('<p class="muted">일별 스냅샷이 쌓이면 추세선이 그려집니다. (현재 '
                 f'{len(hist)}일치)</p>' if len(hist) < 3 else "")
    bt = build_backtest()
    bt_section = (f"""<section><h2>이 페이지 말이 맞았나 (성적표)</h2>
 {note('backtest')}
 <div class="card">{bt}</div></section>""" if bt else "")

    body = f"""<title>{ticker} 옵션 대시보드</title>
{CSS_JS}
<div id="tip"></div>
<div class="wrap">
{build_switcher(a['ticker'])}
<header>
 <h1>{ticker} 옵션 대시보드 <span style="font-weight:400;color:var(--ink2);font-size:1rem">나스닥100 ETF</span></h1>
 <div class="sub">{regime_pill}</div>
 <div class="asof">
  <div class="asof-row"><span class="asof-tag live">주가</span>
   {'실시간 (15~20분 지연)' if a.get('spot_is_live') else (a.get('price_date') or a['date']) + ' 장 마감값'}</div>
  <div class="asof-row"><span class="asof-tag live">옵션 거래량</span>
   {'<strong>오늘 지금까지</strong> (실시간)' if a.get('volume_is_live') else '<strong>' + (a.get('volume_date') or a['date']) + '</strong> 하루치'}</div>
  <div class="asof-row"><span class="asof-tag day">옵션 계약 수</span>
   <strong>{a['date']} 장 마감 기준</strong>{' — <strong style="color:var(--serious)">' + str(a['oi_lag_sessions']) + '거래일 뒤처져 있습니다.</strong>' if a.get('oi_lag_sessions', 0) >= 1 else ''}</div>
  <details class="asof-fold"><summary>왜 옵션 숫자만 하루 늦나</summary>
  <div class="asof-when">보험이 얼마나 깔렸는지는 미국 정산소가 밤새 계산해서
   <strong>미 동부 오전 6시 30분(한국 저녁 7시 30분)에 하루 딱 한 번</strong> 발표합니다.
   그래서 장이 끝나도 그날 옵션 숫자는 <strong>다음 날 저녁에야</strong> 나옵니다.
   이 페이지는 <strong>미국장이 열린 동안 15분마다</strong> 자동으로 새로 받습니다.
   새 계약 수가 화면에 들어오는 건 <strong>미국장이 열리는 한국시간 밤 10시 30분 무렵</strong>입니다.<br>
   <strong>거래량은 다릅니다 — 실시간으로 들어옵니다.</strong> 그래서 "평소보다 많이 거래된 자리"를 보면
   계약 수가 갱신되기 전에도 <strong>지금 어디가 뜨거운지</strong> 알 수 있습니다.</div>
  </details>
 </div>
</header>
{alert}
<section><h2>1. 시황 정리</h2>
 {tiles}
 <div class="card prose" style="margin-top:14px">{outlook_now}</div></section>

<section><h2>2. 해석</h2>
 <p class="desc">갈림길을 기준으로 증권사가 하는 일이 뒤집힙니다. 동그라미는 계약이 많이 쌓인 자리입니다.</p>
 <div class="card">{build_zone_map(a, snap)}</div>
 <div class="card prose" style="margin-top:12px">{outlook_next}</div></section>

<section><h2>3. 옵션</h2>
 {note('ladder')}
 <div class="card">{build_ladder(a)}</div>
 <div class="card" style="margin-top:12px">{build_flow_read(a['ticker'], px)}</div>
 <div class="card" style="margin-top:12px">{build_flows(a['ticker'])}</div></section>

<details class="more">
<summary>더 보기 — 자세한 그래프와 표</summary>
<div class="more-body">
{tiles_more}
<section><h2>어느 가격에 보험이 깔렸나</h2>{note('oi_by_strike')}
 <div class="card">{legend_pc}{build_oi_chart(a, snap)}{build_oi_table(a)}</div></section>
<section><h2>이 가격이 되면 증권사가 뭘 하나</h2>
 {note('gamma_tile')}
 <div class="card">{build_gex_curve(a)}
  <details><summary>행사가별로 자세히 보기</summary>{build_gex_chart(a)}</details></div></section>
<section><h2>최근 3개월 가격과 주요 선</h2>
 {note('price_chart')}
 <div class="card">{build_price_chart(a, px)}</div></section>
<section><h2>보험벽이 매일 어디로 옮겨갔나</h2>
 {note('level_history')}
 <div class="card">{build_history_read(hist)}{legend_hist}{build_history_chart(hist)}{hist_note}</div></section>
<section><h2>어제 대비 늘고 준 자리</h2>
 {note('oi_change')}
 <div class="card">{build_oi_change(a)}</div></section>
<section><h2>평소보다 유난히 많이 거래된 자리</h2>
 {note('unusual')}
 <div class="card">{build_unusual(a)}</div></section>
<section><h2>누가 거래했나</h2>
 {note('occ')}
 <div class="card">{build_occ(a)}</div></section>
<section><h2>언제 큰 만기가 오나</h2>
 {note('expiry_gex')}
 <div class="card">{build_expiry_gex(a)}</div></section>
<section><h2>보험료가 언제 제일 비싼가</h2>
 {note('term_structure')}
 <div class="card">{build_term_structure(a)}</div></section>
{bt_section}
<section><h2>이 페이지 읽는 법</h2>
 {intro}</section>
</div></details>
<footer>데이터: 야후 파이낸스 (주가는 15~20분 지연, 보험 계약 수는 하루 한 번 갱신) · 증권사 행동 계산은 표준 공식을 쓴 근사치입니다.<br>
본 대시보드는 정보 제공 목적이며 투자 자문이 아닙니다. 매매 판단과 책임은 이용자 본인에게 있습니다.</footer>
</div>
{TIP_JS}"""
    out = BASE / "dashboard" / f"{ticker}_dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    # 웹으로 올릴 때는 완전한 HTML 문서로 감싸고, 10분마다 스스로 새로고침하게 한다
    page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="refresh" content="600">'
            f'<meta name="description" content="{ticker} 옵션 대시보드 — 자동 갱신">'
            "</head><body>" + body + "</body></html>")
    out.write_text(page, encoding="utf-8")
    print(f"[완료] {out}")
    return out


if __name__ == "__main__":
    for tk in (sys.argv[1:] or ["QQQ"]):
        generate(tk)
