"""
replay_player.py — renders a tick-by-tick decision replay as a single self-contained HTML file.

The point of difference from a conventional trade-viewer is narrow but decisive: a viewer that
only annotates *fills* is silent on the overwhelming majority of ticks, because most ticks have
no fill. Here every frame carries the decision — which branches fired, both sides of each
comparison, and why the alternative was not taken — reconstructed by `decision_trace` from the
unmodified submitted source.

Two further corrections over a naive viewer:
  - the ladder draws **my own resting quotes** alongside the market book; where I am quoting
    relative to the touch is the whole of market making
  - one-sided books show no midpoint, rather than a degenerate one

Frames store structured fields rather than rendered text, so the file stays small and the
wording can be changed without regenerating 10,000 frames.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from decision_trace import R1_ASH, _fired, _last_snap


# Where to read each product's state from: the line ranges of its order and fair-price
# routines, and the line numbers of each branch.
# These must be per product: ASH and ROOT both execute within a single run() call, so using
# the wrong range attributes one product's locals to the other — real numbers, wrong owner.
# And per round: the sources differ. Round 2 adds MIN_EDGE=2 to every threshold comparison,
# which the renderer must carry or the inequalities shown will not match the code.
SPEC_BY_ROUND = {
    1: {
        "ASH_COATED_OSMIUM": dict(kind="ash", ord_rng=(75, 113), fair_rng=(45, 55), min_edge=0,
            branches={"take_buy": {93}, "take_sell": {100}, "make_bid": {106}, "make_ask": {111}}),
        "INTARIAN_PEPPER_ROOT": dict(kind="pepper", ord_rng=(57, 73), fair_rng=(32, 43), min_edge=0,
            branches={"take_buy": {66}, "take_sell": set(), "make_bid": {71}, "make_ask": set()}),
    },
    2: {
        "ASH_COATED_OSMIUM": dict(kind="ash", ord_rng=(82, 120), fair_rng=(47, 62), min_edge=2,
            branches={"take_buy": {102}, "take_sell": {109}, "make_bid": {115}, "make_ask": {120}}),
        "INTARIAN_PEPPER_ROOT": dict(kind="pepper", ord_rng=(64, 80), fair_rng=(34, 45), min_edge=0,
            branches={"take_buy": {73}, "take_sell": set(), "make_bid": {78}, "make_ask": set()}),
    },
}
SPEC = SPEC_BY_ROUND[1]   # backwards compatibility


def build_frames(traces, states, log, product: str = "ASH_COATED_OSMIUM",
                 rnd: int = 1) -> list[dict]:
    """Compress the trace and the exchange record into one compact row per tick."""
    spec = SPEC_BY_ROUND[rnd][product]
    act = log.activities
    pnl = (act[act["product"] == product]
           .set_index("timestamp")["profit_and_loss"].to_dict())

    own = log.trades[(log.trades["side"] != 0) & (log.trades["symbol"] == product)]
    fills: dict[int, list] = {}
    for _, r in own.iterrows():
        fills.setdefault(int(r["timestamp"]), []).append(
            [float(r["price"]), int(r["quantity"]) * int(r["side"])])

    st_by_t = {s.timestamp: s for s in states}
    out = []
    for tt in traces:
        st = st_by_t[tt.timestamp]
        od = st.order_depths.get(product)
        if od is None:
            continue
        s = _last_snap(tt, *spec["ord_rng"])
        fs = _last_snap(tt, *spec["fair_rng"])
        bids = sorted(od.buy_orders.items(), reverse=True)
        asks = sorted((p, -v) for p, v in od.sell_orders.items())

        rec = {
            "t": int(tt.timestamp),
            "b": [[int(p), int(v)] for p, v in bids],
            "a": [[int(p), int(v)] for p, v in asks],
            "pos": int(st.position.get(product, 0)),
            "pnl": round(float(pnl.get(tt.timestamp, 0)), 1),
            "fair": round(s["fair"], 2) if "fair" in s else None,
            "mid": fs.get("mid"),
            "o": [[int(p), int(q)] for p, q in tt.orders.get(product, [])],
            "fl": fills.get(tt.timestamp, []),
            "br": [_fired(tt, spec["branches"][k]) if spec["branches"][k] else False
                   for k in ("take_buy", "take_sell", "make_bid", "make_ask")],
            "me": spec["min_edge"],
        }
        if spec["kind"] == "ash":
            rec.update({
                "fsk": round(s["fair_skewed"], 2) if "fair_skewed" in s else None,
                "sp": s.get("spread"),
                "sk": round(s["skew_k"], 1) if "skew_k" in s else None,
                "cap": s.get("passive_cap"),
                "dev": round(fs["deviation"], 2) if "deviation" in fs else None,
                "al": round(fs["alpha"], 3) if "alpha" in fs else None,
            })
        else:   # ROOT: threshold is fair+10 (the buy buffer); no inventory skew, no sell side
            rec.update({
                "thr": round(s["fair"] + 10, 2) if "fair" in s else None,
                "cap": s.get("buy_cap"),
                "imp": round(fs["implied_intercept"], 2) if "implied_intercept" in fs else None,
            })
        out.append(rec)
    return out


_HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>__TITLE__</title><style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC",sans-serif;background:#0e1116;color:#e6e6e6}
#wrap{max-width:1280px;margin:0 auto;padding:18px}
h2{margin:4px 0 6px;font-size:24px} .sub{color:#9aa4b2;font-size:13px;margin-bottom:14px;line-height:1.6}
#top{display:flex;gap:16px;align-items:flex-start}
#ladderBox{flex:0 0 300px} #chartBox{flex:1;min-width:0}
canvas{background:#151a21;border-radius:8px;display:block;width:100%}
.lbl{color:#9aa4b2;font-size:12px;margin-bottom:6px}
#info{margin:12px 0;padding:14px 16px;background:#151a21;border-radius:8px;
      font-size:14px;line-height:1.85;font-variant-numeric:tabular-nums}
#status{font-size:15px;margin-bottom:10px;color:#c9d1d9}
.k{color:#9aa4b2} .buy{color:#3fb950} .sell{color:#f85149} .fair{color:#a371f7}
.no{color:#8b949e} .yes{color:#58a6ff} b{color:#fff}
#ctl{display:flex;align-items:center;gap:14px;margin-top:12px}
button{background:#238636;border:0;color:#fff;padding:9px 20px;border-radius:6px;
       font-size:15px;cursor:pointer}
input[type=range]{flex:1}
.step{margin:2px 0}
</style></head><body><div id="wrap">
<h2>__TITLE__</h2>
<div class="sub">Drag the timeline or press Play. Left: the current book (<span class="buy">bids green</span>,
<span class="sell">asks red</span>, bar length = size; <span class="fair">purple</span> = the algorithm's fair price;
◀ = <b>my own resting quotes</b>). Right: the session's prices and my fills.<br>
Every frame is reconstructed by running the <b>unmodified submitted source</b> under <code>sys.settrace</code>,
verified against the exchange log — all __NFILL__ of my fills are explained by orders the replay emits.</div>
<div id="top">
  <div id="ladderBox"><div class="lbl">Book and my quotes</div><canvas id="ladder" height="360"></canvas></div>
  <div id="chartBox"><div class="lbl">Session prices and my fills</div><canvas id="chart" height="360"></canvas></div>
</div>
<div id="info"><div id="status"></div><div id="why"></div></div>
<div id="ctl"><button id="play">▶ Play</button>
  <input type="range" id="slider" min="0" value="0">
  <span class="k">Speed</span><input type="range" id="spd" min="1" max="60" value="20" style="flex:0 0 120px">
  <span class="k" id="tlabel"></span></div>
</div>
<script>
const D=__DATA__;
const ld=document.getElementById('ladder'),ch=document.getElementById('chart');
const slider=document.getElementById('slider');slider.max=D.length-1;
function fit(c){c.width=c.clientWidth*devicePixelRatio;c.height=360*devicePixelRatio;
  c.getContext('2d').setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);}
addEventListener('resize',()=>{fit(ld);fit(ch);bg=null;render(+slider.value)});fit(ld);fit(ch);

// ---- session price chart (drawn once) ----
const mids=D.map(d=>{const b=d.b[0]?d.b[0][0]:null,a=d.a[0]?d.a[0][0]:null;
  return (b!==null&&a!==null)?(b+a)/2:(b!==null?b:a);});
let lo=1e9,hi=-1e9;for(const m of mids){if(m===null)continue;lo=Math.min(lo,m);hi=Math.max(hi,m)}
lo-=4;hi+=4;
function cy(v){const H=ch.height/devicePixelRatio;return H-14-(v-lo)/(hi-lo)*(H-28)}
function cx(i){const W=ch.width/devicePixelRatio;return 44+i/(D.length-1)*(W-54)}
// The session backdrop never changes, so it is built once offscreen and blitted each frame.
// Redrawing 10,000 points per frame is what makes a scrub unresponsive.
let bg=null;
function buildBackdrop(){
  const W=ch.width/devicePixelRatio,H=ch.height/devicePixelRatio;
  bg=document.createElement('canvas');bg.width=ch.width;bg.height=ch.height;
  const x=bg.getContext('2d');
  x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  x.fillStyle='#151a21';x.fillRect(0,0,W,H);
  x.strokeStyle='#2a323d';x.lineWidth=1;
  for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4;x.beginPath();x.moveTo(44,cy(v));x.lineTo(W,cy(v));x.stroke();
    x.fillStyle='#6e7681';x.font='11px monospace';x.fillText(v.toFixed(0),4,cy(v)+4)}
  x.strokeStyle='#8b949e';x.lineWidth=1;x.beginPath();let st=false;
  for(let j=0;j<D.length;j++){if(mids[j]===null)continue;
    if(!st){x.moveTo(cx(j),cy(mids[j]));st=true}else x.lineTo(cx(j),cy(mids[j]))}
  x.stroke();
  x.strokeStyle='#a371f7';x.lineWidth=1.5;x.beginPath();st=false;
  for(let j=0;j<D.length;j++){if(D[j].fair==null)continue;
    if(!st){x.moveTo(cx(j),cy(D[j].fair));st=true}else x.lineTo(cx(j),cy(D[j].fair))}
  x.stroke();
  for(let j=0;j<D.length;j++)for(const f of D[j].fl){
    x.fillStyle=f[1]>0?'#3fb950':'#f85149';x.beginPath();x.arc(cx(j),cy(f[0]),2,0,7);x.fill()}
}
function drawChart(i){
  const x=ch.getContext('2d'),H=ch.height/devicePixelRatio;
  if(!bg)buildBackdrop();
  x.setTransform(1,0,0,1,0,0);x.drawImage(bg,0,0);
  x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  x.strokeStyle='#e3b341';x.lineWidth=1.5;x.beginPath();x.moveTo(cx(i),8);x.lineTo(cx(i),H-8);x.stroke();
}

// ---- ladder: market book plus my own quotes ----
function drawLadder(d){
  const x=ld.getContext('2d'),W=ld.width/devicePixelRatio,H=ld.height/devicePixelRatio;
  x.clearRect(0,0,W,H);x.fillStyle='#151a21';x.fillRect(0,0,W,H);
  const px=[];for(const [p]of d.b)px.push(p);for(const [p]of d.a)px.push(p);
  for(const [p]of d.o)px.push(p); if(d.fair!=null)px.push(d.fair);
  if(!px.length)return;
  const mn=Math.min(...px)-2,mx=Math.max(...px)+2;
  const y=v=>H-18-(v-mn)/(mx-mn)*(H-36);
  const maxv=Math.max(1,...d.b.map(r=>r[1]),...d.a.map(r=>r[1]));
  x.font='11px monospace';
  const bar=(p,v,col)=>{const w=Math.max(3,v/maxv*130);
    x.fillStyle=col;x.fillRect(150,y(p)-5,w,10);
    x.fillStyle='#c9d1d9';x.fillText(p+' ×'+v,84,y(p)+4)};
  for(const [p,v]of d.a)bar(p,v,'#7d2b28');
  for(const [p,v]of d.b)bar(p,v,'#1f6f34');
  if(d.fair!=null){x.strokeStyle='#a371f7';x.lineWidth=1.5;x.setLineDash([4,3]);
    x.beginPath();x.moveTo(150,y(d.fair));x.lineTo(W-6,y(d.fair));x.stroke();x.setLineDash([]);
    x.fillStyle='#a371f7';x.fillText('fair '+d.fair.toFixed(1),6,y(d.fair)+4)}
  for(const [p,q]of d.o){                       // <- my own quotes
    const col=q>0?'#3fb950':'#f85149';
    x.fillStyle=col;x.beginPath();
    x.moveTo(146,y(p));x.lineTo(136,y(p)-6);x.lineTo(136,y(p)+6);x.closePath();x.fill();
    x.fillStyle=col;x.fillText((q>0?'my bid ':'my offer ')+p+' ×'+Math.abs(q),
      6,y(p)+4)}
}

// ---- annotation: present on every frame ----
const KIND="__KIND__";
function why(d){return KIND==='ash'?whyAsh(d):whyPepper(d)}

function whyPepper(d){
  const L=[],B=d.b[0]?d.b[0][0]:null,A=d.a[0]?d.a[0][0]:null;
  if(d.mid!=null)L.push(`① fair: mid=${d.mid.toFixed(1)} → implied intercept = mid − 0.001·t = ${d.imp};`+
      `after the 0.02 EWMA update, <b>fair = intercept + 0.001·t = ${d.fair}</b>`);
  else L.push(`① fair: <span class="no">${!d.b.length?'no bid':'no ask'}</span> → `+
      `the guard at line 34 fails, <b>intercept not updated</b>, carrying forward fair=${d.fair==null?'—':d.fair}`);
  L.push(`② buy threshold: fair + BUFFER(10) = <b>${d.thr}</b>  `+
      `<span class="k">capacity = 80 − ${d.pos} = ${80-d.pos}</span>`);
  if(d.br[0])L.push(`③ <span class="yes">lift</span>: an offer at or below ${d.thr} → buy`);
  else if(A!=null)L.push(`③ lift? cheapest ask ${A} &gt; ${d.thr} → <span class="no">no</span> (${(A-d.thr).toFixed(2)}）`);
  const mb=d.o.filter(o=>o[1]>0);
  if(d.br[2]&&mb.length)L.push(`④ <span class="buy">post bid</span>: min(${B}+1, ⌊${d.fair}⌋) = ${mb[mb.length-1][0]} → BUY ×${mb[mb.length-1][1]}`);
  else if(80-d.pos<=0)L.push(`④ post bid? <span class="no">capacity 0 — at the +80 limit</span> → no quote`);
  L.push(`<span class="no">⑤ sell: <b>this algorithm has no sell branch at all</b> (lines 57–73 are buy-only) —`+
      `an unhedged long with no downside protection. A structural gap, not a decision taken this tick.</span>`);
  if(d.fl.length)L.push('→ <b>filled</b>: '+d.fl.map(f=>
      `<span class="${f[1]>0?'buy':'sell'}">${f[1]>0?'buy':'sell'} ${f[0]} ×${Math.abs(f[1])}</span>`).join('，'));
  else L.push(d.o.length?`→ no fill: resting at ${d.o.map(o=>o[0]).join('/')}, waiting`
                        :'→ no fill: at the limit, nothing quoted');
  return L.map(s=>'<div class="step">'+s+'</div>').join('');
}

function whyAsh(d){
  const L=[],B=d.b[0]?d.b[0][0]:null,A=d.a[0]?d.a[0][0]:null;
  const n=v=>v==null?'—':v;
  if(d.mid!=null){
    if(d.dev!=null)L.push(`① fair: mid=${d.mid.toFixed(1)}  |mid − previous|=${d.dev} → α=0.05+0.05×min(${d.dev}/5,1)=${d.al} ⇒ <b>fair=${d.fair}</b>`);
    else L.push(`① fair: first tick, seeded from mid=${d.mid.toFixed(1)} ⇒ <b>fair=${d.fair}</b>`);
  }else{
    const miss=!d.b.length?'no bid':(!d.a.length?'no ask':'empty book');
    L.push(`① fair: <span class="no">${miss}</span> this tick → the guard at line 47 fails, <b>fair is not updated</b>, carrying forward ${n(d.fair)}`);
  }
  if(d.fsk!=null)L.push(`② inventory skew: spread=${d.sp} → skew_k=${d.sk}；fair_skewed=${d.fair}−${d.sk}×(${d.pos}/80)=<b>${d.fsk}</b>`);
  const ME=d.me||0, TB=d.fsk-ME, TS=d.fsk+ME;
  if(d.br[0])L.push(`③ <span class="yes">lift</span>: an offer below ${TB.toFixed(2)}${ME?` (=fair_skewed−MIN_EDGE ${ME})`:''} → buy`);
  else if(A!=null)L.push(`③ lift? cheapest ask ${A} ≥ ${TB.toFixed(2)}${ME?` (=fair_skewed−${ME})`:''} → <span class="no">no</span> (${(A-TB).toFixed(2)}）`);
  if(d.br[1])L.push(`④ hit? a bid above ${TS.toFixed(2)}${ME?` (=fair_skewed+${ME})`:''} → sell`);
  else if(B!=null)L.push(`④ hit? best bid ${B} ≤ ${TS.toFixed(2)}${ME?` (=fair_skewed+${ME})`:''} → <span class="no">no</span> (${(TS-B).toFixed(2)}）`);
  const mb=d.o.filter(o=>o[1]>0),ma=d.o.filter(o=>o[1]<0);
  const MB=Math.trunc(d.fsk)-ME, MA=Math.trunc(d.fsk)+ME;
  if(d.br[2]&&mb.length)L.push(`⑤ <span class="buy">post bid</span>: ${B}+1=${mb[0][0]} &lt; ${MB} ✓ → BUY ${mb[0][0]} ×${mb[0][1]}`);
  else if(B!=null)L.push(`⑤ post bid? ${B}+1=${B+1} ≥ ${MB} ✗ → <span class="no">no quote</span>`);
  if(d.br[3]&&ma.length)L.push(`⑥ <span class="sell">post offer</span>: ${A}−1=${ma[0][0]} &gt; ${MA} ✓ → SELL ${ma[0][0]} ×${Math.abs(ma[0][1])}`);
  else if(A!=null)L.push(`⑥ post offer? ${A}−1=${A-1} ≤ ${MA} ✗ → <span class="no">no quote</span>`);
  if(d.cap!=null)L.push(`<span class="k">    quote size = ${d.cap} = clip(0.6 × mean book size, 10, 30)</span>`);
  if(d.fl.length)L.push('→ <b>filled</b>: '+d.fl.map(f=>
      `<span class="${f[1]>0?'buy':'sell'}">${f[1]>0?'buy':'sell'} ${f[0]} ×${Math.abs(f[1])}</span>`).join('，'));
  else L.push(d.o.length?`→ no fill: resting at ${d.o.map(o=>o[0]).join('/')}, waiting`
                        :'→ no fill: nothing quoted');
  return L.map(s=>'<div class="step">'+s+'</div>').join('');
}

function render(i){
  const d=D[i];drawLadder(d);drawChart(i);
  const B=d.b[0]?d.b[0][0]:null,A=d.a[0]?d.a[0][0]:null;
  const midTxt=(B!=null&&A!=null)?`<span class="k">mid=</span>${((B+A)/2).toFixed(1)}`
    :`<span class="k">mid=</span><span class="no">one-sided book</span>`;
  document.getElementById('status').innerHTML=
    `<span class="k">t=</span>${d.t}  <span class="fair">fair=${d.fair==null?'—':d.fair}</span>  ${midTxt}  `+
    `<span class="k">position=</span>${d.pos}  <span class="k">exchange PnL=</span>${d.pnl}`;
  document.getElementById('why').innerHTML=why(d);
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
ch.onclick=e=>{const r=ch.getBoundingClientRect();
  const W=ch.width/devicePixelRatio;
  render(Math.max(0,Math.min(D.length-1,Math.round((e.clientX-r.left-44)/(W-54)*(D.length-1)))))};
render(0);
</script></body></html>"""


def write_player(frames: list[dict], out_path: str, title: str, n_fill: int,
                 kind: str = "ash") -> str:
    html = (_HTML.replace("__DATA__", json.dumps(frames, separators=(",", ":")))
                 .replace("__TITLE__", title)
                 .replace("__KIND__", kind)
                 .replace("__NFILL__", str(n_fill)))
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
