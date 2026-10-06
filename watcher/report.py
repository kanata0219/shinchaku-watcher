"""
report.py - 出力(作業用ダッシュボード / 日次ダイジェスト / JSON)の生成。

- new_items.json : items(新着) + health(稼働状況) + run(実行情報) を1つにまとめた
                   機械可読データ。ダッシュボードはこれを読み込んで表示する。
- index.html     : 作業用ダッシュボード(静的シェル)。ブラウザ側で new_items.json を
                   読み込み、出版社フィルタ・検索・検知日絞り込み・個別/一括の
                   「登録済み(消去)」・カタログ登録用コピーを行う。
                   「登録済み」状態は見ている端末のブラウザに保存される(localStorage)。
- digest.html    : その日に初めて検知した新着だけの簡易ページ(サーバ側で生成)。

配色は既存SPAと同じ 白 × 濃緑。ライト/ダーク両対応。検索除け(noindex)付き。
"""
import html
import json
from datetime import datetime

GREEN = "#1f6b4a"
GREEN_DARK = "#12402d"


def _esc(s):
    return html.escape(str(s or ""))


# ---------------------------------------------------------------- data
def _payload(store, limit=1000):
    items = store.recent_items(limit=limit)
    health = store.health_rows()
    run = store.last_run() or {}
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "total": store.total_items(),
        "items": [
            {
                "key": it["key"],
                "publisher": it["publisher_name"],
                "publisher_id": it["publisher_id"],
                "title": it["title"],
                "url": it["url"],
                "published_at": it["published_at"],
                "first_seen": it["first_seen"],
                "method": it["method"],
            } for it in items
        ],
        "health": [
            {
                "publisher_id": h["publisher_id"],
                "publisher": h["publisher_name"],
                "last_error": h["last_error"],
                "consecutive_empty": h["consecutive_empty"],
                "last_item_count": h["last_item_count"],
                "last_ok": h["last_ok"],
                "note": h["note"],
            } for h in health
        ],
        "run": {
            "finished_at": run.get("finished_at", ""),
            "sites_ok": run.get("sites_ok", 0),
            "sites_failed": run.get("sites_failed", 0),
            "new_count": run.get("new_count", 0),
        },
    }


def write_json(store, path, limit=1000):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_payload(store, limit=limit), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- styles
_BASE_CSS = f"""
:root {{
  --green:{GREEN}; --green-dark:{GREEN_DARK};
  --bg:#f6f8f6; --card:#ffffff; --text:#1a2420; --muted:#5d6b63;
  --border:#d9e2dc; --warn-bg:#fff4e5; --warn:#9a5b00;
  --bad-bg:#fde8e8; --bad:#9b1c1c; --ok:#1f6b4a; --accent:#1f6b4a;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0f1613; --card:#16211c; --text:#e7efe9; --muted:#9fb0a7;
    --border:#26362e; --warn-bg:#3a2c12; --warn:#ffcf7a;
    --bad-bg:#3a1a1a; --bad:#ff9b9b; --ok:#6fd3a2; --green:#2f9c6e; --accent:#6fd3a2;
  }}
}}
*{{box-sizing:border-box;}}
body{{margin:0;background:var(--bg);color:var(--text);
 font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",Meiryo,sans-serif;
 line-height:1.6;}}
header{{background:var(--green);color:#fff;padding:16px;}}
header .wrap,main{{max-width:1000px;margin:0 auto;}}
main{{padding:16px;}}
h1{{margin:0;font-size:1.25rem;}}
.sub{{opacity:.85;font-size:.8rem;margin-top:4px;}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;}}
.stat{{background:rgba(255,255,255,.15);border-radius:10px;padding:8px 14px;min-width:90px;}}
.stat b{{display:block;font-size:1.4rem;}}
.stat span{{font-size:.72rem;opacity:.9;}}
.controls{{background:var(--card);border:1px solid var(--border);border-radius:12px;
 padding:12px;margin:14px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:center;}}
.controls input[type=search],.controls select{{padding:8px 10px;border:1px solid var(--border);
 border-radius:8px;background:var(--bg);color:var(--text);font-size:.9rem;}}
.controls input[type=search]{{flex:1;min-width:180px;}}
.seg{{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;}}
.seg button{{border:none;background:var(--bg);color:var(--text);padding:7px 12px;
 font-size:.82rem;cursor:pointer;}}
.seg button.on{{background:var(--green);color:#fff;}}
.btn{{border:1px solid var(--border);background:var(--bg);color:var(--text);
 padding:8px 12px;border-radius:8px;font-size:.82rem;cursor:pointer;}}
.btn.primary{{background:var(--green);color:#fff;border-color:var(--green);}}
.btn:hover{{filter:brightness(1.05);}}
.bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:4px 0 12px;}}
.bar .count{{color:var(--muted);font-size:.85rem;margin-right:auto;}}
ul.items{{list-style:none;margin:0;padding:0;background:var(--card);
 border:1px solid var(--border);border-radius:12px;}}
ul.items li{{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;
 border-top:1px solid var(--border);}}
ul.items li:first-child{{border-top:none;}}
ul.items li.done{{opacity:.5;}}
.itm{{flex:1;min-width:0;}}
.itm a{{color:var(--text);text-decoration:none;font-weight:600;word-break:break-word;}}
.itm a:hover{{text-decoration:underline;color:var(--accent);}}
.meta{{color:var(--muted);font-size:.76rem;margin-top:2px;}}
.badge{{display:inline-block;font-size:.7rem;padding:1px 7px;border-radius:999px;
 border:1px solid var(--border);color:var(--muted);margin-right:4px;}}
.rowbtn{{white-space:nowrap;border:1px solid var(--border);background:var(--bg);
 color:var(--accent);padding:6px 10px;border-radius:8px;font-size:.78rem;cursor:pointer;}}
.rowbtn:hover{{background:var(--green);color:#fff;border-color:var(--green);}}
.empty{{color:var(--muted);padding:16px;background:var(--card);
 border:1px dashed var(--border);border-radius:12px;text-align:center;}}
details.health{{margin:18px 0;background:var(--card);border:1px solid var(--border);
 border-radius:12px;padding:4px 12px;}}
details.health summary{{cursor:pointer;font-weight:600;padding:8px 0;}}
table{{width:100%;border-collapse:collapse;font-size:.83rem;margin:6px 0 12px;}}
th,td{{text-align:left;padding:7px 8px;border-top:1px solid var(--border);}}
th{{color:var(--muted);font-weight:600;}}
.pill{{padding:2px 8px;border-radius:999px;font-size:.74rem;font-weight:600;}}
.pill.ok{{color:var(--ok);}} .pill.warn{{background:var(--warn-bg);color:var(--warn);}}
.pill.bad{{background:var(--bad-bg);color:var(--bad);}}
.note{{color:var(--muted);font-size:.74rem;margin-top:6px;}}
footer{{color:var(--muted);font-size:.76rem;text-align:center;padding:24px 16px;}}
.toast{{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);
 background:var(--green-dark);color:#fff;padding:10px 16px;border-radius:10px;
 font-size:.85rem;opacity:0;transition:opacity .2s;pointer-events:none;}}
.toast.show{{opacity:1;}}
"""

# ---------------------------------------------------------------- dashboard
_DASH_JS = r"""
const FALLBACK = window.__DATA__ || {items:[],health:[],run:{}};
const LS_KEY = 'swatch_processed_v1';
let DATA = FALLBACK;
let state = {q:'', pub:'all', range:'all', showDone:false};

function loadProcessed(){
  try{ return new Set(JSON.parse(localStorage.getItem(LS_KEY) || '[]')); }
  catch(e){ return new Set(); }
}
function saveProcessed(set){
  try{ localStorage.setItem(LS_KEY, JSON.stringify([...set])); }catch(e){}
}
let processed = loadProcessed();

function toast(msg){
  let t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show');
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),1800);
}
function esc(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function dpart(iso){ return (iso||'').slice(0,10); }

function inRange(iso){
  if(state.range==='all') return true;
  if(!iso) return false;
  const d = new Date(iso); if(isNaN(d)) return false;
  const now = new Date();
  if(state.range==='today'){ return dpart(d.toISOString())===dpart(localIso(now)) || sameLocalDay(d,now); }
  if(state.range==='7d'){ return (now - d) <= 7*864e5; }
  return true;
}
function localIso(d){ return new Date(d.getTime()-d.getTimezoneOffset()*6e4).toISOString(); }
function sameLocalDay(a,b){ return a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate(); }

function matches(it){
  if(state.pub!=='all' && it.publisher_id!==state.pub) return false;
  if(!inRange(it.first_seen)) return false;
  if(state.q){
    const h=(it.title+' '+it.publisher).toLowerCase();
    if(!h.includes(state.q.toLowerCase())) return false;
  }
  return true;
}

function visibleItems(){
  return DATA.items.filter(it=>{
    const done = processed.has(it.key);
    if(!state.showDone && done) return false;
    return matches(it);
  });
}

function buildPublisherSelect(){
  const sel=document.getElementById('pub');
  const counts={};
  DATA.items.forEach(it=>{ if(state.showDone || !processed.has(it.key)){
    counts[it.publisher]=(counts[it.publisher]||0)+1; }});
  const byId={};
  DATA.items.forEach(it=>{ byId[it.publisher]=it.publisher_id; });
  const names=Object.keys(counts).sort((a,b)=>a.localeCompare(b,'ja'));
  const cur=state.pub;
  sel.innerHTML='<option value="all">すべての出版社 ('+DATA.items.filter(it=>state.showDone||!processed.has(it.key)).length+')</option>'
    + names.map(n=>'<option value="'+esc(byId[n])+'">'+esc(n)+' ('+counts[n]+')</option>').join('');
  sel.value=cur;
  if(sel.value!==cur) state.pub='all', sel.value='all';
}

function stats(){
  const unproc=DATA.items.filter(it=>!processed.has(it.key)).length;
  const h=DATA.health||[];
  const need=h.filter(x=>x.last_error || (x.consecutive_empty||0)>=2).length;
  document.getElementById('s-unproc').textContent=unproc;
  document.getElementById('s-sites').textContent=h.length;
  document.getElementById('s-need').textContent=need;
}

function render(){
  buildPublisherSelect(); stats();
  const list=document.getElementById('list');
  const items=visibleItems();
  document.getElementById('count').textContent='表示 '+items.length+' 件';
  if(items.length===0){ list.innerHTML='<div class="empty">該当する新着はありません。</div>'; return; }
  list.innerHTML='<ul class="items">'+items.map(it=>{
    const done=processed.has(it.key);
    const meta='<span class="badge">'+esc(it.publisher)+'</span>検知 '+esc(dpart(it.first_seen))
      + (it.published_at?' · 公開 '+esc(dpart(it.published_at)):'') + ' · '+esc(it.method);
    const btn = done
      ? '<button class="rowbtn" data-undo="'+esc(it.key)+'">戻す</button>'
      : '<button class="rowbtn" data-done="'+esc(it.key)+'">登録済み</button>';
    return '<li class="'+(done?'done':'')+'"><div class="itm"><a href="'+esc(it.url)
      +'" target="_blank" rel="noopener">'+esc(it.title)+'</a><div class="meta">'+meta+'</div></div>'+btn+'</li>';
  }).join('')+'</ul>';
}

function renderHealth(){
  const h=DATA.health||[]; const t=document.getElementById('health-body');
  if(!h.length){ t.innerHTML='<tr><td>まだ実行されていません。</td></tr>'; return; }
  t.innerHTML=h.slice().sort((a,b)=>a.publisher.localeCompare(b.publisher,'ja')).map(x=>{
    let st = x.last_error? '<span class="pill bad">エラー</span>'
      : (x.consecutive_empty||0)>=2? '<span class="pill warn">要確認</span>'
      : '<span class="pill ok">正常</span>';
    return '<tr><td>'+esc(x.publisher)+'</td><td>'+st+'</td><td>'+(x.last_item_count||0)
      +'</td><td>'+esc(x.last_error||x.note||'')+'</td></tr>';
  }).join('');
}

// --- actions ---
document.addEventListener('click',e=>{
  const d=e.target.closest('[data-done]'); const u=e.target.closest('[data-undo]');
  if(d){ processed.add(d.getAttribute('data-done')); saveProcessed(processed); render(); }
  if(u){ processed.delete(u.getAttribute('data-undo')); saveProcessed(processed); render(); }
});

function bulkDone(){
  const items=visibleItems().filter(it=>!processed.has(it.key));
  if(!items.length){ toast('対象がありません'); return; }
  if(!confirm('表示中の '+items.length+' 件を「登録済み」にします。よろしいですか？')) return;
  items.forEach(it=>processed.add(it.key)); saveProcessed(processed); render();
  toast(items.length+' 件を登録済みにしました');
}
function copyShown(){
  const items=visibleItems();
  if(!items.length){ toast('コピー対象がありません'); return; }
  const text=items.map(it=>it.title+'\t'+it.url+'\t'+it.publisher).join('\n');
  navigator.clipboard.writeText(text).then(()=>toast(items.length+' 件をコピーしました（曲名/URL/出版社）'))
    .catch(()=>toast('コピーできませんでした'));
}
function resetAll(){
  if(!processed.size){ toast('登録済みはありません'); return; }
  if(!confirm('登録済みの印をすべて解除して、元に戻します。よろしいですか？')) return;
  processed=new Set(); saveProcessed(processed); render(); toast('すべて元に戻しました');
}
function exportProc(){
  const blob=new Blob([JSON.stringify([...processed])],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='processed-backup.json'; a.click();
}
function importProc(ev){
  const f=ev.target.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ try{ JSON.parse(r.result).forEach(k=>processed.add(k));
    saveProcessed(processed); render(); toast('読み込みました'); }catch(e){ toast('読み込み失敗'); } };
  r.readAsText(f);
}

// --- wire up controls ---
function wire(){
  document.getElementById('q').addEventListener('input',e=>{state.q=e.target.value; render();});
  document.getElementById('pub').addEventListener('change',e=>{state.pub=e.target.value; render();});
  document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{
    state.range=b.getAttribute('data-range');
    document.querySelectorAll('[data-range]').forEach(x=>x.classList.toggle('on',x===b)); render();}));
  document.querySelectorAll('[data-show]').forEach(b=>b.addEventListener('click',()=>{
    state.showDone=b.getAttribute('data-show')==='1';
    document.querySelectorAll('[data-show]').forEach(x=>x.classList.toggle('on',x===b)); render();}));
  document.getElementById('bulk').addEventListener('click',bulkDone);
  document.getElementById('copy').addEventListener('click',copyShown);
  document.getElementById('reset').addEventListener('click',resetAll);
  document.getElementById('export').addEventListener('click',exportProc);
  document.getElementById('import').addEventListener('change',importProc);
}

async function init(){
  wire();
  try{ const r=await fetch('./new_items.json',{cache:'no-store'});
       if(r.ok) DATA=await r.json(); }catch(e){}
  const run=DATA.run||{};
  document.getElementById('lastrun').textContent =
    (DATA.generated_at||run.finished_at||'').slice(0,16).replace('T',' ') || '—';
  renderHealth(); render();
}
init();
"""


def _dashboard_html(payload):
    data_json = json.dumps(payload, ensure_ascii=False)
    return (
        "<!doctype html>\n<html lang=\"ja\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow, noarchive, noimageindex\">\n"
        "<title>新着楽譜ダッシュボード</title>\n<style>" + _BASE_CSS + "</style></head>\n<body>\n"
        "<header><div class=\"wrap\">\n"
        "  <h1>新着楽譜ダッシュボード</h1>\n"
        "  <div class=\"sub\">最終更新: <span id=\"lastrun\">—</span>　／　新着を確認し、カタログへ登録したら「登録済み」で消し込みます</div>\n"
        "  <div class=\"stats\">\n"
        "    <div class=\"stat\"><b id=\"s-unproc\">0</b><span>未処理の新着</span></div>\n"
        "    <div class=\"stat\"><b id=\"s-sites\">0</b><span>監視サイト</span></div>\n"
        "    <div class=\"stat\"><b id=\"s-need\">0</b><span>要確認/エラー</span></div>\n"
        "  </div>\n</div></header>\n<main>\n"
        "  <div class=\"controls\">\n"
        "    <input type=\"search\" id=\"q\" placeholder=\"曲名・出版社で検索\">\n"
        "    <select id=\"pub\"></select>\n"
        "    <span class=\"seg\">\n"
        "      <button data-range=\"all\" class=\"on\">すべて</button>\n"
        "      <button data-range=\"today\">今日</button>\n"
        "      <button data-range=\"7d\">7日</button>\n"
        "    </span>\n"
        "    <span class=\"seg\">\n"
        "      <button data-show=\"0\" class=\"on\">未処理のみ</button>\n"
        "      <button data-show=\"1\">登録済みも表示</button>\n"
        "    </span>\n"
        "  </div>\n"
        "  <div class=\"bar\">\n"
        "    <span class=\"count\" id=\"count\">表示 0 件</span>\n"
        "    <button class=\"btn\" id=\"copy\">表示中をコピー（登録用）</button>\n"
        "    <button class=\"btn primary\" id=\"bulk\">表示中をすべて登録済みに</button>\n"
        "    <button class=\"btn\" id=\"reset\">登録済みを元に戻す</button>\n"
        "  </div>\n"
        "  <div id=\"list\"></div>\n"
        "  <details class=\"health\"><summary>サイト稼働状況</summary>\n"
        "    <table><thead><tr><th>出版社</th><th>状態</th><th>取得件数</th><th>備考</th></tr></thead>\n"
        "    <tbody id=\"health-body\"></tbody></table>\n"
        "    <div class=\"note\">「要確認（黄）」は、取得成功でも新着が2回連続0件＝サイトの作りが変わった可能性。"
        "その社だけ registry.yaml を直せば直ります。</div>\n"
        "  </details>\n"
        "  <div class=\"note\">※「登録済み」の印は、いま見ているこの端末のブラウザに保存されます（他の端末には共有されません）。"
        "端末を移すときは下のバックアップを使ってください：\n"
        "    <button class=\"btn\" id=\"export\">登録済みを書き出す</button>\n"
        "    <label class=\"btn\" style=\"cursor:pointer\">読み込む<input type=\"file\" id=\"import\" accept=\"application/json\" hidden></label>\n"
        "  </div>\n"
        "</main>\n"
        "<div class=\"toast\" id=\"toast\"></div>\n"
        "<footer>shinchaku-watcher · 吹奏楽譜 新着監視システム</footer>\n"
        "<script>window.__DATA__=" + data_json + ";</script>\n"
        "<script>" + _DASH_JS + "</script>\n"
        "</body></html>"
    )


def render_dashboard(store, path, max_new=1000):
    payload = _payload(store, limit=max_new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_dashboard_html(payload))


# ---------------------------------------------------------------- digest
def _page(title, body):
    return (
        "<!doctype html>\n<html lang=\"ja\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow, noarchive, noimageindex\">\n"
        "<title>" + _esc(title) + "</title>\n<style>" + _BASE_CSS + "</style></head>\n<body>" + body +
        "\n<footer>shinchaku-watcher · 吹奏楽譜 新着監視システム</footer>\n</body></html>"
    )


def render_digest(store, path, date_str=None):
    if date_str is None:
        date_str = datetime.now().astimezone().strftime("%Y-%m-%d")
    items = store.items_first_seen_on(date_str)
    rows = []
    for it in items:
        pub = _esc(it["publisher_name"])
        rows.append(
            f'<li><div class="itm"><a href="{_esc(it["url"])}" target="_blank" rel="noopener">'
            f'<span class="badge">{pub}</span>{_esc(it["title"])}</a></div></li>')
    body = [f"""<header><div class="wrap">
      <h1>新着ダイジェスト</h1>
      <div class="sub">{_esc(date_str)} に初めて検知した新着 · {len(items)}件</div>
      </div></header><main>"""]
    if rows:
        body.append('<ul class="items">' + "".join(rows) + "</ul>")
    else:
        body.append('<div class="empty">本日の新着はありません。</div>')
    body.append('<div class="note">このページは「その日の新着だけ」の簡易版です。'
                '検索・絞り込み・消し込みはダッシュボード（index.html）をお使いください。</div>')
    body.append("</main>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_page(f"新着ダイジェスト {date_str}", "".join(body)))
    return len(items)
