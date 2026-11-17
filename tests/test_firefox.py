#!/usr/bin/env python3
"""Real Firefox History and Dark Reader in isolated lab profiles, never the owner's browser.

Usage: python tests/test_firefox.py OUTDIR SIGNED_DARK_READER_XPI
The signed XPI is an explicit test dependency, not downloaded or installed on the host.
"""
import json
from pathlib import Path
import shlex
import sys
import time

from lab import ROOT, VM, install, shot, toggle, user, vmctl, wait_for

OUT = Path(sys.argv[1])
XPI = Path(sys.argv[2]).resolve()
PROFILE = '/tmp/win7-firefox-profile'
PAGE = 'http://127.0.0.1:8765/'
BROAD = 'browser { background-color: #131314 !important; }\n'
SCOPED = '#tabbrowser-tabpanels ' + BROAD
STATE = """
const sidebar=document.getElementById('sidebar');
function text(root) { return root.textContent + [...root.querySelectorAll('*')]
  .filter(e=>e.shadowRoot).map(e=>text(e.shadowRoot)).join(''); }
return {background:getComputedStyle(sidebar).backgroundColor,
        color:getComputedStyle(sidebar).color,
        dark:matchMedia('(prefers-color-scheme: dark)').matches,
        tabs:gBrowser.tabs.length,
        contentBackgrounds:[...document.querySelectorAll('#tabbrowser-tabpanels browser')]
          .map(b=>getComputedStyle(b).backgroundColor),
        history:text(sidebar.contentDocument).includes('Classic history fixture')};
"""
PREFS = r"""
return Object.fromEntries(Services.prefs.getChildList('').filter(k=>
  /^(browser\.theme\.|widget\.gtk\.|ui\.systemUsesDarkTheme$|extensions\.activeThemeID$|toolkit\.legacyUserProfileCustomizations\.stylesheets$)/.test(k)
).sort().map(k=>[k,[Services.prefs.prefHasUserValue(k),
  Services.prefs.getPrefType(k)==32?Services.prefs.getStringPref(k):
  Services.prefs.getPrefType(k)==64?Services.prefs.getIntPref(k):Services.prefs.getBoolPref(k)]]));
"""


def request(script=None, context='chrome', command=None, parameters=None):
    data = {'context': context, 'parameters': parameters if parameters is not None else {'script': script, 'args': []}}
    if command:
        data['command'] = command
    return json.loads(user('python /tmp/fixture_firefox.py <<\'JSON\'\n' + json.dumps(data) + '\nJSON'))


def select_page():
    request(f"gBrowser.selectedTab=[...gBrowser.tabs].find(t=>t.linkedBrowser.currentURI.spec=='{PAGE}'); return true;")


def options():
    request("const url=WebExtensionPolicy.getByID('addon@darkreader.org').getURL('ui/options/index.html'); "
            "let tab=[...gBrowser.tabs].find(t=>t.linkedBrowser.currentURI.spec==url); "
            "gBrowser.selectedTab=tab || gBrowser.addTab(url,{triggeringPrincipal:Services.scriptSecurityManager.getSystemPrincipal()}); return true;")
    wait_for(lambda: request('return document.title;', 'content') == 'Dark Reader settings', 'Dark Reader options')


def storage():
    options()
    return request('return Promise.all([browser.storage.local.get(null),browser.storage.sync.get(null)]);', 'content')


def content_dark():
    select_page()
    return request("return !!document.querySelector('style.darkreader');", 'content')


def history():
    request("window.SidebarController.show('viewHistorySidebar'); return true;")
    wait_for(lambda: request(STATE)['history'], 'genuine History entry')
    state = request(STATE)
    assert state['contentBackgrounds'] and set(state['contentBackgrounds']) == {'rgb(19, 19, 20)'}, state
    return state


def start(css):
    user(f"rm -rf {PROFILE}; mkdir -p {PROFILE}/chrome; "
         f"printf %s {shlex.quote(css)} >{PROFILE}/chrome/userChrome.css")
    prefs = {'browser.shell.checkDefaultBrowser': False, 'browser.aboutwelcome.enabled': False,
             'browser.startup.homepage_override.mstone': 'ignore', 'sidebar.revamp': True,
             'browser.tabs.inTitlebar': 0, 'toolkit.legacyUserProfileCustomizations.stylesheets': True}
    user(f"cat >{PROFILE}/user.js <<'EOF'\n" + ''.join(f'user_pref({json.dumps(k)}, {json.dumps(v)});\n' for k, v in prefs.items()) + 'EOF')
    user(f'systemd-run --user --collect -q env MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1 firefox --no-remote --marionette --profile {PROFILE} {PAGE}')
    wait_for(lambda: user('ss -lnt | grep -q :2828 && echo ready', check=False) == 'ready', 'lab Marionette port')
    wait_for(lambda: request(f"return gBrowser.browsers.some(b=>b.currentURI.spec=='{PAGE}');"), 'fixture tab opened')
    select_page()
    wait_for(lambda: request('return document.title;', 'content') == 'Classic history fixture', 'fixture page loaded')
    request("document.querySelector('textarea').value='unsaved Firefox work'; return true;", 'content')


def stop():
    user('pkill -TERM -u tester -x firefox')
    wait_for(lambda: user('pgrep -u tester -x firefox || true') == '', 'lab Firefox exited')


def assert_work(pid, preferences, windows=False):
    assert user('pgrep -u tester -x firefox') == pid, 'Firefox restarted'
    # Firefox derives this pref from the system theme itself; compare its exact dark value on return.
    follows_system = preferences['extensions.activeThemeID'][1] == 'default-theme@mozilla.org'
    expected = preferences | {'browser.theme.toolbar-theme': [False, 2]} if windows and follows_system else preferences
    actual = request(PREFS)
    assert actual == expected, f'Firefox appearance preferences changed: {expected!r} -> {actual!r}'
    select_page()
    assert request("return document.querySelector('textarea').value;", 'content') == 'unsaved Firefox work'
    assert user(f'cat {PROFILE}/chrome/userChrome.css') == SCOPED.strip(), 'profile CSS changed during toggle'
    backgrounds = request(STATE)['contentBackgrounds']
    assert backgrounds and set(backgrounds) == {'rgb(19, 19, 20)'}, backgrounds


def main():
    assert XPI.is_file(), f'missing signed Dark Reader test dependency: {XPI}'
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_firefox.py'), '/tmp/fixture_firefox.py')
    vmctl.transfer(VM, 'put', str(XPI), '/tmp/win7-darkreader.xpi')
    user('systemctl --user stop win7-firefox-http.service; mkdir -p /tmp/win7-firefox-page; '
         "printf '%s' '<!doctype html><title>Classic history fixture</title><body style=\"background:white;color:black\"><h1>Classic history fixture</h1><textarea></textarea>' >/tmp/win7-firefox-page/index.html; "
         'systemd-run --user --collect -q --unit=win7-firefox-http python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/win7-firefox-page')
    user('kwriteconfig6 --file kdeglobals --group KDE --key widgetStyle Breeze; '
         'dbus-send --session --type=signal /KGlobalSettings org.kde.KGlobalSettings.notifyChange int32:2 int32:0; '
         'plasma-apply-colorscheme BreezeDark >/dev/null; dconf write /org/gnome/desktop/interface/gtk-theme "\'Breeze\'"')
    start(BROAD)
    toggle('windows')
    assert history()['background'] == 'rgb(19, 19, 20)', 'negative control did not reproduce owner CSS defect'
    shot(OUT / '1-broad-selector-red.png')
    toggle('current')
    stop()

    start(SCOPED)
    pid, preferences = user('pgrep -u tester -x firefox'), request(PREFS)
    (OUT / 'firefox-preferences.json').write_text(json.dumps(preferences, indent=2) + '\n')
    wait_for(lambda: request(STATE)['dark'], 'Firefox follows dark current mode')
    original_dark = history()
    for cycle in range(3):
        toggle('windows')
        state = history()
        assert state['background'] == 'rgb(255, 255, 255)' and not state['dark'], state
        assert_work(pid, preferences, windows=True)
        shot(OUT / f'2-scoped-windows-{cycle}.png')
        toggle('current')
        assert history() == original_dark, 'current Firefox appearance/tabs did not return exactly'
        assert_work(pid, preferences)
    shot(OUT / '3-scoped-current.png')
    print('missing Dark Reader: live History light/dark, 3 exact round trips, preferences and unsaved work preserved')

    assert request(command='Addon:Install', parameters={'path': '/tmp/win7-darkreader.xpi', 'temporary': False}) == 'addon@darkreader.org'
    settings = storage()
    wait_for(content_dark, 'manual Dark Reader darkens fixture')
    toggle('windows')
    assert history()['background'] == 'rgb(255, 255, 255)'
    assert content_dark(), 'manual Dark Reader must not be misreported as automatically controlled'
    assert storage() == settings, 'Dark Reader settings changed'
    select_page()
    shot(OUT / '4-manual-darkreader-still-dark.png')
    toggle('current')
    assert storage() == settings
    assert_work(pid, preferences)
    print('manual Dark Reader: History unaffected; web content stays dark in Windows (documented limitation), exact settings preserved')

    options()
    request("[...document.querySelectorAll('button')].find(e=>e.textContent=='Automation').click(); return true;", 'content')
    request("document.querySelector('.automation__system-control__checkbox input').click(); return true;", 'content')
    time.sleep(1)
    settings = storage()
    for cycle in range(2):
        wait_for(content_dark, 'System Dark Reader on in dark current mode')
        toggle('windows')
        assert history()['background'] == 'rgb(255, 255, 255)'
        wait_for(lambda: not content_dark(), 'System Dark Reader off in Windows')
        assert storage() == settings
        assert_work(pid, preferences, windows=True)
        shot(OUT / f'5-system-darkreader-windows-{cycle}.png')
        toggle('current')
        wait_for(content_dark, 'System Dark Reader restored in dark current mode')
        assert storage() == settings
        assert_work(pid, preferences)
    print('System automation, Toggle on/off: content follows existing live signal without modifying settings, 2 exact round trips')

    toggle('windows')
    wait_for(lambda: not content_dark(), 'System Dark Reader removes styles before fixture disables it')
    # Disabling a dark content script does not remove its injected DOM styles. Start this case off/light.
    request("const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs'); return AddonManager.getAddonByID('addon@darkreader.org').then(a=>a.disable()).then(()=>true);")
    toggle('current')
    assert not content_dark(), 'disabled Dark Reader injected styles'
    toggle('windows')
    assert history()['background'] == 'rgb(255, 255, 255)'
    assert not content_dark(), 'disabled Dark Reader became active'
    toggle('current')
    assert request("const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs'); return AddonManager.getAddonByID('addon@darkreader.org').then(a=>a.userDisabled);") is True
    assert_work(pid, preferences)
    print('disabled Dark Reader: stays disabled through both directions; native History still light in Windows')
    request("const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs'); return AddonManager.getAddonByID('firefox-compact-dark@mozilla.org').then(a=>a.enable()).then(()=>true);")
    wait_for(lambda: request(PREFS)['extensions.activeThemeID'][1] == 'firefox-compact-dark@mozilla.org', 'explicit Dark theme selected')
    changed = request(PREFS)
    toggle('windows')
    assert_work(pid, changed, windows=True)
    assert request(STATE)['dark'], 'explicit Dark theme overridden'
    toggle('current')
    assert_work(pid, changed)
    print('explicit Firefox Dark theme user edit persists exactly, including dark Windows chrome (documented limit)')
    stop()
    user('systemctl --user stop win7-firefox-http; plasma-apply-colorscheme BreezeLight >/dev/null')
    print('ALL FIREFOX CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
