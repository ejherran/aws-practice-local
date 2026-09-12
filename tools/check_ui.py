"""Optional headless UI regression checks; Python standard library only.

Supply an installed Chromium/Chrome executable. No downloads, live accounts,
running app, network requests or third-party Python packages are needed.
All database records are synthetic; output is written into a NEW directory.
"""
import argparse
import base64
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trainer.auth import Access
from trainer.banks import BankRepository, make_archive
from trainer.engine import Trainer
from trainer.storage import Storage
from tests.helpers import bank_data

VIEWS = ('home', 'mobile-menu', 'auth', 'question', 'rush', 'report',
         'history', 'admin', 'admin-fields', 'profile', 'session')


def json_for_script(value):
    """Keep fixture text inert inside an HTML script element."""
    return json.dumps(value).replace('<', '\\u003c')


def create_fixtures(directory):
    """Use a temporary isolated engine, never the application's data directory."""
    storage = Storage(Path(directory) / 'ui-fixtures.sqlite3')
    access = Access(storage)
    access.bootstrap_admin()
    access.reset_password('Admin', 'Synthetic-UI-password')
    with storage.connection() as con:
        user = access.public(con.execute('SELECT * FROM users WHERE id=1').fetchone())
    banks = BankRepository(storage)
    for archive in sorted((ROOT / 'banks').glob('*.zip')):
        banks.import_archive(archive.read_bytes())
    for index in range(24):
        manifest, questions = bank_data(bank_id=f'demo-{index:02d}')
        manifest['exam_code'] = f'DEMO-{index:02d}'
        manifest['title'] = {'en': f'Quality assurance certification {index + 1}',
                             'es': f'Certificación de prueba {index + 1}'}
        banks.import_archive(make_archive(manifest, questions))
    engine = Trainer(storage, banks)
    attempt = engine.create(1, 'aws-aif-c01', 'quiz')
    saved = engine.update(1, attempt['id'], {
        'revision': attempt['revision'], 'index': 0,
        'selected': [attempt['questions'][0]['options'][0]['id']]})
    report = engine.finish(1, attempt['id'], saved['revision'])
    rush = engine.create(1, 'aws-aif-c01', 'rush')
    engine.finish(1, rush['id'], rush['revision'])
    fixtures = {
        '/api/dashboard': engine.dashboard(1),
        '/api/banks': {'banks': banks.list()},
        '/api/admin/banks': {'banks': banks.list(admin=True)},
        '/api/admin/audit': {'items': []},
        '/api/session': {'user': user, 'authenticated': True, 'registration_open': True},
        'history': engine.history(1), 'attempt': attempt,
        'saved': saved, 'report': report, 'rush': rush,
    }
    for language in ('en', 'es'):
        fixtures[f'/locales/{language}.json'] = json.loads(
            (ROOT / f'web/locales/{language}.json').read_text(encoding='utf-8'))
    return fixtures


def run_browser_checks(fixtures, OUTPUT, BROWSER, widths, views):
    css = (ROOT / 'web/styles.css').read_text(encoding='utf-8')
    app_js = (ROOT / 'web/app.js').read_text(encoding='utf-8')
    favicon = 'data:image/svg+xml;base64,' + base64.b64encode((ROOT / 'web/favicon.svg').read_bytes()).decode()
    template = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    template = template.replace('<link rel="stylesheet" href="/styles.css">', '<style>' + css + '</style>')
    template = template.replace('<script src="/app.js" defer></script>', '')
    app_js = app_js.replace('src="/favicon.svg"', f'src="{favicon}"')
    test_js = r'''
    window.qaErrors = [];
    window.addEventListener('error', e => qaErrors.push(e.message));
    window.addEventListener('unhandledrejection', e => qaErrors.push(String(e.reason)));
    window.fetch = async (endpoint, options={}) => {
      let data = fixtures[endpoint];
      if (endpoint.startsWith('/api/history')) data = fixtures.history;
      if (endpoint === '/api/profile') data = {user:{...fixtures['/api/session'].user,...JSON.parse(options.body)}};
      if (endpoint === '/api/activity') data = fixtures['/api/session'];
      if (endpoint.startsWith('/api/attempts/')) data = endpoint.endsWith('/answer') ? fixtures.saved : fixtures.attempt;
      if (!data) throw new Error('Missing fixture: ' + endpoint);
      return new Response(JSON.stringify(data), {status:200,headers:{'Content-Type':'application/json'}});
    };
    '''
    checks = r'''
    setTimeout(async () => {
      const failures = [];
      function check(value, message) { if (!value) failures.push(message); }
      try {
        state.language = qaLanguage; state.bankQuery=''; state.selectedBank='';
        await renderRoute();
        check($$('.bank-menu-item').length === 26, '26 banks in menu');
        check($$('.bank-card').length === 1, 'single detail panel');
        const search=$('#bank-search'); search.value='clf'; search.dispatchEvent(new Event('input'));
        check($$('.bank-menu-item').length===1, 'search by code');
        $('.bank-menu-item').click();
        check(state.selectedBank==='aws-clf-c02', 'selected bank');
        check($('#bank-title').textContent.includes('Cloud'), 'selected title');
        check(local.get('practice-bank-1')==='aws-clf-c02', 'per-profile preference');
        check($('#bank-detail')===document.activeElement, 'selection moves focus to panel');
        if(innerWidth<=760) check(!$('#bank-menu').open, 'mobile menu collapses on selection');
        $('#bank-menu').open=true;
        $('#bank-search').value='unmatched'; $('#bank-search').dispatchEvent(new Event('input'));
        check($$('.bank-menu-item').length===0 && $$('.bank-card').length===1, 'no-results retains selected panel');
        $('#clear-bank-search').click();
        check($$('.bank-menu-item').length===26 && document.activeElement===$('#bank-search'), 'clear search restores list and focus');
        $('#bank-search').value='certificacion de prueba'; $('#bank-search').dispatchEvent(new Event('input'));
        check($$('.bank-menu-item').length===24, 'accent-insensitive bilingual search');
        state.bankQuery=''; state.selectedBank=''; await renderRoute();
        check(state.selectedBank==='aws-clf-c02', 'selection survives rerender');
        state.language=qaLanguage==='en'?'es':'en'; await renderRoute();
        check(state.selectedBank==='aws-clf-c02', 'selection survives language switch');
        state.user={...state.user,id:2}; state.selectedBank=''; await renderRoute();
        check(state.selectedBank==='aws-aif-c01', 'preferences isolated by profile');
        state.user={...fixtures['/api/session'].user}; state.language=qaLanguage;
        state.selectedBank='aws-aif-c01'; state.bankQuery=''; await renderRoute();
        const viewRoute = ['admin', 'admin-fields'].includes(qaView) ? 'admin' :
          ['history', 'profile'].includes(qaView) ? qaView :
          ['question', 'rush', 'report'].includes(qaView) ? 'attempt/qa' : 'home';
        history.replaceState(null,'','#'+viewRoute); renderHeader();
        if(qaView==='session') {
          const userCopy={...state.user};
          $('#confirm-dialog').showModal();
          fixtures['/api/session']={user:null,authenticated:false,registration_open:true};
          await checkSession();
          check(state.user===null && state.dashboard===null && state.attempt===null, 'expired UI clears private data');
          check(!!$('#auth-form') && !$('#confirm-dialog').open, 'expired UI closes modal and shows sign-in');
          state.user=userCopy;
          const savedFetch=window.fetch;
          let resolveOld;
          window.fetch=()=>new Promise(resolve=>resolveOld=resolve);
          const oldRequest=request('/api/session').catch(error=>handleError(error));
          clearSession(); state.user={...userCopy,id:2};
          resolveOld(new Response('{}',{status:200})); await oldRequest;
          check(state.user?.id===2, 'old request cannot sign out a new profile');
          window.fetch=savedFetch; clearSession(); renderHeader(); renderAuth();
        }
        if(qaView==='auth') { clearSession(); renderHeader(); renderAuth(); }
        if(qaView==='question') {
          state.attempt=fixtures.attempt; state.index=0;
          history.replaceState(null,'','#attempt/'+state.attempt.id); renderAttempt();
          const input=$('input[name=answer]'); input.focus(); window.scrollTo(0,250);
          const before=window.scrollY;
          await updateAnswer({selected:[input.value]});
          check(Math.abs(window.scrollY-before)<2, 'answer save preserves scroll');
          check(document.activeElement?.value===input.value, 'answer save preserves focus');
          check($('input[name=answer]:checked')?.value===input.value, 'saved answer retained');
          const realFetch=window.fetch;
          window.fetch=async()=>{throw new Error('Simulated offline');};
          await updateAnswer({selected:[]});
          check(state.saveFailed && $('input[name=answer]:checked')?.value===input.value, 'failed save retains server-confirmed answer');
          check(Math.abs(window.scrollY-before)<2, 'failed save preserves scroll');
          window.fetch=realFetch; state.saveFailed=false; $('#connection').classList.add('hidden'); $('#toast').classList.add('hidden');
          setIndex(1);
          check(state.index===1 && window.scrollY===0 && document.activeElement===$('.question-prompt'), 'next question scrolls to useful start');
          setIndex(0);
          $('.nav-panel details').open=true;
          check($$('.map button').every(button=>button.getBoundingClientRect().width>=43 && button.getBoundingClientRect().height>=43), '44px question map targets');
        }
        if(qaView==='profile') renderProfile();
        if(qaView==='rush') { state.attempt=fixtures.rush; history.replaceState(null,'','#attempt/'+state.attempt.id); renderAttempt(); }
        if(qaView==='admin-fields') { await renderAdmin(state.routeId); $('.bank-config').open=true; $('.bank-config').scrollIntoView(); }
        if(qaView==='report') { state.attempt=fixtures.report; renderReport(); }
        if(qaView==='history') await renderHistory(state.routeId);
        if(qaView==='admin') { await renderAdmin(state.routeId); $('.bank-config').open=true; }
        if(qaView==='mobile-menu') $('#bank-menu').open=true;
        if(qaView==='home' || qaView==='mobile-menu') window.scrollTo(0,0);
        check(document.documentElement.scrollWidth<=innerWidth+1, 'no horizontal overflow: '+document.documentElement.scrollWidth+'/'+innerWidth);
        check(qaErrors.length===0, 'runtime errors: '+qaErrors.join(';'));
        if(qaView==='home') {
          const copied=JSON.parse(JSON.stringify(state.dashboard));
          state.dashboard={...copied,banks:copied.banks.filter(b=>b.id!=='aws-aif-c01')};
          fixtures['/api/dashboard']=state.dashboard; await renderRoute();
          check(state.selectedBank!=='aws-aif-c01', 'disabled selection falls back');
          fixtures['/api/dashboard']=copied; state.selectedBank='aws-aif-c01'; await renderRoute();
        }
      } catch(e) { failures.push(e.stack); }
      document.title=failures.length ? 'QA FAIL' : 'QA PASS';
      const output=document.createElement('pre'); output.id='qa-result'; output.hidden=true;
      output.textContent=JSON.stringify({width:innerWidth,view:qaView,language:qaLanguage,failures}); document.body.append(output);
    }, 100);
    '''
    results = []
    for width in widths:
        for language in ('en', 'es'):
            for view in views:
                name = f'{view}-{language}-{width}'
                payload = (f'<script>var fixtures={json_for_script(fixtures)};var qaLanguage={json.dumps(language)};'
                           f'var qaView={json.dumps(view)};</script><script>{test_js}</script>'
                           f'<script>{app_js}</script><script>{checks}</script>')
                document = template.replace('</body>', payload + '</body>')
                # Windows Chrome enforces a 500px window minimum. An iframe gives
                # the application an exact narrow CSS viewport without scaling.
                (OUTPUT / 'viewport.html').write_text(document, encoding='utf-8')
                document = (f'<!doctype html><style>body{{margin:0}}iframe{{border:0;display:block}}</style>'
                            f'<iframe width="{width}" height="1100" src="viewport.html"></iframe>'
                            '<script>setTimeout(()=>{const result=document.querySelector("iframe").contentDocument'
                            '.querySelector("#qa-result");if(result)document.body.append(result.cloneNode(true));},1200);</script>')
                page = OUTPUT / 'render.html'
                page.write_text(document, encoding='utf-8')
                with tempfile.TemporaryDirectory(prefix='practice-browser-') as profile:
                    command = [BROWSER, '--headless', '--disable-gpu', '--disable-background-networking',
                               '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check',
                               '--force-device-scale-factor=1', '--hide-scrollbars', '--allow-file-access-from-files',
                               '--user-data-dir=' + profile, f'--window-size={max(600,width)},1100', '--virtual-time-budget=1800',
                               '--screenshot=' + str(OUTPUT / (name + '.png')), '--dump-dom', page.as_uri()]
                    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                match = re.search(r'<pre id="qa-result" hidden="">(.*?)</pre>', result.stdout, re.S)
                if not match:
                    print(result.stderr[-1500:])
                    raise RuntimeError('No browser test results: ' + name)
                record = json.loads(html.unescape(match.group(1)))
                results.append(record)
                print(json.dumps(record), flush=True)
    (OUTPUT / 'browser-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    if any(result['failures'] for result in results):
        raise SystemExit(1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', type=Path, required=True,
                        help='Path to an already installed Chromium/Chrome executable')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for screenshots, fixture HTML and results')
    parser.add_argument('--widths', type=int, nargs='+', default=[320, 390, 768, 1280])
    parser.add_argument('--views', nargs='+', choices=VIEWS, default=VIEWS)
    args = parser.parse_args()
    if not args.browser.is_file():
        parser.error('Browser executable does not exist.')
    if any(width < 320 or width > 2560 for width in args.widths):
        parser.error('Viewport widths must be between 320 and 2560 CSS pixels.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='practice-ui-fixtures-') as directory:
        run_browser_checks(create_fixtures(directory), output,
                           str(args.browser.resolve()), args.widths, args.views)
    print('UI regression checks passed. Output: ' + str(output))


if __name__ == '__main__':
    main()
