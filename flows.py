# 일별 스냅샷을 이어붙여 콜·풋 미결제약정의 유입·이탈(자금 흐름) 시계열을 만드는 계산기.
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
MIN_OI = 25  # 백필분이 OI 25 미만을 안 담아와서, 비교 기준을 양쪽 다 25로 맞춘다


def load(path):
    df = pd.read_csv(path)
    need = {"expiry", "type", "strike", "oi"}
    if not need.issubset(df.columns):
        return None
    df = df[df["oi"] >= MIN_OI]
    return df if len(df) else None


def flow_between(prev, cur):
    # 만기 소멸은 '돈이 빠졌다'가 아니라 '계약이 죽었다'이므로 분리해서 센다
    common = set(prev["expiry"]) & set(cur["expiry"])
    gone = prev[~prev["expiry"].isin(common)]
    out = {
        "call_expired": int(gone[gone["type"] == "C"]["oi"].sum()),
        "put_expired": int(gone[gone["type"] == "P"]["oi"].sum()),
    }
    for t, name in (("C", "call"), ("P", "put")):
        p = prev[(prev["expiry"].isin(common)) & (prev["type"] == t)].groupby(["expiry", "strike"])["oi"].sum()
        c = cur[(cur["expiry"].isin(common)) & (cur["type"] == t)].groupby(["expiry", "strike"])["oi"].sum()
        diff = c.sub(p, fill_value=0)
        out[f"{name}_in"] = int(diff[diff > 0].sum())      # 새로 걸린 계약
        out[f"{name}_out"] = int(-diff[diff < 0].sum())    # 빠져나간 계약
        out[f"{name}_net"] = out[f"{name}_in"] - out[f"{name}_out"]
        out[f"{name}_total"] = int(c.sum())
    return out


def run(ticker):
    files = sorted((BASE / "data" / "snapshots").glob(f"{ticker}_*.csv"))
    outpath = BASE / "data" / "history" / f"{ticker}_flows.csv"
    done = set()
    if outpath.exists():
        old = pd.read_csv(outpath)
        done = set(old["date"])
    else:
        old = pd.DataFrame()

    rows = []
    prev_df = prev_day = prev_path = None
    for f in files:
        day = f.stem.split("_", 1)[1]
        if day in done:
            # 이미 계산된 날은 파일을 안 읽되, 다음 날의 비교 대상이 되도록 경로만 기억한다
            prev_df, prev_day, prev_path = None, day, f
            continue
        cur = load(f)
        if cur is None:
            continue
        if prev_df is None and prev_path is not None:
            prev_df = load(prev_path)
        if prev_df is not None:
            r = flow_between(prev_df, cur)
            r["date"], r["prev_date"] = day, prev_day
            rows.append(r)
        prev_df, prev_day, prev_path = cur, day, f

    if rows:
        new = pd.DataFrame(rows)
        allrows = pd.concat([old, new]) if len(old) else new
        allrows = allrows.drop_duplicates(subset="date", keep="last").sort_values("date")
        cols = ["date", "prev_date", "call_in", "call_out", "call_net", "call_expired", "call_total",
                "put_in", "put_out", "put_net", "put_expired", "put_total"]
        allrows[[c for c in cols if c in allrows]].to_csv(outpath, index=False)
        print(f"[완료] {ticker} 흐름 {len(allrows)}일치 (이번에 새로 {len(rows)}일)")
    else:
        print(f"[완료] {ticker} 새로 계산할 구간 없음")


if __name__ == "__main__":
    for tk in (sys.argv[1:] or ["QQQ"]):
        run(tk)
