"""Verify the complete offline report in Chromium, including the per-run media selector."""
from pathlib import Path
import hashlib, json, os
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
review = root / "review"
catalog=json.loads((review/"catalog.json").read_text())
media=json.loads((review/"media-check.json").read_text())
seen=set()
def check_ref(base,ref,page=None):
    url=urlparse(ref)
    if url.scheme or url.netloc: raise ValueError(ref)
    target=(base.parent / unquote(url.path)).resolve() if url.path else base
    assert target.is_relative_to(root) and target.is_file(), (base,ref)
    if page is not None and url.fragment and target==base: assert page.locator('[id="'+url.fragment+'"]').count()==1,ref
    seen.add(str(target.relative_to(root)))
for item in catalog:
    for path in [item["media"],*[link[1] for link in item["links"]]]: check_ref(root/"index.html",path)
def verify():
    with sync_playwright() as api:
        chrome=api.chromium.launch(executable_path="/runtime/cache/ms-playwright/chromium-1248/chrome-linux64/chrome", args=["--no-sandbox","--allow-file-access-from-files","--disable-gpu"], headless=True)
        page=chrome.new_page(viewport={"width":1440,"height":900})
        errors=[]; page.on("pageerror",lambda e: errors.append(str(e)))
        selected=filters=0
        for doc in (review/"reproduce.html",root/"index.html"):
            page.goto(doc.as_uri(),wait_until="load")
            for ref in page.locator('a[href],img[src],script[src],link[href]').evaluate_all("(els)=>els.map(el=>el.getAttribute('href')||el.getAttribute('src'))"):check_ref(doc,ref,page)
        for group in dict.fromkeys(row["group"] for row in catalog):
            page.get_by_role('button',name=group,exact=True).click()
            cases=[row for row in catalog if row["group"]==group]
            assert len(cases)==page.locator("#choice option").count()
            for i,row in enumerate(cases):
                page.select_option("#choice",str(i))
                assert page.locator('#title').inner_text()==row['title']
                if row["media"].endswith(".mp4"):
                    page.wait_for_function("()=>{const v=document.querySelector('#display video');return v && v.readyState>=1 && v.videoWidth>0 && v.duration>0}")
                    assert page.locator('#display video').evaluate("v=>v.controls && v.getAttribute('src')") == row['media']
                    check_ref(root/'index.html',page.locator('#display video').get_attribute('poster'))
                else:
                    page.wait_for_function("()=>document.querySelector('#display img')?.naturalWidth>0")
                selected+=1
            for label in ['通过','部分通过','未通过','全部']:
                page.select_option("#filter",label)
                count=sum(label=="全部" or r["status"]==label for r in cases)
                assert page.locator("#choice option").count()==count
                if not count: assert '没有' in page.locator('#title').inner_text()
                filters+=1
        for width in [1440,1024,768,390]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"),width
        chrome.close()
        assert not errors,errors
    return dict(index_rows=selected,filters=filters,viewports=[1440,1024,768,390],relative_targets=len(seen),playable_videos=sum(x['video'] for x in media),non_video_containers=[x for x in media if not x['video']],js_errors=errors)
if __name__=="__main__":
    result=verify()
    (review/"site-check.json").write_text(json.dumps(result,indent=2))
    print(result)
