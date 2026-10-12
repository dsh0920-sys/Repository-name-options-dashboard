import json, os
tickers = ['QQQ','NVDA','TSLA','AMZN','GOOGL','SOXX','PLTR','CRWV','IREN','IONQ','TEM','EWY']
keys=['date','price_date','spot','chg_pct','put_wall','call_wall','gamma_flip','gex_total_bn','max_pain','pcr_oi','atm_iv','opex_biggest','occ','volume_mix']
base = os.path.dirname(__file__)
for t in tickers:
    fn = os.path.join(base, f"{t}_latest.json")
    if not os.path.exists(fn):
        print(f"=== {t} === MISSING")
        continue
    with open(fn) as f:
        d = json.load(f)
    print(f"=== {t} ===")
    for k in keys:
        print(f"  {k} = {d.get(k)}")
