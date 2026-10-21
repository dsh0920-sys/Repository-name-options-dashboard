import json
tickers = ['QQQ','NVDA','TSLA','AMZN','GOOGL','SOXX','PLTR','CRWV','IREN','IONQ','TEM','EWY']
for t in tickers:
    d = json.load(open(f'data/analytics/{t}_latest.json'))
    print(t, 'gex_total_bn raw=', d['gex_total_bn'])
