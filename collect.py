# 나스닥 종목 옵션체인·가격을 수집해 일별 스냅샷을 쌓고 풋월·콜월·맥스페인·GEX·지지저항을 계산하는 수집기.
import io
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

BASE = Path(__file__).parent
TICKERS = ["QQQ"]
RISK_FREE = 0.04  # 감마 계산용 근사 무위험금리
OCC_URL = "https://marketdata.theocc.com/volume-query"


def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_delta(spot, strike, iv, t_years, is_call):
    if iv <= 0.01 or t_years <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0


def bs_gamma(spot, strike, iv, t_years):
    if iv <= 0.01 or t_years <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
    return norm_pdf(d1) / (spot * iv * math.sqrt(t_years))


def pick_expirations(expirations, today):
    # 14일 내 전부 + 60일 내 금요일 + 120일 내 셋째주 금요일, 최대 16개
    picked = []
    for e in expirations:
        d = datetime.strptime(e, "%Y-%m-%d").date()
        dte = (d - today).days
        if dte < 0 or dte > 120:
            continue
        is_friday = d.weekday() == 4
        is_third_friday = is_friday and 15 <= d.day <= 21
        if dte <= 14 or (dte <= 60 and is_friday) or is_third_friday:
            picked.append(e)
    return picked[:16]


def clean(v, cast=float):
    # 야후 데이터의 NaN·None을 0으로 정리
    try:
        f = float(v)
        return cast(f) if not math.isnan(f) else cast(0)
    except (TypeError, ValueError):
        return cast(0)


def fetch_chain(ticker_obj, expiry, today):
    chain = ticker_obj.option_chain(expiry)
    rows = []
    for opt_type, df in (("C", chain.calls), ("P", chain.puts)):
        for _, r in df.iterrows():
            rows.append({
                "expiry": expiry,
                "type": opt_type,
                "strike": clean(r.get("strike")),
                "oi": clean(r.get("openInterest"), int),
                "volume": clean(r.get("volume"), int),
                "iv": clean(r.get("impliedVolatility")),
                "last": clean(r.get("lastPrice")),
                "bid": clean(r.get("bid")),
                "ask": clean(r.get("ask")),
            })
    return rows


def max_pain(df_exp):
    strikes = sorted(df_exp["strike"].unique())
    best_k, best_pay = None, None
    for k in strikes:
        calls = df_exp[df_exp["type"] == "C"]
        puts = df_exp[df_exp["type"] == "P"]
        pay = (np.maximum(0, k - calls["strike"]) * calls["oi"]).sum() + \
              (np.maximum(0, puts["strike"] - k) * puts["oi"]).sum()
        if best_pay is None or pay < best_pay:
            best_k, best_pay = k, pay
    return best_k


def occ_one(ticker, ymd, porc):
    params = {"reportDate": ymd, "format": "csv", "volumeQueryType": "O", "symbolType": "O",
              "symbol": ticker, "reportType": "D", "accountType": "ALL",
              "productKind": "OSTK", "porc": porc}
    r = requests.get(OCC_URL, params=params, timeout=30)
    r.raise_for_status()
    # 각 행 끝에 쉼표가 하나 더 붙어 있어 index_col=False로 고정해야 컬럼이 안 밀린다
    df = pd.read_csv(io.StringIO(r.text), index_col=False)
    if "actype" not in df or not len(df):
        return None
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    return df


def fetch_occ(ticker, trade_date):
    # OCC 계좌유형별 거래량: C=고객, F=증권사 자기매매, M=마켓메이커
    # 해당 일자가 아직 공표 전이면 최대 4영업일 뒤로 물러나며 탐색
    d0 = datetime.strptime(trade_date, "%Y-%m-%d").date()
    used, frames = None, {}
    for back in range(5):
        d = d0 - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        try:
            c = occ_one(ticker, d.strftime("%Y%m%d"), "C")
            p = occ_one(ticker, d.strftime("%Y%m%d"), "P")
        except Exception:
            continue
        if c is not None and p is not None:
            used, frames = d.strftime("%Y-%m-%d"), {"call": c, "put": p}
            break
    if not used:
        raise RuntimeError("최근 5일 내 OCC 데이터를 찾지 못함")

    out = {"as_of": used, "stale": used != trade_date}
    for name, df in frames.items():
        g = df.groupby("actype")["quantity"].sum()
        for code, label in (("C", "customer"), ("F", "firm"), ("M", "market_maker")):
            out[f"{name}_{label}"] = int(g.get(code, 0))
    total = sum(v for k, v in out.items() if isinstance(v, int)) or 1
    out["customer_share"] = round((out["call_customer"] + out["put_customer"]) / total, 4)
    out["firm_share"] = round((out["call_firm"] + out["put_firm"]) / total, 4)
    cust = out["call_customer"] + out["put_customer"]
    out["customer_pcr"] = round(out["put_customer"] / max(1, out["call_customer"]), 3)
    out["firm_pcr"] = round(out["put_firm"] / max(1, out["call_firm"]), 3)
    out["customer_total"] = cust
    out["firm_total"] = out["call_firm"] + out["put_firm"]
    out["mm_total"] = out["call_market_maker"] + out["put_market_maker"]
    return out


def atm_strike(sub, spot):
    # 콜·풋이 모두 있고, 실제로 값이 붙어 있는(호가나 미결제약정이 있는) 행사가만 후보로 쓴다.
    # 텅 빈 행사가를 잡으면 내재변동성·기대변동폭이 통째로 엉킨다.
    live = sub[(sub["oi"] > 0) | ((sub["bid"] > 0) & (sub["ask"] > 0))]
    for cand in (live, sub):
        both = set(cand[cand["type"] == "C"]["strike"]) & set(cand[cand["type"] == "P"]["strike"])
        if both:
            return min(both, key=lambda k: abs(k - spot))
    return None


def clean_iv(series):
    """말이 되는 범위의 내재변동성만 남긴다 (0.00001 같은 쓰레기 값 제거)."""
    s = pd.to_numeric(series, errors="coerce")
    return s[(s >= 0.03) & (s <= 3.0)]


def bs_price(spot, strike, sig, t_years, is_call):
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * sig * sig) * t_years) / (sig * math.sqrt(t_years))
    d2 = d1 - sig * math.sqrt(t_years)
    disc = math.exp(-RISK_FREE * t_years)
    call = spot * norm_cdf(d1) - strike * disc * norm_cdf(d2)
    return call if is_call else call - spot + strike * disc


def solve_iv(price, spot, strike, t_years, is_call):
    """옵션 값에서 내재변동성을 직접 역산한다.
    야후가 주는 iv 필드는 계산이 실패하면 0.5·0.25·0.125 같은 값을 그대로 뱉으므로 믿을 수 없다."""
    if price <= 0 or t_years <= 0 or spot <= 0 or strike <= 0:
        return None
    intrinsic = max(0.0, spot - strike) if is_call else max(0.0, strike - spot)
    if price <= intrinsic + 1e-6:
        return None
    lo, hi = 0.01, 3.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs_price(spot, strike, mid, t_years, is_call) > price:
            hi = mid
        else:
            lo = mid
    iv = 0.5 * (lo + hi)
    return iv if 0.02 < iv < 2.9 else None


def atm_iv_from_prices(atm, spot, strike, t_years):
    """ATM 콜·풋 값에서 각각 변동성을 역산해 평균낸다."""
    vals = []
    for _, r in atm.iterrows():
        px = (r["bid"] + r["ask"]) / 2 if (r["bid"] > 0 and r["ask"] > 0) else r["last"]
        v = solve_iv(px, spot, strike, t_years, r["type"] == "C")
        if v:
            vals.append(v)
    return float(np.mean(vals)) if vals else None


def mid_price(sub):
    # 체결가(last)는 오래된 값이 섞이므로 호가 중간값을 우선 사용
    ok = sub[(sub["bid"] > 0) & (sub["ask"] > 0) & (sub["ask"] >= sub["bid"])]
    if len(ok):
        return float(((ok["bid"] + ok["ask"]) / 2).sum())
    return float(sub["last"].sum())


def realized_vol(hist, days):
    r = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    if len(r) < days:
        return None
    return round(float(r.tail(days).std() * math.sqrt(252)), 4)


def extra_metrics(df, hist, spot, today):
    # 새 데이터 없이 체인만으로 뽑는 2차 지표들
    d = df[(df["oi"] > 0) & (df["iv"] >= 0.03) & (df["iv"] <= 2.0)].copy()
    d["dte"] = d["expiry"].map(lambda e: max(0, (datetime.strptime(e, "%Y-%m-%d").date() - today).days))
    d["t"] = d["dte"].clip(lower=0.5) / 365.0
    d["delta"] = [bs_delta(spot, r.strike, r.iv, r.t, r.type == "C") for r in d.itertuples()]

    # 딜러 델타 노출(DEX): 고객이 콜·풋을 순매수했다고 보고 딜러는 그 반대라 가정
    d["dex"] = -d["delta"] * d["oi"] * 100 * spot
    dex_total = float(d["dex"].sum())

    # 만기별 GEX 분해 + OPEX 소멸 캘린더
    d["gamma"] = [bs_gamma(spot, r.strike, r.iv, r.t) for r in d.itertuples()]
    sign = np.where(d["type"] == "C", 1.0, -1.0)
    d["gex"] = d["gamma"] * d["oi"] * 100 * spot * spot * 0.01 * sign
    by_exp = d.groupby("expiry").agg(gex=("gex", "sum"), oi=("oi", "sum"), dte=("dte", "first"))
    by_exp["abs_gex"] = by_exp["gex"].abs()
    total_abs = by_exp["abs_gex"].sum() or 1
    expiry_gex = [{"expiry": e, "dte": int(r.dte), "gex_bn": round(r.gex / 1e9, 3),
                   "oi": int(r.oi), "share": round(r.abs_gex / total_abs, 4)}
                  for e, r in by_exp.sort_values("dte").iterrows()]
    biggest = by_exp.sort_values("abs_gex", ascending=False).head(1)
    opex = {"expiry": biggest.index[0], "dte": int(biggest["dte"].iloc[0]),
            "share": round(float(biggest["abs_gex"].iloc[0] / total_abs), 4),
            "oi": int(biggest["oi"].iloc[0])}

    # 만기별 ATM IV(텀 스트럭처)와 기대변동폭(스트래들)
    term, emove = [], []
    for e, sub in df.groupby("expiry"):
        dte = (datetime.strptime(e, "%Y-%m-%d").date() - today).days
        if dte < 0:
            continue
        atm_k = atm_strike(sub, spot)
        if atm_k is None:
            continue
        atm = sub[sub["strike"] == atm_k]
        iv = atm_iv_from_prices(atm, spot, atm_k, max(0.5, dte) / 365.0)
        if iv is None:
            ivs = clean_iv(atm["iv"])
            iv = float(ivs.median()) if len(ivs) else 0.0
        strad = mid_price(atm[atm["type"] == "C"]) + mid_price(atm[atm["type"] == "P"])
        if iv > 0:
            term.append({"expiry": e, "dte": dte, "iv": round(iv, 4)})
        if strad > 0:
            emove.append({"expiry": e, "dte": dte, "move": round(strad, 2),
                          "pct": round(strad / spot * 100, 2)})
    term.sort(key=lambda x: x["dte"])
    emove.sort(key=lambda x: x["dte"])
    # 백워데이션 = 단기 IV가 장기보다 높음 (임박한 충격을 두려워하는 상태)
    backwardation = None
    if len(term) >= 2:
        near = [t["iv"] for t in term if t["dte"] <= 10]
        far = [t["iv"] for t in term if t["dte"] >= 45]
        if near and far:
            backwardation = round(float(np.mean(near) - np.mean(far)), 4)

    # 만기 구간별 거래량 비중 (0DTE 쏠림 감지)
    dfv = df.copy()
    dfv["dte"] = dfv["expiry"].map(lambda e: (datetime.strptime(e, "%Y-%m-%d").date() - today).days)
    vt = dfv["volume"].sum() or 1
    buckets = {"0-1일": (0, 1), "2-7일": (2, 7), "8-30일": (8, 30), "31일+": (31, 9999)}
    vol_mix = {k: round(float(dfv[(dfv["dte"] >= lo) & (dfv["dte"] <= hi)]["volume"].sum() / vt), 4)
               for k, (lo, hi) in buckets.items()}

    # 달러(프리미엄) 가중 PCR — 계약수 PCR이 못 보는 '투입 자금' 기준
    dfv["prem"] = dfv["last"] * dfv["volume"] * 100
    pc = dfv[dfv["type"] == "C"]["prem"].sum()
    pp = dfv[dfv["type"] == "P"]["prem"].sum()
    pcr_dollar = round(float(pp / max(1.0, pc)), 3)

    # IV vs 실현변동성 갭 (변동성 리스크 프리미엄)
    atm_near = term[0]["iv"] if term else 0
    hv10, hv21 = realized_vol(hist, 10), realized_vol(hist, 21)

    return {
        "dex_total_bn": round(dex_total / 1e9, 2),
        "expiry_gex": expiry_gex, "opex_biggest": opex,
        "iv_term": term[:10], "expected_move": emove[:6],
        "iv_backwardation": backwardation,
        "volume_mix": vol_mix, "pcr_dollar": pcr_dollar,
        "hv10": hv10, "hv21": hv21,
        "vrp10": round(atm_near - hv10, 4) if hv10 else None,
        "vrp21": round(atm_near - hv21, 4) if hv21 else None,
    }


def swing_levels(hist, spot):
    # 1년 일봉에서 스윙 고저점을 뽑아 0.6% 이내로 묶고 터치 횟수·최근성으로 점수화
    highs, lows = hist["High"].values, hist["Low"].values
    n = len(hist)
    points = []
    for i in range(2, n - 2):
        if highs[i] == max(highs[i - 2:i + 3]):
            points.append((highs[i], i))
        if lows[i] == min(lows[i - 2:i + 3]):
            points.append((lows[i], i))
    points.sort()
    clusters = []
    for price, idx in points:
        if clusters and abs(price - clusters[-1]["price"]) / clusters[-1]["price"] < 0.006:
            c = clusters[-1]
            c["touches"] += 1
            c["price"] = (c["price"] * (c["touches"] - 1) + price) / c["touches"]
            c["last_idx"] = max(c["last_idx"], idx)
        else:
            clusters.append({"price": price, "touches": 1, "last_idx": idx})
    for c in clusters:
        c["score"] = c["touches"] * 2 + (c["last_idx"] / n) * 3
    supports = sorted([c for c in clusters if c["price"] < spot], key=lambda c: -c["score"])[:4]
    resistances = sorted([c for c in clusters if c["price"] >= spot], key=lambda c: -c["score"])[:4]
    fmt = lambda cs: [{"price": round(c["price"], 2), "touches": c["touches"]} for c in
                      sorted(cs, key=lambda c: c["price"])]
    return fmt(supports), fmt(resistances)


def analyze(ticker, df, hist, spot, today_str):
    near = df[df["oi"] > 0]
    band = near[(near["strike"] >= spot * 0.85) & (near["strike"] <= spot * 1.15)]

    put_oi = band[band["type"] == "P"].groupby("strike")["oi"].sum()
    call_oi = band[band["type"] == "C"].groupby("strike")["oi"].sum()
    # 관례: 풋월 = 현물 이하 최대 풋 OI(지지), 콜월 = 현물 이상 최대 콜 OI(저항)
    put_below = put_oi[put_oi.index <= spot]
    call_above = call_oi[call_oi.index >= spot]
    put_wall = float(put_below.idxmax()) if len(put_below) else None
    call_wall = float(call_above.idxmax()) if len(call_above) else None

    pcr_oi = round(near[near["type"] == "P"]["oi"].sum() / max(1, near[near["type"] == "C"]["oi"].sum()), 3)
    pcr_vol = round(df[df["type"] == "P"]["volume"].sum() / max(1, df[df["type"] == "C"]["volume"].sum()), 3)

    # GEX: 감마 * OI * 100 * S^2 * 1% (콜 +, 풋 -), 스파이크 방지로 IV 5%~200%만
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    g = band[(band["iv"] >= 0.05) & (band["iv"] <= 2.0) & (band["oi"] > 0)].copy()
    gex_by_strike, gamma_flip, gex_total, gex_curve = {}, None, 0.0, []
    if len(g):
        dte = g["expiry"].map(lambda e: max(0.5, (datetime.strptime(e, "%Y-%m-%d").date() - today).days))
        t_arr = dte.values / 365.0
        k_arr, iv_arr = g["strike"].values, g["iv"].values
        sign = np.where(g["type"].values == "C", 1.0, -1.0)
        oi_arr = g["oi"].values

        def total_gex(s):
            d1 = (np.log(s / k_arr) + (RISK_FREE + 0.5 * iv_arr ** 2) * t_arr) / (iv_arr * np.sqrt(t_arr))
            gamma = np.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi) / (s * iv_arr * np.sqrt(t_arr))
            return gamma * oi_arr * 100 * s * s * 0.01 * sign

        per = total_gex(spot)
        gex_total = float(per.sum())
        gs = pd.Series(per).groupby(k_arr).sum().sort_index()
        gex_by_strike = {str(k): round(v / 1e9, 3) for k, v in gs.items()}

        # 감마 플립: 현물을 ±15% 움직여가며 총 GEX 부호가 바뀌는 레벨 탐색
        grid = np.linspace(spot * 0.85, spot * 1.15, 121)
        totals = np.array([total_gex(s).sum() for s in grid])
        crossings = np.where(np.sign(totals[:-1]) != np.sign(totals[1:]))[0]
        if len(crossings):
            i = crossings[np.argmin(abs(grid[crossings] - spot))]
            x0, x1, y0, y1 = grid[i], grid[i + 1], totals[i], totals[i + 1]
            gamma_flip = round(float(x0 - y0 * (x1 - x0) / (y1 - y0)), 2)
        # "이 가격이 되면 증권사가 어떻게 행동하나" 곡선 (대시보드 표시용, ±10% 구간만)
        keep = (grid >= spot * 0.90) & (grid <= spot * 1.10)
        gex_curve = [{"price": round(float(p), 2), "gex_bn": round(float(v) / 1e9, 3)}
                     for p, v in zip(grid[keep], totals[keep])]

    # 만기별 맥스페인 (최근접 + OI 최대 만기)
    expiries = sorted(df["expiry"].unique())
    nearest = expiries[0]
    biggest = df.groupby("expiry")["oi"].sum().idxmax()
    mp = {e: float(max_pain(df[df["expiry"] == e])) for e in {nearest, biggest}}

    # ATM IV·기대변동폭 (최근접 만기 스트래들)
    ne = df[df["expiry"] == nearest]
    atm_k = atm_strike(ne, spot) or float(ne.iloc[(ne["strike"] - spot).abs().argsort()]["strike"].iloc[0])
    atm = ne[ne["strike"] == atm_k]
    near_dte = max(0.5, (datetime.strptime(nearest, "%Y-%m-%d").date() - today).days)
    atm_iv = atm_iv_from_prices(atm, spot, atm_k, near_dte / 365.0)
    if atm_iv is None:  # 역산이 안 되면 야후 값 중 말이 되는 것으로 대체
        iv_ok = clean_iv(atm["iv"])
        atm_iv = float(iv_ok.median()) if len(iv_ok) else 0.0
    straddle = mid_price(atm[atm["type"] == "C"]) + mid_price(atm[atm["type"] == "P"])

    # OTM 5% 스큐
    def iv_near(target, opt_type):
        sub = near[(near["type"] == opt_type) & (near["iv"] > 0.03)]
        if not len(sub):
            return None
        return float(sub.iloc[(sub["strike"] - target).abs().argsort()]["iv"].iloc[0])
    put_iv, call_iv = iv_near(spot * 0.95, "P"), iv_near(spot * 1.05, "C")
    skew = round(put_iv - call_iv, 4) if put_iv and call_iv else None

    extra = extra_metrics(df, hist, spot, today)

    occ = None
    try:
        occ = fetch_occ(ticker, today_str)
    except Exception as ex:
        print(f"  [경고] OCC 계좌유형별 거래량 수집 실패: {ex}")

    supports, resistances = swing_levels(hist, spot)
    ma = {f"MA{w}": round(float(hist["Close"].rolling(w).mean().iloc[-1]), 2) for w in (20, 50, 200) if len(hist) >= w}

    top = lambda s: [{"strike": float(k), "oi": int(v)} for k, v in s.sort_values(ascending=False).head(7).items()]
    return {
        "ticker": ticker, "date": today_str, "spot": round(spot, 2),
        "put_wall": put_wall, "call_wall": call_wall,
        "top_put_oi": top(put_oi), "top_call_oi": top(call_oi),
        "pcr_oi": pcr_oi, "pcr_vol": pcr_vol,
        "max_pain": mp, "nearest_expiry": nearest, "biggest_oi_expiry": biggest,
        "atm_iv": round(atm_iv, 4), "straddle_move": round(straddle, 2),
        "skew_5pct": skew,
        "gex_total_bn": round(gex_total / 1e9, 2), "gamma_flip": gamma_flip,
        "gex_by_strike_bn": gex_by_strike, "gex_curve": gex_curve,
        "supports": supports, "resistances": resistances, "ma": ma,
        "high_52w": round(float(hist["High"].max()), 2), "low_52w": round(float(hist["Low"].min()), 2),
        "expirations_used": expiries,
        "occ": occ, **extra,
    }


def run(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"{ticker} 가격 이력 조회 실패")

    # 옵션 호가는 항상 '현재' 값이므로, 현물도 같은 시점 값을 쓴다.
    spot = float(hist["Close"].iloc[-1])
    et_now = datetime.now(timezone.utc) - timedelta(hours=4)  # 서머타임 기준 ET
    live = hist.index[-1].strftime("%Y-%m-%d") == et_now.strftime("%Y-%m-%d") and et_now.hour < 16

    # 스냅샷 라벨은 반드시 'OI가 속한 거래일'이어야 한다.
    # 미결제약정은 OCC가 밤새 정산해 OPRA가 미 동부 06:30에 배포하므로,
    # 지금 받는 OI는 '가장 최근 06:30 경계' 직전에 끝난 거래일의 마감분이다.
    # (예: ET 7/30 18:00에 받는 OI는 7/30이 아니라 7/29 마감분)
    boundary = et_now.date() if (et_now.hour, et_now.minute) >= (6, 30) else et_now.date() - timedelta(days=1)
    sessions = [d.strftime("%Y-%m-%d") for d in hist.index]
    older = [d for d in sessions if d < boundary.strftime("%Y-%m-%d")]
    if not older:
        raise RuntimeError(f"{ticker} OI 기준 거래일을 정할 수 없음")
    trade_date = older[-1]

    # 등락률은 '직전 거래일 대비'여야 한다. OI 기준일과는 무관하게 계산한다.
    closes = hist["Close"]
    prev_close = float(closes.iloc[-1] if live else closes.iloc[-2] if len(closes) >= 2 else closes.iloc[-1])
    if live:
        print(f"  [안내] 장중 실행 — 현물은 실시간 {spot:.2f}, 옵션 숫자는 {trade_date} 마감 기준입니다.")
    elif sessions[-1] != trade_date:
        print(f"  [안내] 주가는 {sessions[-1]} 마감({spot:.2f}), 옵션 숫자는 아직 {trade_date} 마감 기준입니다.")
        print("         옵션 계약 수는 미 동부 06:30(한국 19:30)에 하루 한 번 갱신됩니다.")

    today = datetime.now(timezone.utc).date()
    exps = pick_expirations(t.options, today)
    if not exps:
        raise RuntimeError(f"{ticker} 만기 목록 조회 실패")
    rows = []
    for e in exps:
        try:
            rows += fetch_chain(t, e, today)
            time.sleep(0.3)
        except Exception as ex:
            print(f"  [경고] {e} 만기 수집 실패: {ex}")
    df = pd.DataFrame(rows)

    # 안전장치 — 미 동부 06:30 배포 직전 몇 시간 동안 야후는 계약 수를 통째로 0으로 비운다.
    # 그 상태로 저장하면 풋월·콜월이 사라지고 흐름 이력이 영구히 오염되므로 저장하지 않는다.
    filled = (df["oi"] > 0).mean() if len(df) else 0
    if filled < 0.15:
        raise RuntimeError(
            f"{ticker} 계약 수가 비어 있습니다 (OI 있는 계약 {filled:.0%}). "
            f"지금은 미 동부 {et_now:%H:%M} — 계약 수는 미 동부 06:30(한국 19:30)에 발표됩니다. "
            "그 이후에 다시 실행하세요. 저장하지 않았습니다.")

    snap_path = BASE / "data" / "snapshots" / f"{ticker}_{trade_date}.csv"
    df.insert(0, "date", trade_date)
    df.insert(0, "ticker", ticker)
    df.to_csv(snap_path, index=False)

    result = analyze(ticker, df, hist, spot, trade_date)
    result["spot_is_live"] = bool(live)
    result["prev_close"] = round(prev_close, 2)
    result["chg_pct"] = round((spot / prev_close - 1) * 100, 2)
    result["price_date"] = hist.index[-1].strftime("%Y-%m-%d")  # 주가 기준일
    result["oi_lag_sessions"] = sum(1 for d in hist.index.strftime("%Y-%m-%d") if d > trade_date)
    # 거래량은 OI와 달리 실시간으로 들어온다. 장중이면 '오늘 지금까지', 아니면 마지막 세션 전체.
    result["volume_date"] = result["price_date"]
    result["volume_is_live"] = bool(live)
    apath = BASE / "data" / "analytics" / f"{ticker}_{trade_date}.json"
    apath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "data" / "analytics" / f"{ticker}_latest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 기간별 추적용 히스토리 한 줄 추가 (같은 날짜는 갱신)
    hrow = {k: result.get(k) for k in
            ("date", "spot", "put_wall", "call_wall", "pcr_oi", "pcr_vol", "atm_iv", "gex_total_bn",
             "gamma_flip", "dex_total_bn", "pcr_dollar", "vrp21", "iv_backwardation")}
    hrow["max_pain_near"] = result["max_pain"].get(result["nearest_expiry"])
    if result.get("occ"):
        hrow["occ_customer_pcr"] = result["occ"]["customer_pcr"]
        hrow["occ_firm_share"] = result["occ"]["firm_share"]
    hpath = BASE / "data" / "history" / f"{ticker}_history.csv"
    hdf = pd.read_csv(hpath) if hpath.exists() else pd.DataFrame()
    hdf = pd.concat([hdf[hdf["date"] != trade_date] if len(hdf) else hdf, pd.DataFrame([hrow])])
    hdf.sort_values("date").to_csv(hpath, index=False)

    # 최근 90일 가격도 대시보드용으로 저장
    px = hist.tail(90)[["Open", "High", "Low", "Close", "Volume"]].reset_index()
    px["Date"] = px["Date"].dt.strftime("%Y-%m-%d")
    px.to_csv(BASE / "data" / "history" / f"{ticker}_price90.csv", index=False)

    print(f"[완료] {ticker} {trade_date} | 현물 {spot:.2f} | 계약 {len(df)}건 | 만기 {len(exps)}개")
    print(f"  풋월 {result['put_wall']} / 콜월 {result['call_wall']} / 맥스페인 {hrow['max_pain_near']} / PCR(OI) {result['pcr_oi']}")
    return result


if __name__ == "__main__":
    tickers = sys.argv[1:] or TICKERS
    for tk in tickers:
        run(tk)
