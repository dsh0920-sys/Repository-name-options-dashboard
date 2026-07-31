# 쌓여 있는 과거 스냅샷에서 주요 가격선(아래·위 보험벽, 손해최대)을 날짜별로 다시 계산해 채우는 스크립트.
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent
TICKERS = ["QQQ", "NVDA", "TSLA", "AMZN", "GOOGL", "SOXX",
           "PLTR", "CRWV", "IREN", "IONQ", "TEM", "EWY"]


def max_pain(df_exp):
    strikes = sorted(df_exp["strike"].unique())
    calls, puts = df_exp[df_exp["type"] == "C"], df_exp[df_exp["type"] == "P"]
    best_k, best = None, None
    for k in strikes:
        pay = (np.maximum(0, k - calls["strike"]) * calls["oi"]).sum() + \
              (np.maximum(0, puts["strike"] - k) * puts["oi"]).sum()
        if best is None or pay < best:
            best_k, best = k, pay
    return best_k


def one(path, day):
    df = pd.read_csv(path)
    if "underlying" in df and df["underlying"].notna().any():
        spot = float(df["underlying"].dropna().iloc[0])
    else:
        return None  # 현물값이 없는 스냅샷은 건너뛴다
    band = df[(df["oi"] > 0) & (df["strike"] >= spot * 0.85) & (df["strike"] <= spot * 1.15)]
    if not len(band):
        return None
    po = band[band["type"] == "P"].groupby("strike")["oi"].sum()
    co = band[band["type"] == "C"].groupby("strike")["oi"].sum()
    pb, ca = po[po.index <= spot], co[co.index >= spot]
    later = [e for e in sorted(df["expiry"].unique()) if e > day]
    mp = max_pain(df[df["expiry"] == later[0]]) if later else None
    return {
        "date": day, "spot": round(spot, 2),
        "put_wall": float(pb.idxmax()) if len(pb) else None,
        "call_wall": float(ca.idxmax()) if len(ca) else None,
        "max_pain_near": float(mp) if mp else None,
        "pcr_oi": round(float(df[df["type"] == "P"]["oi"].sum() / max(1, df[df["type"] == "C"]["oi"].sum())), 3),
    }


for tk in TICKERS:
    rows = []
    for p in sorted((BASE / "data" / "snapshots").glob(f"{tk}_*.csv")):
        day = p.stem.split("_", 1)[1]
        try:
            r = one(p, day)
        except Exception:
            r = None
        if r:
            rows.append(r)
    if not rows:
        print(f"{tk}: 계산할 스냅샷 없음")
        continue

    out = BASE / "data" / "history" / f"{tk}_history.csv"
    new = pd.DataFrame(rows)
    if out.exists():
        old = pd.read_csv(out)
        # 기존 행에만 있는 열(감마 등)은 살리고, 날짜가 겹치면 새로 계산한 값을 쓴다
        merged = pd.concat([old[~old["date"].isin(new["date"])], new])
    else:
        merged = new
    merged.sort_values("date").to_csv(out, index=False)
    print(f"{tk:6} {len(merged)}일치 ({merged['date'].min()} ~ {merged['date'].max()})")
