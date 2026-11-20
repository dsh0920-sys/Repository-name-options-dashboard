import json, os
tickers = ["QQQ","NVDA","TSLA","AMZN","GOOGL","SOXX","PLTR","CRWV","IREN","IONQ","TEM","EWY"]
for t in tickers:
    f = f"data/analytics/{t}_latest.json"
    if not os.path.exists(f):
        print(t, "NO ANALYTICS FILE")
        continue
    d = json.load(open(f))
    date = d.get("date")
    outlook_path = f"outlook/{t}_{date}.md"
    exists = os.path.exists(outlook_path)
    print(t, "date=", date, "price_date=", d.get("price_date"), "spot=", d.get("spot"), "chg_pct=", d.get("chg_pct"), "gex_total_bn=", d.get("gex_total_bn"), "outlook_exists=", exists)
