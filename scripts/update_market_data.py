#!/usr/bin/env python3
"""Fetch public daily prices and SEC companyfacts. No API key is required."""
import csv, io, json, os, re, time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "tickers.json")
OUTPUT = os.path.join(ROOT, "data", "market.json")
UA = "TX-1151026-2 stock research dashboard (public GitHub repository)"

def get_json(url, delay=0):
    if delay:
        time.sleep(delay)
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def get_text(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")

def sec_company_map():
    raw = get_json("https://www.sec.gov/files/company_tickers.json")
    return {str(v["ticker"]).upper(): str(v["cik_str"]).zfill(10) for v in raw.values()}

def stooq_quote(ticker):
    # Free public daily CSV endpoint; availability and delay may vary.
    url = "https://stooq.com/q/d/l/?s=" + ticker.lower() + ".us&i=d"
    rows = list(csv.DictReader(io.StringIO(get_text(url))))
    if not rows or "Close" not in rows[-1]:
        raise ValueError("No daily price rows returned")
    row = rows[-1]
    if not row.get("Close") or row["Close"] in ("N/D", "-"):
        raise ValueError("No closing price in response")
    volume = row.get("Volume")
    return {
        "date": row.get("Date", ""),
        "close": float(row["Close"]),
        "volume": int(float(volume)) if volume and volume not in ("N/D", "-") else None,
        "source": "Stooq daily CSV; may be delayed, verify independently"
    }

def fact_units(fact):
    units = fact.get("units", {})
    for unit in ("USD", "USD/shares", "shares", "pure"):
        if unit in units:
            return units[unit]
    return next(iter(units.values()), [])

def tag_values(facts, candidates):
    for tag in candidates:
        obj = facts.get("us-gaap", {}).get(tag)
        if obj:
            values = fact_units(obj)
            if values:
                return values, tag
    return [], None

def records_for(facts, candidates, period):
    values, tag = tag_values(facts, candidates)
    result = {}
    for value in values:
        if value.get("form") not in ("10-K", "10-Q", "20-F", "40-F"):
            continue
        if not value.get("end") or value.get("val") is None:
            continue
        start = value.get("start")
        days = 0
        if start:
            days = (datetime.strptime(value["end"], "%Y-%m-%d") -
                    datetime.strptime(start, "%Y-%m-%d")).days
        if period == "annual" and not (330 <= days <= 380):
            continue
        if period == "quarterly" and not (70 <= days <= 110):
            continue
        end = value["end"]
        old = result.get(end)
        if old is None or value.get("filed", "") > old.get("filed", ""):
            result[end] = dict(value, _days=days)
    return result, tag

def make_financials(companyfacts):
    facts = companyfacts.get("facts", {})
    tags = {
        "revenue": [
            "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
            "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet"
        ],
        "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
        "grossProfit": ["GrossProfit"],
        "operatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
        "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"]
    }
    output = {"annual": [], "quarterly": [], "tag_used": {}}
    raw = {}
    for period in ("annual", "quarterly"):
        raw[period] = {}
        for key, candidates in tags.items():
            raw[period][key], used = records_for(facts, candidates, period)
            if used:
                output["tag_used"][key] = used
        dates = sorted(set().union(*(set(v.keys()) for v in raw[period].values())))
        for date in dates:
            item = {"period_end": date}
            for key in tags:
                value = raw[period][key].get(date)
                item[key] = value.get("val") if value else None
                if key == "revenue" and value:
                    item["filed"] = value.get("filed")
                    item["form"] = value.get("form")
                    item["fiscal_year"] = value.get("fy")
                    item["fiscal_period"] = value.get("fp")
            revenue, gross_profit = item.get("revenue"), item.get("grossProfit")
            item["gross_margin_pct"] = (
                round(gross_profit / revenue * 100, 2)
                if gross_profit is not None and revenue else None
            )
            ocf, capex = item.get("operatingCashFlow"), item.get("capex")
            item["free_cash_flow"] = ocf - capex if ocf is not None and capex is not None else None
            output[period].append(item)
        output[period] = output[period][-12:] if period == "annual" else output[period][-16:]
    return output

def main():
    with open(CONFIG, encoding="utf-8") as file:
        tickers = [
            str(t).strip().upper()
            for t in json.load(file).get("tickers", [])
            if re.fullmatch(r"[A-Z0-9.-]{1,15}", str(t).strip().upper())
        ]
    data = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "provider_notes": {
            "prices": "Stooq daily CSV; may be delayed and is not guaranteed real-time.",
            "fundamentals": "SEC companyfacts XBRL filings; some tags may be absent or amended.",
            "financial_units": "SEC reported values are generally USD; EPS is USD/share. Website tables show revenue/FCF in millions."
        },
        "stocks": {},
        "errors": []
    }
    errors = []
    try:
        company_map = sec_company_map()
    except Exception as error:
        company_map = {}
        errors.append("SEC ticker map failed: " + str(error))
    for ticker in tickers:
        item = {
            "ticker": ticker, "price": None, "quote": None,
            "financials": {"annual": [], "quarterly": [], "tag_used": {}},
            "status": {}
        }
        try:
            quote = stooq_quote(ticker)
            item["quote"] = quote
            item["price"] = quote["close"]
            item["status"]["price"] = "ok"
        except Exception as error:
            item["status"]["price"] = "error: " + str(error)
            errors.append(ticker + " price: " + str(error))
        cik = company_map.get(ticker)
        if not cik:
            item["status"]["sec"] = "ticker not found in SEC ticker map"
        else:
            try:
                facts = get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK" + cik + ".json", 0.15)
                item["company"] = facts.get("entityName", ticker)
                item["cik"] = cik
                item["financials"] = make_financials(facts)
                item["status"]["sec"] = "ok"
            except Exception as error:
                item["status"]["sec"] = "error: " + str(error)
                errors.append(ticker + " SEC: " + str(error))
        data["stocks"][ticker] = item
        print(ticker, item["status"])
        time.sleep(0.2)
    data["errors"] = errors
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    temp = OUTPUT + ".tmp"
    with open(temp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp, OUTPUT)
    print("Wrote", OUTPUT, "with", len(data["stocks"]), "tickers")

if __name__ == "__main__":
    main()
