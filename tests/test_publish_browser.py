"""Opt-in local DOM integration; no Douyin connection, account or public submission."""

import asyncio
import os
from types import SimpleNamespace

import pytest

from dy_cli.engines.publish_flow import PublishFlowError, VideoPublisher
from dy_cli.utils.browser import launch_chrome

pytestmark = pytest.mark.skipif(os.environ.get("DY_LOCAL_BROWSER_TESTS") != "1", reason="opt-in local Chrome test")

HTML = r"""<!doctype html><meta charset=utf-8><style>
.coverControl-fixture {display:inline-block;width:160px;height:160px}.cover-fixture{height:120px;background:#ccc}.cover-fixture img{width:160px;height:120px}
#modal{position:fixed;inset:20px;background:white;border:1px solid black;z-index:5;padding:30px}#editor{min-height:100px;border:1px solid black}
</style><input placeholder="填写作品标题，为作品获得更多流量"><div id=editor contenteditable=true></div><div class=mention-suggest-mount-dom></div>
<div class=coverControl-fixture id=horizontal><div class=cover-fixture onclick="openCover()">选择封面</div>横封面4:3</div>
<div class=coverControl-fixture id=vertical><div class=cover-fixture onclick="openCover()">选择封面</div>竖封面3:4</div>
<label><input type=checkbox checked>公开 </label><label><input type=checkbox>好友可见 </label><label><input type=checkbox>仅自己可见 </label>
<label><input type=checkbox checked>允许 </label><label><input type=checkbox>不允许 </label>
<label><input type=checkbox checked>立即发布 </label><label><input type=checkbox>定时发布 </label>
<button id=submit>发布</button><script>
const editor=document.querySelector('#editor');const suggest=document.querySelector('.mention-suggest-mount-dom');let orientation='horizontal';let selected={};let submissions=0;
document.querySelector('#submit').onclick=()=>submissions++;
editor.addEventListener('input',()=>{suggest.innerHTML='';let m=editor.innerText.match(/\s#([^#\s]+)$/);if(!m)return;let tag=m[1];
 if(tag==='不存在')return;let el=document.createElement('span');el.textContent=tag;suggest.append(el);el.onclick=()=>{
 let walker=document.createTreeWalker(editor,NodeFilter.SHOW_TEXT);let node,last;while(node=walker.nextNode())last=node;
 last.textContent=last.textContent.replace(new RegExp('\\s#'+tag+'$'),' ');let token=document.createElement('span');token.dataset.mention='#';token.contentEditable='false';token.textContent='#'+tag;editor.append(token,document.createTextNode(' '));suggest.innerHTML='';};});
function openCover(){orientation='horizontal';let modal=document.createElement('div');modal.id='modal';modal.innerHTML=`
 <div id=preview>横封面预览（4:3）</div><div class=semi-upload><input id=trap class=semi-upload-hidden-input type=file></div>
 <div class=semi-upload><input id=coverInput class=semi-upload-hidden-input type=file><div class=semi-upload-drag-area-main-text>点击上传文件或拖拽文件到这里</div></div>
 <button id=next>设置竖封面</button><button id=done>完成</button>`;document.body.append(modal);
 document.querySelector('#coverInput').onchange=e=>selected[orientation]=e.target.files[0].name;
 document.querySelector('#next').onclick=()=>{orientation='vertical';document.querySelector('#preview').textContent='竖封面预览（3:4）';};
 document.querySelector('#done').onclick=()=>{for(const key of ['horizontal','vertical'])document.querySelector('#'+key+' .cover-fixture').innerHTML='<img src="https://fixture.invalid/'+key+'/'+selected[key]+'">';modal.remove();};}
</script>"""


def test_real_locators_select_two_independent_images_and_real_topics(tmp_path):
    async def run():
        from playwright.async_api import async_playwright

        paths = []
        for name in ("horizontal.png", "vertical.png"):
            p = tmp_path / name
            p.write_bytes(b"image fixture")
            paths.append(str(p))
        spec = {
            "title": "真实标题",
            "content": "第一段 第二段",
            "rendered_content": "第一段 第二段",
            "tags": ["心理学", "科普"],
            "covers": {"horizontal": {"path": paths[0], "sha256": "h"}, "vertical": {"path": paths[1], "sha256": "v"}},
            "visibility": "公开",
            "save_permission": "keep",
        }
        flow = VideoPublisher(SimpleNamespace(), spec, tmp_path / "receipt.json")
        async with async_playwright() as pw:
            b = await launch_chrome(pw, headless=True)
            page = await b.new_page(viewport={"width": 1440, "height": 1100})

            async def route(r):
                await r.fulfill(
                    content_type="image/svg+xml",
                    body='<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="green"/></svg>',
                )

            await page.route("**/*", route)
            await page.set_content(HTML)
            try:
                await flow.fill_copy(page)
            except Exception:
                print(await page.locator("#editor").inner_html())
                print(await page.locator(".mention-suggest-mount-dom").inner_html())
                raise
            await flow.covers(page)
            await flow.settings(page)
            assert await page.evaluate("selected") == {"horizontal": "horizontal.png", "vertical": "vertical.png"}
            assert await page.evaluate("submissions") == 0
            assert (tmp_path / "receipt.assets" / "cover-horizontal.png").is_file()
            await page.locator("[contenteditable=true]").fill("被改动的正文")
            with pytest.raises(PublishFlowError, match="不符"):
                await flow.check_copy(page)
            await b.close()

    asyncio.run(run())


def test_reupload_button_does_not_bypass_preview_transcoding(tmp_path):
    async def run():
        from playwright.async_api import async_playwright

        flow = VideoPublisher(SimpleNamespace(), {}, tmp_path / "wait.json", upload_timeout=10)
        async with async_playwright() as pw:
            browser = await launch_chrome(pw, headless=True)
            page = await browser.new_page()
            await page.set_content('<button>重新上传</button><div id="transcoding">预览转码中，请稍后</div>')
            await page.evaluate("setTimeout(()=>document.querySelector('#transcoding').remove(), 300)")
            await flow.wait_upload(page)
            assert await page.locator("#transcoding").count() == 0
            await browser.close()

    asyncio.run(run())


def test_cover_baseline_waits_for_both_updates_then_still_rejects_changes(tmp_path):
    async def run():
        from playwright.async_api import async_playwright

        flow = VideoPublisher(
            SimpleNamespace(),
            {"covers": {"horizontal": {"sha256": "h"}, "vertical": {"sha256": "v"}}},
            tmp_path / "stable.json",
        )
        async with async_playwright() as pw:
            browser = await launch_chrome(pw, headless=True)
            try:
                page = await browser.new_page()

                async def route(r):
                    await r.fulfill(
                        content_type="image/svg+xml",
                        body='<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"/>',
                    )

                await page.route("https://fixture.invalid/**", route)
                await page.set_content("""<div class="coverControl-fixture">横封面4:3<img id="h" src="https://fixture.invalid/old-h"></div>
                    <div class="coverControl-fixture">竖封面3:4<img id="v" src="https://fixture.invalid/old-v"></div>
                    <div id="processing">封面检测中</div>""")
                await page.evaluate("""() => {
                    setTimeout(()=>document.querySelector('#h').src='https://fixture.invalid/new-h?signature=private',100);
                    setTimeout(()=>{document.querySelector('#v').src='https://fixture.invalid/new-v';document.querySelector('#processing').remove()},300);
                }""")
                await flow.wait_covers(page, {"horizontal": "/old-h", "vertical": "/old-v"})
                await flow.check_covers(page)
                assert flow.receipt["covers"]["horizontal"]["image_path"] == "/new-h"
                assert flow.receipt["covers"]["vertical"]["image_path"] == "/new-v"
                assert flow.receipt["cover_processing"]["both_updated"]
                await page.locator("#h").evaluate("el=>el.src='https://fixture.invalid/unreviewed'")
                with pytest.raises(PublishFlowError) as error:
                    await flow.check_covers(page)
                assert error.value.code == "cover_changed"
            finally:
                await browser.close()

    asyncio.run(run())
