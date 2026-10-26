# -*- coding: utf-8 -*-
"""Monitor local 2T 2026: descarga por zona, proyeccion y publicacion.

Servidor read-only (no toca el runner). Sirve monitor.html y /api/status.
Uso:  python monitor_local.py --abrir
"""
import csv
import json
import os
import sys
import time
import threading
import subprocess
import argparse
import http.server
from datetime import datetime, timezone, timedelta
from collections import deque
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor

import requests

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
try:
    import rutas_datos as rd
    DATA = rd.DATA_ROOT
except Exception:
    DATA = os.environ.get(
        "BRASIL2026_DATA",
        "/mnt/dae292c1-10dd-4169-83ec-c1360228407b/home/rquiroga/brasil2026_data",
    )

CSV = os.path.join(DATA, "escrutinio_zonas_2026_2t.csv")
PAYLOAD = os.path.join(DATA, "datos_web_2t.json")
HEART = os.path.join(DATA, "scraper_heartbeat.json")
RUNLOG = os.path.join(DATA, "runner_2t.log")
SCRALOG = os.path.join(DATA, "scraper_2t.log")
LOCK = os.path.join(DATA, "runner_2t.lock")
RUNS = os.path.join(DATA, "lanzamiento", "scrape_runs.csv")

BR_U = "https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json"
ZU = ("https://resultados.tse.jus.br/oficial/ele2026/6258/dados/"
      "{uf}/{uf}{mun}-z{zona}-c0001-e006258-u.json")
TZ = timezone(timedelta(hours=-3))
H = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"}

_CACHE = {}
_HIST = deque(maxlen=1440)


def cached(key, ttl, fn):
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < ttl:
        return _CACHE[key][1]
    try:
        v = fn()
    except Exception as exc:
        v = {"error": str(exc)}
    _CACHE[key] = (now, v)
    return v


def alive(pid):
    if not pid:
        return False
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, 0, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def finfo(path):
    try:
        st = os.stat(path)
        return {"size": st.st_size, "mtime": st.st_mtime,
                "mtime_iso": datetime.fromtimestamp(st.st_mtime, TZ).isoformat(),
                "age_s": round(time.time() - st.st_mtime, 1)}
    except OSError:
        return {"size": None, "age_s": None}


def read_tail(path, n=40, maxbytes=65536):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - maxbytes))
            data = f.read().decode("utf-8", "replace")
        return data.splitlines()[-n:]
    except OSError:
        return []


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _int(x):
    try:
        return int(float(str(x).replace(".", "").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def csv_stats():
    rows = []
    last = {}
    try:
        with open(CSV, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r)
                k = (r.get("estado_uf", ""), str(r.get("codigo_municipio", "")).zfill(5),
                     str(r.get("zona_electoral", "")).zfill(4))
                if k not in last or (r.get("hora_local") or "") >= (last[k].get("hora_local") or ""):
                    last[k] = r
    except OSError:
        pass
    votes = sum(_int(r.get("Lula")) + _int(r.get("Flavio_Bolsonaro")) for r in last.values())
    sec = sum(_int(r.get("secoes_totalizadas")) for r in last.values())
    sample = [{"uf": k[0], "mun": k[1], "zona": k[2]} for k in list(last)[-12:]]
    info = finfo(CSV)
    return {**info, "rows": len(rows), "zones": len(last), "votes": votes,
            "sec": sec, "last": rows[-1] if rows else None, "sample": sample}


def _check_zone(s):
    uf, mun, zona = s["uf"].lower(), s["mun"].zfill(5), s["zona"].zfill(4)
    url = ZU.format(uf=uf, mun=mun, zona=zona)
    try:
        r = requests.get(url, headers=H, timeout=6)
        if r.status_code != 200:
            return {**s, "http": r.status_code}
        d = r.json()
        ss = d.get("s") or {}
        vv = d.get("v") or {}
        lula = flavio = 0
        for cargo in d.get("carg", []):
            for agr in cargo.get("agr", []):
                for par in agr.get("par", []):
                    for c in par.get("cand", []):
                        nm = (c.get("nmu") or c.get("nm") or "").lower()
                        if "lula" in nm:
                            lula = _int(c.get("vap"))
                        elif "flavio" in nm:
                            flavio = _int(c.get("vap"))
        lm = r.headers.get("Last-Modified")
        age = None
        if lm:
            try:
                dt = parsedate_to_datetime(lm)
                age = round(time.time() - dt.timestamp(), 1)
            except Exception:
                pass
        return {**s, "http": 200, "dg": d.get("dg", ""), "st": _int(ss.get("st")),
                "tv": _int(vv.get("tv")), "lula": lula, "flavio": flavio,
                "lm": lm, "age_s": age}
    except Exception as exc:
        return {**s, "http": "ERR", "error": str(exc)}


def zone_check():
    z = csv_stats()
    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(_check_zone, z["sample"]))


def aggregate():
    d = requests.get(BR_U, headers=H, timeout=8).json()
    ss = d.get("s") or {}
    vv = d.get("v") or {}
    lula = flavio = 0
    for cargo in d.get("carg", []):
        for agr in cargo.get("agr", []):
            for par in agr.get("par", []):
                for c in par.get("cand", []):
                    nm = (c.get("nmu") or c.get("nm") or "").lower()
                    if "lula" in nm:
                        lula = _int(c.get("vap"))
                    elif "flavio" in nm:
                        flavio = _int(c.get("vap"))
    st, ts = _int(ss.get("st")), _int(ss.get("ts"))
    age = None
    try:
        dt = datetime.strptime((d.get("dg") or "") + " " + (d.get("hg") or ""),
                               "%d/%m/%Y %H:%M:%S").replace(tzinfo=TZ)
        age = round(time.time() - dt.timestamp(), 1)
    except Exception:
        pass
    return {"dg": d.get("dg"), "hg": d.get("hg"), "st": st, "ts": ts,
            "tv": _int(vv.get("tv")), "lula": lula, "flavio": flavio,
            "pct": round(100.0 * st / ts, 3) if ts else 0.0,
            "stamp_age_s": age}


def payload_stats():
    d = read_json(PAYLOAD) or {}
    n = d.get("nacional") or {}
    c = n.get("crudo") or {}
    return {**finfo(PAYLOAD), "escrutado": d.get("escrutado_pct"),
            "actualizado": d.get("actualizado"),
            "crudo_lula": (c.get("lula") or {}).get("pct"),
            "crudo_flavio": (c.get("flavio") or {}).get("pct"),
            "crudo_votos": (c.get("lula") or {}).get("votos"),
            "swing": (n.get("swing") or {}).get("lula", {}).get("pct"),
            "hybrid": (n.get("hybrid") or {}).get("lula", {}).get("pct"),
            "serie_n": len(d.get("serie") or [])}


def heart_stats():
    h = read_json(HEART) or {}
    if h.get("ts"):
        try:
            h["age_s"] = round(time.time() - datetime.fromisoformat(h["ts"]).timestamp(), 1)
        except Exception:
            pass
    return h


def branch_stats():
    try:
        out = subprocess.check_output(
            ["git", "-C", REPO, "log", "-1", "--format=%cI|%h|%s", "origin/data2t"],
            timeout=8).decode("utf-8", "replace").strip()
        p = out.split("|", 2)
        when = p[0] if p else ""
        age = round(time.time() - datetime.fromisoformat(when).timestamp(), 1) if when else None
        return {"when": when, "commit": p[1] if len(p) > 1 else "",
                "msg": p[2] if len(p) > 2 else "", "age_s": age}
    except Exception as exc:
        return {"error": str(exc)}


def runs_stats():
    return {**finfo(RUNS), "tail": read_tail(RUNS, 8)}


def _runner_pid():
    try:
        return int(open(LOCK, encoding="utf-8").read().strip())
    except Exception:
        return None


def status():
    cs = csv_stats()
    zc = cached("zones", 15, zone_check)
    ag = cached("br", 15, aggregate)
    pl = payload_stats()
    hb = heart_stats()
    br = cached("branch", 15, branch_stats)
    rn = runs_stats()
    rpid = _runner_pid()

    today = datetime.now(TZ).strftime("%d/%m/%Y")
    zone_live = any(isinstance(z, dict) and str(z.get("dg", "")).startswith(today)
                    and _int(z.get("st")) > 0 for z in zc)
    zone_stale = all(isinstance(z, dict) and not str(z.get("dg", "")).startswith(today)
                     for z in zc) if zc else True

    if not hb.get("pid"):
        down = "unknown"
    elif not alive(hb.get("pid")):
        down = "dead"
    elif (hb.get("age_s") or 999) > 90:
        down = "stalled"
    elif zone_live:
        down = "ok"
    elif zone_stale and (ag or {}).get("tv", 0) > 0:
        down = "waiting_tse"
    elif zone_stale:
        down = "waiting_tse"
    else:
        down = "ok"

    if not rpid or not alive(rpid):
        up = "dead"
    elif (pl.get("age_s") or 999) > 180:
        up = "stalled"
    elif (br.get("age_s") or 999) > 300:
        up = "stalled"
    else:
        up = "ok"

    return {"now": datetime.now(TZ).isoformat(),
            "csv": cs, "zones": zc, "aggregate": ag, "payload": pl,
            "heart": hb, "branch": br, "runs": rn,
            "runner": {"pid": rpid, "alive": alive(rpid)},
            "scraper": {"pid": hb.get("pid"), "alive": alive(hb.get("pid"))},
            "zone_live": zone_live, "zone_stale": zone_stale,
            "status": {"download": down, "upload": up},
            "history": [dict(x) for x in _HIST]}


def sampler():
    while True:
        try:
            cs = csv_stats()
            ag = cached("br", 15, aggregate)
            _HIST.append({"t": time.time(), "rows": cs.get("rows"),
                          "zones": cs.get("zones"), "votes": cs.get("votes"),
                          "agg_votes": (ag or {}).get("tv", 0)})
        except Exception:
            pass
        time.sleep(5)


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            body = json.dumps(status(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path.startswith("/api/log"):
            body = json.dumps({"runner": read_tail(RUNLOG, 120),
                               "scraper": read_tail(SCRALOG, 200)},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path == "/" or self.path.startswith("/index"):
            try:
                body = open(os.path.join(REPO, "monitor.html"), "rb").read()
            except OSError:
                body = b"monitor.html missing"
            self._send(200, body, "text/html; charset=utf-8")
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8787)
    ap.add_argument("--abrir", action="store_true")
    args = ap.parse_args()
    threading.Thread(target=sampler, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
    url = f"http://127.0.0.1:{args.puerto}/"
    print(f"[*] Monitor en {url}  (Ctrl+C para salir)")
    if args.abrir:
        threading.Timer(1.0, lambda: __import__("webbrowser").open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
