import json, os

tickers = ["QQQ","NVDA","TSLA","AMZN","GOOGL","SOXX","PLTR","CRWV","IREN","IONQ","TEM","EWY"]
fields = ["date","price_date","spot","chg_pct","put_wall","call_wall","gamma_flip",
          "gex_total_bn","max_pain","pcr_oi","atm_iv","opex_biggest","occ","volume_mix",
          "straddle_move","high_52w","low_52w","ma","dex_total_bn","vrp21","hv21","skew_5pct"]

for t in tickers:
    path = f"data/analytics/{t}_latest.json"
    if not os.path.exists(path):
        print(f"=== {t}: MISSING ===")
        continue
    with open(path) as f:
        d = json.load(f)
    print(f"=== {t} ===")
    for k in fields:
        if k in d:
            print(f"{k}: {d[k]}")
    print()
