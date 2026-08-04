import json, sys, os

tickers = ["QQQ","NVDA","TSLA","AMZN","GOOGL","SOXX","PLTR","CRWV","IREN","IONQ","TEM","EWY"]
keys = ['date','price_date','spot','chg_pct','put_wall','call_wall','gamma_flip','gex_total_bn','max_pain','pcr_oi','atm_iv','opex_biggest','occ','volume_mix']

for t in tickers:
    f = f"data/analytics/{t}_latest.json"
    print(f"=== {t} ===")
    if not os.path.exists(f):
        print("NO FILE")
        continue
    d = json.load(open(f))
    for k in keys:
        print(k, ':', d.get(k))
    print()
