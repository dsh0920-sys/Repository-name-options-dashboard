import json, os

tickers = ["QQQ","NVDA","TSLA","AMZN","GOOGL","SOXX","PLTR","CRWV","IREN","IONQ","TEM","EWY"]
keys = ['date','price_date','spot','chg_pct','put_wall','call_wall','gamma_flip','gex_total_bn','max_pain','pcr_oi','atm_iv','opex_biggest','occ','volume_mix']

base = os.path.dirname(__file__)
for t in tickers:
    print(f"=== {t} ===")
    path = os.path.join(base, f"{t}_latest.json")
    if not os.path.exists(path):
        print("NO FILE")
        continue
    d = json.load(open(path))
    for k in keys:
        print(k, ':', d.get(k))
    flows_path = os.path.join(base, "..", "history", f"{t}_flows.csv")
    if os.path.exists(flows_path):
        lines = open(flows_path).read().strip().split("\n")
        print("--- flows tail ---")
        for l in lines[-4:]:
            print(l)
    print()
