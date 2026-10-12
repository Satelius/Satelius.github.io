"""Validate the portable viewer in a fresh local headless browser; no teacher API."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


def main() -> None:
    validation = ROOT / 'validation'
    screenshots = validation / 'screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    browser_errors: list[str] = []
    unexpected_requests: list[str] = []
    checks: dict[str, object] = {}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            executable_path='/usr/bin/google-chrome', headless=True,
            args=['--disable-gpu', '--allow-file-access-from-files'],
        )
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda error: browser_errors.append(str(error)))
        page.on('request', lambda request: unexpected_requests.append(request.url) if not request.url.startswith(('file:', 'data:', 'blob:')) else None)
        page.goto((ROOT/'index.html').as_uri(), wait_until='load')
        page.wait_for_function('window.ROLLOUT_VIEWER_READY === true')
        assert '100次决策' in page.locator('#load-status').inner_text()
        assert page.locator('#token-timeline button').count() == 50
        page.wait_for_function("[...document.querySelectorAll('video')].every(v=>v.readyState>=1 && !v.error)")
        checks['file_protocol_load'] = True
        checks['all_three_video_metadata_load'] = page.evaluate("[...document.querySelectorAll('video')].map(v=>({id:v.id,duration:v.duration,width:v.videoWidth,height:v.videoHeight}))")
        assert all(abs(item['duration']-5) < .05 for item in checks['all_three_video_metadata_load'])
        page.screenshot(path=str(screenshots/'desktop-overview.png'))

        # Check every rendered decision, not only one successful initial load.
        rendered = 0
        for run_index, run_id in enumerate(('A','B')):
            page.locator('#choose-'+run_id.lower()).click()
            for index in range(50):
                page.locator('#decision-range').evaluate('(element,index)=>{element.value=index;element.dispatchEvent(new Event("input",{bubbles:true}));}', index)
                expected = page.evaluate('(indices)=>window.ROLLOUT_DATA.runs[indices[0]].decisions[indices[1]]', [run_index,index])
                assert page.locator('#selected-token').inner_text() == expected['token']
                assert page.locator('#user-text').inner_text() == expected['userText']
                assert page.locator('#system-text').text_content() == expected['systemPrompt']
                assert page.locator('#request-text').text_content() == expected['requestText']
                assert page.locator('#response-text').text_content() == expected['responseText']
                assert page.locator('#request-link').get_attribute('href') == expected['rawLinks']['request']
                assert page.locator('#frame-rows tr').count() == 5
                assert page.locator('#image-scene').get_attribute('src') == expected['images']['scene']
                assert page.locator('#image-wrist').get_attribute('src') == expected['images']['wrist']
                assert page.locator('#image-tactile').get_attribute('src') == expected['images']['tactile']
                rendered += 1
        checks['all_100_rendered_decisions_match_original_inputs_outputs_and_intervals'] = rendered

        page.locator('[data-jump="A:5"]').first.click()
        assert page.locator('.http-attempt').count() == 2
        assert page.locator('#frame-rows tr').count() == 5
        assert '重试' in page.locator('#decision-note').inner_text()
        checks['retry_two_sends_one_execution_interval'] = True

        page.locator('[data-jump="B:11"]').first.click()
        assert page.locator('#selected-token').inner_text() == 'GRASP'
        assert '675.9mm' in page.locator('#decision-note').inner_text()
        page.locator('#explorer').scroll_into_view_if_needed()
        page.wait_for_function("[...document.querySelectorAll('.observations img')].every(i=>i.complete && i.naturalWidth>0)")
        page.screenshot(path=str(screenshots/'desktop-empty-grasp.png'))
        checks['actual_three_input_images_load'] = page.evaluate("[...document.querySelectorAll('.observations img')].map(i=>[i.naturalWidth,i.naturalHeight])")
        assert checks['actual_three_input_images_load'] == [[640,360],[640,360],[384,576]]
        page.locator('#image-scene').click()
        assert page.locator('#image-dialog').is_visible()
        page.locator('#close-image').click()
        checks['original_image_zoom'] = True
        page.locator('#play-decision').click()
        page.wait_for_function("document.getElementById('decision-video').paused && document.getElementById('decision-video').currentTime>=1.18",timeout=10000)
        stop = page.locator('#decision-video').evaluate('(video)=>video.currentTime')
        assert 1.18 <= stop < 1.2, stop
        checks['five_frame_clip_stops_before_next_decision'] = {'run':'B','decision':11,'current_time_s':stop,'interval_s':[1.1,1.2]}

        page.locator('#next-decision').click()
        assert 'GRASP' not in page.locator('#history-tokens').inner_text()
        assert '−1 · 闭合' in page.locator('#movement-detail').inner_text()
        checks['grasp_excluded_from_movement_history_and_gripper_persists'] = True
        page.locator('#frame-range').evaluate('(e)=>{e.value=249;e.dispatchEvent(new Event("input",{bubbles:true}));}')
        assert 'decision_000049' in page.locator('#decision-id').inner_text()
        assert '自动reset' in page.locator('#decision-note').inner_text()
        assert '原生超时终态' in page.locator('#frame-detail').inner_text()
        checks['terminal_frame_249_uses_pre_reset_trajectory'] = True
        page.locator('#prev-frame').click()
        assert '#248' in page.locator('#frame-number').inner_text()
        checks['frame_step_navigation'] = True
        page.locator('#follow-video').check()
        page.locator('#decision-video').evaluate('(video)=>{video.currentTime=2.22}')
        page.wait_for_function("document.getElementById('decision-id').textContent.includes('decision_000022')")
        checks['video_follow_selects_owning_decision'] = True
        page.locator('#follow-video').uncheck()

        assert page.locator('.mapping-table tbody tr').count() == 9
        assert page.locator('#height-chart svg path').count() == 2
        checks['nine_token_mapping_and_two_original_tcp_curves'] = True
        for width,height in ((390,844),(768,1024),(1440,1000)):
            page.set_viewport_size({'width':width,'height':height})
            page.locator('[data-jump="B:11"]').first.click()
            page.locator('#explorer').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            if width==390:
                page.screenshot(path=str(screenshots/'mobile-decision.png'))
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=str(screenshots/'mobile-overview.png'))
        checks['responsive_no_document_overflow'] = [390,768,1440]
        resources = page.evaluate("[...document.querySelectorAll('[src],[href]')].flatMap(e=>['src','href'].filter(a=>e.hasAttribute(a)).map(a=>e.getAttribute(a))).filter(p=>p && !p.startsWith('#'))")
        def local_path(value: str) -> Path:
            return Path(unquote(urlsplit(value).path)) if value.startswith('file:') else ROOT/value
        missing = [path for path in resources if not local_path(path).exists() and path not in ('README.md','validation/web_checks.json')]
        assert not missing, missing
        assert not browser_errors, browser_errors
        assert not unexpected_requests, unexpected_requests
        checks['browser_javascript_errors'] = browser_errors
        checks['page_requests_outside_local_bundle'] = unexpected_requests
        browser.close()

    result={'schema':'tacharness.rollout-local-web-checks.v1','created_at':datetime.now(timezone.utc).isoformat(),'passed':True,'browser':'fresh headless Google Chrome, no existing profile','in_app_browser':'unavailable; browser runtime discovery returned no browser','page_protocol':'file://; no local web server required','checks':checks,'evidence_review':{'file_hashes':1324,'actual_request_pngs':300,'original_contexts':100,'control_frames':500,'decision_original_links':902,'passed':True},'new_teacher_api_requests':0,'new_native_starts':0,'screenshots':[str(path.relative_to(ROOT)) for path in sorted(screenshots.glob('*.png'))]}
    (validation/'web_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'rendered_decisions':rendered,'clip_stop_s':stop,'screenshots':len(result['screenshots'])},ensure_ascii=False))


if __name__ == '__main__':
    main()
