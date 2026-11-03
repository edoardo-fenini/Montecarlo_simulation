"""Scarica i prezzi (adjusted close, dividendi inclusi) e il cambio. Salva in data/."""
import io, sys, urllib.request, warnings
import pandas as pd, yaml, yfinance as yf
warnings.filterwarnings("ignore")

def tutti_i_ticker(cfg):
    t = [x for p in cfg["portafogli"].values() for x in p["titoli"]]
    t += [p["proxy"] for p in cfg["portafogli"].values()]
    b = cfg["benchmark"]
    t += [b["ticker"], b["proxy_storico"], cfg["cambio"]]
    return sorted(set(t))

def main():
    cfg = yaml.safe_load(open("config.yaml"))
    tick = tutti_i_ticker(cfg)
    d = yf.download(tick, period="max", auto_adjust=False, progress=False, group_by="column")
    px = d["Adj Close"].dropna(how="all").sort_index()
    px.index.name = "Date"
    px.to_csv("data/prices.csv")
    # cambio USD per 1 EUR prima del 2003: FRED
    raw = urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU", timeout=60).read()
    f = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True).iloc[:, 0]
    f = pd.to_numeric(f, errors="coerce").dropna()
    f.name = "EURUSD_FRED"; f.index.name = "Date"
    f.to_csv("data/fx_fred.csv")
    print("Scaricati", px.shape[1], "ticker;", px.index[0].date(), "->", px.index[-1].date())
    print("Primo dato per ticker:")
    print(px.apply(lambda s: s.first_valid_index().date()).sort_values().to_string())

if __name__ == "__main__":
    main()
