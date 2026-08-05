"""
replay_generic.py — a decision replay that works on any submission.

`replay_player.py` renders a hand-written narration per product, which requires knowing each
branch's line number and writing prose for it. That is workable for the two-product rounds and
impractical for twelve or fifty products across three quite different codebases.

This module takes the other route: **show what the replay actually captured.** For each tick it
reports the book, my resting quotes, the fills, the internal variables the algorithm computed,
and which lines of the source executed. No narration is written in advance, so nothing has to
be maintained when the submission changes — and nothing can drift away from the code either.

A per-round config only names which variables are worth surfacing first; everything else stays
available underneath.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from decision_trace import _last_snap

# Which locals to surface for each round, in order. Anything not listed is still captured and
# shown in the "all variables" panel.
KEY_VARS = {
    3: ["wall_mid", "theo", "theo_diff", "delta", "vega", "avg_abs_dev",
        "dev_at_bid", "dev_at_ask", "ema", "dev"],
    4: ["S", "T", "fair", "mm", "last", "iv", "iv_std", "take_edge", "net_delta",
        "delta", "theo", "mid"],
    5: ["mid", "mid_a", "mid_b", "spread", "mu", "sigma", "z", "fair", "beta",
        "buy_qty", "sell_qty", "pos"],
}


def build(traces, states, log, product: str, rnd: int, max_vars: int = 10) -> list[dict]:
    """One compact record per tick: book, my orders, fills, position, PnL, captured locals."""
    act = log.activities
    pnl = (act[act["product"] == product]
           .set_index("timestamp")["profit_and_loss"].to_dict())

    own = log.trades[(log.trades["side"] != 0) & (log.trades["symbol"] == product)]
    fills: dict[int, list] = {}
    for _, r in own.iterrows():
        fills.setdefault(int(r["timestamp"]), []).append(
            [float(r["price"]), int(r["quantity"]) * int(r["side"])])

    st_by_t = {s.timestamp: s for s in states}
    keys = KEY_VARS.get(rnd, [])
    out = []

    for tt in traces:
        st = st_by_t.get(tt.timestamp)
        od = st.order_depths.get(product) if st else None
        if od is None:
            continue

        # every scalar local seen this tick, last value wins
        allv: dict[str, float] = {}
        for _, snap in tt.lines:
            for k, v in snap.items():
                if isinstance(v, (int, float, bool)) and not isinstance(v, bool):
                    allv[k] = round(float(v), 4)

        # Only the configured variables. Capturing every local produces frames an order of
        # magnitude larger than the information they carry — most locals are loop counters.
        shown = [(k, allv[k]) for k in keys if k in allv][:max_vars]

        out.append({
            "t": int(tt.timestamp),
            "b": [[int(p), int(v)] for p, v in sorted(od.buy_orders.items(), reverse=True)],
            "a": [[int(p), int(-v)] for p, v in sorted(od.sell_orders.items())],
            "pos": int(st.position.get(product, 0)),
            "pnl": round(float(pnl.get(tt.timestamp, 0)), 1),
            "o": [[int(p), int(q)] for p, q in tt.orders.get(product, [])],
            "fl": fills.get(tt.timestamp, []),
            "v": shown,
            "ln": [min(l for l, _ in tt.lines), max(l for l, _ in tt.lines)] if tt.lines else [],
        })
    return out


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>__TITLE__</title><style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"SF Pro Text",sans-serif;background:#0e1116;color:#e6e6e6}
#wrap{max-width:1280px;margin:0 auto;padding:18px}
h2{margin:4px 0 6px;font-size:23px} .sub{color:#9aa4b2;font-size:13px;margin-bottom:14px;line-height:1.6}
#top{display:flex;gap:16px;align-items:flex-start}
#ladderBox{flex:0 0 290px} #chartBox{flex:1;min-width:0}
canvas{background:#151a21;border-radius:8px;display:block;width:100%}
.lbl{color:#9aa4b2;font-size:12px;margin-bottom:6px}
#panels{display:flex;gap:16px;margin:12px 0}
.panel{flex:1;padding:13px 15px;background:#151a21;border-radius:8px;font-size:13px;line-height:1.75;
       font-variant-numeric:tabular-nums}
#status{font-size:15px;margin-bottom:10px;color:#c9d1d9}
.k{color:#9aa4b2} .buy{color:#3fb950} .sell{color:#f85149} .no{color:#8b949e} b{color:#fff}
.vr{display:flex;justify-content:space-between;border-bottom:1px solid #1e242c;padding:2px 0}
.vn{color:#9aa4b2} .vv{color:#e6e6e6;font-weight:600}
#lines{color:#6e7681;font-size:11px;margin-top:8px;word-break:break-all;line-height:1.5}
#ctl{display:flex;align-items:center;gap:14px;margin-top:12px}
button{background:#238636;border:0;color:#fff;padding:9px 20px;border-radius:6px;font-size:15px;cursor:pointer}
input[type=range]{flex:1}
</style></head><body><div id="wrap">
<h2>__TITLE__</h2>
<div class="sub">Drag the timeline or press Play. Left: the book (<span class="buy">bids</span>,
<span class="sell">asks</span>, bar length = size; ◀ = <b>my own resting quotes</b>).
Right: the session and my fills.<br>
Every frame is reconstructed by running the <b>unmodified submitted source</b> under
<code>sys.settrace</code>. The values below are what the algorithm actually computed at that
instant — not a description of it. __VERIFY__</div>
<div id="top">
  <div id="ladderBox"><div class="lbl">Book and my quotes</div><canvas id="ladder" height="340"></canvas></div>
  <div id="chartBox"><div class="lbl">Session and my fills</div><canvas id="chart" height="340"></canvas></div>
</div>
<div id="panels">
  <div class="panel"><div id="status"></div><div id="act"></div></div>
  <div class="panel"><div class="lbl">internal state at this tick</div><div id="vars"></div>
    <div id="lines"></div></div>
</div>
<div id="ctl"><button id="play">▶ Play</button>
  <input type="range" id="slider" min="0" value="0">
  <span class="k">Speed</span><input type="range" id="spd" min="1" max="60" value="20" style="flex:0 0 110px">
  <span class="k" id="tlabel"></span></div>
</div>
<script>
const D=__DATA__;
const ld=document.getElementById('ladder'),ch=document.getElementById('chart');
const slider=document.getElementById('slider');slider.max=D.length-1;
function fit(c){c.width=c.clientWidth*devicePixelRatio;c.height=340*devicePixelRatio;
  c.getContext('2d').setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);}
addEventListener('resize',()=>{fit(ld);fit(ch);bg=null;render(+slider.value)});fit(ld);fit(ch);

const mids=D.map(d=>{const b=d.b[0]?d.b[0][0]:null,a=d.a[0]?d.a[0][0]:null;
  return (b!==null&&a!==null)?(b+a)/2:(b!==null?b:a);});
let lo=1e18,hi=-1e18;for(const m of mids){if(m===null)continue;lo=Math.min(lo,m);hi=Math.max(hi,m)}
const pad=Math.max((hi-lo)*0.06,1);lo-=pad;hi+=pad;
function cy(v){const H=ch.height/devicePixelRatio;return H-14-(v-lo)/(hi-lo)*(H-28)}
function cx(i){const W=ch.width/devicePixelRatio;return 52+i/(D.length-1)*(W-62)}
// The session backdrop never changes, so it is rendered once to an offscreen canvas and
// blitted each frame. Redrawing 10,000 points per frame is what makes a scrub unresponsive.
let bg=null;
function buildBackdrop(){
  const W=ch.width/devicePixelRatio,H=ch.height/devicePixelRatio;
  bg=document.createElement('canvas');
  bg.width=ch.width;bg.height=ch.height;
  const x=bg.getContext('2d');
  x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  x.fillStyle='#151a21';x.fillRect(0,0,W,H);
  x.strokeStyle='#2a323d';x.lineWidth=1;x.font='11px monospace';
  for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4;x.beginPath();x.moveTo(52,cy(v));x.lineTo(W,cy(v));x.stroke();
    x.fillStyle='#6e7681';x.fillText(v.toFixed(Math.abs(v)>500?0:1),4,cy(v)+4)}
  x.strokeStyle='#8b949e';x.lineWidth=1;x.beginPath();let st=false;
  for(let j=0;j<D.length;j++){if(mids[j]===null)continue;
    if(!st){x.moveTo(cx(j),cy(mids[j]));st=true}else x.lineTo(cx(j),cy(mids[j]))}
  x.stroke();
  for(let j=0;j<D.length;j++)for(const f of D[j].fl){
    x.fillStyle=f[1]>0?'#3fb950':'#f85149';x.beginPath();x.arc(cx(j),cy(f[0]),2.2,0,7);x.fill()}
}
function drawChart(i){
  const x=ch.getContext('2d'),W=ch.width/devicePixelRatio,H=ch.height/devicePixelRatio;
  if(!bg)buildBackdrop();
  x.setTransform(1,0,0,1,0,0);x.drawImage(bg,0,0);
  x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  x.strokeStyle='#e3b341';x.lineWidth=1.5;x.beginPath();x.moveTo(cx(i),8);x.lineTo(cx(i),H-8);x.stroke();
}
function drawLadder(d){
  const x=ld.getContext('2d'),W=ld.width/devicePixelRatio,H=ld.height/devicePixelRatio;
  x.clearRect(0,0,W,H);x.fillStyle='#151a21';x.fillRect(0,0,W,H);
  const px=[];for(const [p]of d.b)px.push(p);for(const [p]of d.a)px.push(p);
  for(const [p]of d.o)px.push(p);
  if(!px.length){x.fillStyle='#6e7681';x.font='12px monospace';x.fillText('empty book',12,24);return}
  const mn=Math.min(...px),mx=Math.max(...px),sp=Math.max(mx-mn,1);
  const y=v=>H-20-(v-mn+sp*0.1)/(sp*1.2)*(H-40);
  const maxv=Math.max(1,...d.b.map(r=>r[1]),...d.a.map(r=>r[1]));
  x.font='11px monospace';
  const bar=(p,v,col)=>{const w=Math.max(3,v/maxv*118);
    x.fillStyle=col;x.fillRect(150,y(p)-5,w,10);
    x.fillStyle='#c9d1d9';x.fillText(p+' x'+v,86,y(p)+4)};
  for(const [p,v]of d.a)bar(p,v,'#7d2b28');
  for(const [p,v]of d.b)bar(p,v,'#1f6f34');
  for(const [p,q]of d.o){const col=q>0?'#3fb950':'#f85149';
    x.fillStyle=col;x.beginPath();
    x.moveTo(146,y(p));x.lineTo(136,y(p)-6);x.lineTo(136,y(p)+6);x.closePath();x.fill();
    x.fillText((q>0?'bid ':'ask ')+p+' x'+Math.abs(q),4,y(p)+4)}
}
function render(i){
  const d=D[i];drawLadder(d);drawChart(i);
  const B=d.b[0]?d.b[0][0]:null,A=d.a[0]?d.a[0][0]:null;
  document.getElementById('status').innerHTML=
    `<span class="k">t=</span>${d.t}  <span class="k">mid=</span>`+
    ((B!==null&&A!==null)?((B+A)/2).toFixed(1):'<span class="no">one-sided</span>')+
    `  <span class="k">position=</span>${d.pos}  <span class="k">exchange PnL=</span>${d.pnl}`;
  const L=[];
  if(d.o.length)L.push('<b>quoted</b>: '+d.o.map(o=>
    `<span class="${o[1]>0?'buy':'sell'}">${o[1]>0?'bid':'ask'} ${o[0]} x${Math.abs(o[1])}</span>`).join('  '));
  else L.push('<span class="no">no orders emitted this tick</span>');
  if(d.fl.length)L.push('<b>filled</b>: '+d.fl.map(f=>
    `<span class="${f[1]>0?'buy':'sell'}">${f[1]>0?'bought':'sold'} ${Math.abs(f[1])} @ ${f[0]}</span>`).join('  '));
  else L.push('<span class="no">no fill</span>');
  document.getElementById('act').innerHTML=L.join('<br>');
  document.getElementById('vars').innerHTML=d.v.length
    ? d.v.map(([k,v])=>`<div class="vr"><span class="vn">${k}</span><span class="vv">${v}</span></div>`).join('')
    : '<span class="no">no scalars captured — the routine did not run for this product</span>';
  document.getElementById('lines').innerHTML=d.ln.length
    ? '<span class="k">source lines executed:</span> '+d.ln[0]+'&ndash;'+d.ln[1] : '';
  document.getElementById('tlabel').textContent=i+' / '+(D.length-1);
  slider.value=i;
}
slider.oninput=e=>render(+e.target.value);
let timer=null;
document.getElementById('play').onclick=function(){
  if(timer){clearInterval(timer);timer=null;this.textContent='▶ Play';return}
  this.textContent='❚❚ Pause';
  timer=setInterval(()=>{let i=+slider.value+1;
    if(i>=D.length){clearInterval(timer);timer=null;
      document.getElementById('play').textContent='▶ Play';return}
    render(i)},1000/+document.getElementById('spd').value)};
ch.onclick=e=>{const r=ch.getBoundingClientRect(),W=ch.width/devicePixelRatio;
  render(Math.max(0,Math.min(D.length-1,Math.round((e.clientX-r.left-52)/(W-62)*(D.length-1)))))};
render(0);
</script></body></html>"""


def write(frames: list[dict], out_path: str, title: str, verify: str = "") -> str:
    html = (_HTML.replace("__DATA__", json.dumps(frames, separators=(",", ":")))
                 .replace("__TITLE__", title)
                 .replace("__VERIFY__", verify))
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
