import json, os

tickers = ['QQQ','NVDA','TSLA','AMZN','GOOGL','SOXX','PLTR','CRWV','IREN','IONQ','TEM','EWY']
keys = ['date','price_date','spot','chg_pct','put_wall','call_wall','gamma_flip','gex_total_bn','max_pain','pcr_oi','atm_iv','opex_biggest','occ','volume_mix']

base = os.path.dirname(os.path.abspath(__file__))

for t in tickers:
    path = os.path.join(base, f'{t}_latest.json')
    print(f'=== {t} ===')
    if not os.path.exists(path):
        print('NO FILE')
        continue
    with open(path) as f:
        d = json.load(f)
    for k in keys:
        print(k, ':', d.get(k))
