#!/usr/bin/env python3
"""Exercise an actual prepared local analysis; screenshots remain private."""
import argparse
import json
from pathlib import Path
import zipfile

from playwright.sync_api import expect, sync_playwright


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--analysis',required=True);parser.add_argument('--base-url',default='http://127.0.0.1:8770');parser.add_argument('--output',type=Path,default=Path('runtime/browser-proof'));args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1600,'height':1100},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'{args.base_url}/?analysis={args.analysis}&view=compare',wait_until='networkidle')
        expect(page.get_by_role('heading',name='See the difference, side by side.')).to_be_visible()
        page.wait_for_function('document.querySelectorAll("video").length === 2 && [...document.querySelectorAll("video")].every(v=>v.readyState>=2)',timeout=30000)
        assert page.locator('video').count()==2
        before=page.get_by_role('slider',name='Relative clip time').input_value()
        page.get_by_role('button',name='Play playback',exact=True).click();page.wait_for_timeout(650)
        page.get_by_role('button',name='Pause playback',exact=True).click()
        after=page.get_by_role('slider',name='Relative clip time').input_value();assert float(after)!=float(before)
        page.screenshot(path=str(args.output/'01-compare.png'),full_page=True)
        page.get_by_role('button',name='Reference 2',exact=False).click()
        page.wait_for_function('document.querySelectorAll("video").length === 2 && [...document.querySelectorAll("video")].every(v=>v.readyState>=2)')
        page.get_by_role('button',name='Add to report',exact=True).click()
        page.get_by_role('button',name='Explain observations',exact=True).click()
        page.get_by_role('button',name='Viewer wording',exact=True).click()
        page.get_by_role('button',name='Explain from evidence',exact=True).click()
        expect(page.get_by_text('LOCAL · DETERMINISTIC',exact=True)).to_be_visible()
        assert page.locator('.observation').count()>0
        page.screenshot(path=str(args.output/'02-explanation.png'),full_page=True)
        page.get_by_role('button',name='Export report',exact=True).click()
        page.get_by_role('checkbox',name='Include available source clips',exact=False).check()
        page.get_by_role('button',name='Prepare report · 1 episode',exact=True).click()
        link=page.get_by_role('link',name='Download ZIP',exact=True).first
        expect(link).to_be_visible(timeout=30000)
        with page.expect_download() as download:link.click()
        report=args.output/'downloaded-report.zip';download.value.save_as(str(report))
        with zipfile.ZipFile(report) as z:
            assert 'report.html' in z.namelist() and any(n.endswith('.mp4') for n in z.namelist())
            data=json.loads(z.read('report.json'));assert data['items']
            z.extractall(args.output/'report')
        page.screenshot(path=str(args.output/'03-report.png'),full_page=True)
        page.get_by_role('button',name='Quality & coverage',exact=True).click()
        expect(page.get_by_role('heading',name='Start with what you can see.')).to_be_visible()
        page.screenshot(path=str(args.output/'04-quality.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('button',name='Compare clips',exact=True).click()
        expect(page.get_by_role('heading',name='See the difference, side by side.')).to_be_visible()
        page.wait_for_timeout(200)
        mobile_width=page.evaluate('document.documentElement.scrollWidth')
        page.screenshot(path=str(args.output/'05-mobile.png'),full_page=True)
        assert mobile_width<=391,f'Mobile layout overflows: {mobile_width}'
        # The report opens independently of the app and its private API.
        report_page=browser.new_page(viewport={'width':1440,'height':1000})
        report_page.goto((args.output/'report/report.html').resolve().as_uri(),wait_until='load')
        expect(report_page.get_by_role('heading',name='Movement Lens',exact=True)).to_be_visible()
        report_page.screenshot(path=str(args.output/'06-portable-report.png'),full_page=True)
        browser.close()
    assert not errors,errors
    result={'analysis_id':args.analysis,'real_clips_decoded':True,'playback_clock_advanced':True,'local_explanation_has_citations':True,
            'report_download_includes_media':True,'portable_report_opened':True,'mobile_width':mobile_width,'browser_errors':errors}
    (args.output/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
