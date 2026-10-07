import json
tickers = ['QQQ','NVDA','TSLA','AMZN','GOOGL','SOXX','PLTR','CRWV','IREN','IONQ','TEM','EWY']
for t in tickers:
    d = json.load(open(t+'_latest.json'))
    print(t, 'gex_total_bn=', d.get('gex_total_bn'), 'gamma_flip=', d.get('gamma_flip'), 'spot=', d.get('spot'), 'date=', d.get('date'))
