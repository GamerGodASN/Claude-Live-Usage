"""Browser dashboard: stdlib http.server + Chart.js (CDN). Auto-refreshes."""

import json
import os
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import scanner

HOST = os.environ.get("HOST", "localhost")
PORT = int(os.environ.get("PORT", "8080"))


def _summary() -> dict:
    conn = db.connect()
    scanner.scan(conn=conn)
    data = {
        "today": db.totals_for_date(conn, date.today().isoformat()),
        "all": db.totals_all(conn),
        "week": db.daily_series(conn, 7),
        "by_model": db.by_model(conn),
        "by_project": db.by_project(conn)[:15],
    }
    conn.close()
    return data


_PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<title>Claude Live Usage</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
 body{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 system-ui,sans-serif}
 header{padding:18px 28px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center}
 h1{font-size:18px;margin:0}.muted{color:#7d8590;font-size:13px}
 .cards{display:flex;gap:16px;padding:24px 28px;flex-wrap:wrap}
 .card{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:18px 22px;min-width:160px}
 .card .k{color:#7d8590;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
 .card .v{font-size:26px;font-weight:700;margin-top:6px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;padding:0 28px 28px}
 .panel{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:18px 22px}
 @media(max-width:860px){.grid{grid-template-columns:1fr}}
</style></head><body>
<header><div><h1>Claude Live Usage</h1><div class=muted id=ts></div></div>
<div class=muted>auto-refresh 30s</div></header>
<div class=cards id=cards></div>
<div class=grid>
 <div class=panel><canvas id=week></canvas></div>
 <div class=panel><canvas id=models></canvas></div>
</div>
<script>
let wc,mc;
function money(x){return '$'+x.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
function tok(n){return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':n}
async function load(){
 const d=await (await fetch('/api/summary')).json();
 document.getElementById('ts').textContent='updated '+new Date().toLocaleTimeString();
 document.getElementById('cards').innerHTML=[
  ['Today cost',money(d.today.cost)],['Today tokens',tok(d.today.tokens)],
  ['All-time cost',money(d.all.cost)],['All-time tokens',tok(d.all.tokens)],
  ['Turns',d.all.turns.toLocaleString()]
 ].map(c=>`<div class=card><div class=k>${c[0]}</div><div class=v>${c[1]}</div></div>`).join('');
 const wl=d.week.map(w=>w.date.slice(5)),wd=d.week.map(w=>+w.cost.toFixed(2));
 const ml=d.by_model.map(m=>m.model.replace('claude-','')),md=d.by_model.map(m=>+m.cost.toFixed(2));
 if(wc)wc.destroy();if(mc)mc.destroy();
 wc=new Chart(week,{type:'bar',data:{labels:wl,datasets:[{label:'Daily cost ($)',data:wd,backgroundColor:'#2f81f7'}]},options:{plugins:{title:{display:true,text:'Last 7 days',color:'#e6edf3'}},scales:{x:{ticks:{color:'#7d8590'}},y:{ticks:{color:'#7d8590'}}}}});
 mc=new Chart(models,{type:'doughnut',data:{labels:ml,datasets:[{data:md,backgroundColor:['#f78166','#2f81f7','#3fb950','#d29922','#a371f7']}]},options:{plugins:{title:{display:true,text:'Cost by model',color:'#e6edf3'},legend:{labels:{color:'#e6edf3'}}}}});
}
load();setInterval(load,30000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        if self.path.startswith("/api/summary"):
            body = json.dumps(_summary()).encode()
            ctype = "application/json"
        else:
            body = _PAGE.encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> None:
    scanner.scan()
    url = f"http://{HOST}:{PORT}"
    print(f"Claude Live Usage dashboard → {url}  (Ctrl-C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    serve()
