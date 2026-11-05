import csv
tickers = ['QQQ','NVDA','TSLA','AMZN','GOOGL','SOXX','PLTR','CRWV','IREN','IONQ','TEM','EWY']
for t in tickers:
    print('===', t, 'price90 ===')
    try:
        with open(f'{t}_price90.csv') as f:
            rows = list(csv.reader(f))
            print(rows[0])
            for r in rows[-3:]:
                print(r)
    except Exception as e:
        print('ERR', e)
    print('===', t, 'flows ===')
    try:
        with open(f'{t}_flows.csv') as f:
            rows = list(csv.reader(f))
            print(rows[0])
            for r in rows[-3:]:
                print(r)
    except Exception as e:
        print('ERR', e)
