"""Playwright visual check for AuthShell/CodeInputRow. Run ./build.sh first.
Asserts: code-row input/button 40px tall, bottoms within 1px, same line; header/footer fixed while body scrolls;
card corners not clipped (card fully inside main). Screenshots -> $OUT (default /workspace/agy-logs/ak060-*.png)."""
import os, sys, pathlib, json
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent / "dist"
OUT = os.environ.get("OUT", "/workspace/agy-logs")
VIEWS = [(1440, 900), (390, 844), (360, 640)]
PAGES = ["login", "register", "reset", "admin"]
fails, checks = [], 0

def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)

with sync_playwright() as p:
    b = p.chromium.launch()
    for fw in ["react", "vue"]:
        for w, hgt in VIEWS:
            for page in PAGES:
                for native in (False, True):
                    if native and w == 1440:
                        continue
                    ctx = b.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
                    pg = ctx.new_page()
                    url = f"file://{HERE}/{fw}.html?page={page}" + ("&native" if native else "")
                    pg.goto(url)
                    pg.wait_for_selector(".ak-shell-card")
                    pg.wait_for_timeout(150)
                    tag = f"{fw}-{page}-{w}{'-native' if native else ''}"
                    rows = pg.eval_on_selector_all(".ak-code-row", """rs => rs.map(r => {
                        const i = r.querySelector('input').getBoundingClientRect();
                        const btn = r.querySelector('button').getBoundingClientRect();
                        return {ih: i.height, bh: btn.height, ib: i.bottom, bb: btn.bottom, it: i.top, bt: btn.top,
                                wrap: getComputedStyle(r).flexWrap, overflow: r.scrollWidth > r.clientWidth + 1}})""")
                    if page in ("register", "reset", "admin"):
                        check(len(rows) == 1, f"{tag}: expected 1 code row, got {len(rows)}")
                    for r in rows:
                        check(abs(r["ih"] - 40) <= 0.5 and abs(r["bh"] - 40) <= 0.5, f"{tag}: heights {r['ih']},{r['bh']}")
                        check(abs(r["ib"] - r["bb"]) <= 1, f"{tag}: bottom diff {r['ib']-r['bb']}")
                        check(abs(r["it"] - r["bt"]) <= 1 and r["wrap"] == "nowrap" and not r["overflow"], f"{tag}: wrapped/overflow {r}")
                    geo = """() => { const q = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().toJSON() : null };
                        return {header: q('.ak-shell-header'), copy: q('.ak-shell-footer'), ch: q('.ak-shell-card-header'), cf: q('.ak-shell-card-footer'),
                                card: q('.ak-shell-card'), main: q('.ak-shell-main'), doc: document.scrollingElement.scrollHeight,
                                body: (b => ({sh: b.scrollHeight, ch: b.clientHeight}))(document.querySelector('.ak-shell-body'))} }"""
                    g1 = pg.evaluate(geo)
                    check(g1["doc"] <= hgt + 1, f"{tag}: page scrolls ({g1['doc']} > {hgt})")
                    check(g1["card"]["top"] >= g1["main"]["top"] - 0.5 and g1["card"]["bottom"] <= g1["main"]["bottom"] + 0.5, f"{tag}: card clipped")
                    check((g1["copy"] is None) == native, f"{tag}: copyright visibility")
                    check((pg.query_selector(".ak-shell-lang") is None) == native, f"{tag}: lang visibility")
                    pg.screenshot(path=f"{OUT}/ak060-{tag}.png")
                    if g1["body"]["sh"] > g1["body"]["ch"]:
                        pg.eval_on_selector(".ak-shell-body", "b => { b.scrollTop = b.scrollHeight }")
                        pg.mouse.move(w / 2, hgt / 2); pg.mouse.wheel(0, 400); pg.wait_for_timeout(100)
                        g2 = pg.evaluate(geo)
                        for k in ("header", "copy", "ch", "cf"):
                            if g1[k]:
                                check(abs(g1[k]["top"] - g2[k]["top"]) < 0.5, f"{tag}: {k} moved on scroll")
                        pg.screenshot(path=f"{OUT}/ak060-{tag}-scrolled.png")
                    ctx.close()
    b.close()
print(json.dumps({"checks": checks, "fails": fails}, ensure_ascii=False, indent=1))
sys.exit(1 if fails else 0)
