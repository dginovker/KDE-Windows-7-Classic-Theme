#!/usr/bin/env python3
"""Drive packaged Explorer Preview, Close and rejected Folder Options saves in the lab."""
from pathlib import Path
from PIL import Image
from lab import *
from test_explorer import captions
from test_explorer_command_menus import words
import argparse, json, tempfile, time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('out', type=Path)
parser.add_argument('--lock-only', action='store_true', help='run only the immutable-key regression')
args=parser.parse_args()
out=args.out; out.mkdir(parents=True, exist_ok=True)
switcher = '/usr/bin/win7-classic'
original_mode = user(f'{switcher} status')
output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
scale = f'kscreen-doctor output.{output["name"]}.scale.'
tmp=user('mktemp -d /tmp/w7-42-extra.XXXXXXXX'); unit=Path(tmp).name
cfg=tmp+'/config'; listing=tmp+'/Proof'; options=cfg+'/win7-explorer-optionsrc'
def c(x,y): vmctl.pointer(VM,x,y,'left')
def k(*keys): vmctl.keys(VM,*['KEY_'+a for a in keys]); time.sleep(.28)
def cap(n):
 time.sleep(.6); f=out/(n+'.png');shot(f);return Image.open(f).convert('RGB')
def call(x,y,key):
 c(x,y);k(key)
def place(x,y,w,h):
 kwin_script(f'for(const w of workspace.windowList()) if(w.caption=="Proof"){{w.frameGeometry={{x:{x},y:{y},width:{w},height:{h}}}; workspace.activeWindow=w;}}')
def pid():
 return user(f'systemctl --user show {unit} -p MainPID --value')
def launch(x,y,w,h,second=False):
 user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} /usr/bin/win7-explorer {listing}' + (f' {tmp}/Survivor' if second else ''))
 wait_for(lambda:'Proof' in captions(),'Proof listing');place(x,y,w,h);print(user(f'pid=$(systemctl --user show {unit} -p MainPID --value);sha256sum /proc/$pid/exe'))
def fingerprint():
 return user(f'sha256sum {options} {cfg}/kdeglobals {cfg}/dolphinrc')
try:
 toggle('windows', executable=switcher)
 user(scale + '1')
 user(f'mkdir -p {cfg} {listing}/Child {tmp}/Survivor/Retained; cp ~/.config/kdeglobals {cfg}/; printf "[General]\nRememberOpenedTabs=false\n" > {cfg}/dolphinrc; printf "[General]\nOpenFoldersInNewWindow=false\n[View]\nShowHidden=false\nThumbnails=false\n" > {options}')
 with tempfile.NamedTemporaryFile(suffix='.png') as f:
  im=Image.new('RGB',(128,128),'#ff00d9');im.paste('#00f030',(64,0,128,128));im.save(f.name);vmctl.transfer(VM,'put',f.name,listing+'/Preview.png')
 assert vmctl.run(VM, f'chmod 644 {listing}/Preview.png', 10)[0] == 0
 if not args.lock_only:
  launch(256,120,768,560,second=True)
  wait_for(lambda:sorted(captions())==['Proof', 'Survivor'], 'two Explorer windows')
  origin_pid = pid()
  assert int(origin_pid) > 0
  def preview_count(im):
   return sum(r>225 and g<22 and b>185 for r,g,b in im.crop((805,213,1017,613)).get_flattened_data())
  assert preview_count(cap('preview-off'))==0
  c(300,194);k('L');k('P');cap('layout-preview-open'); c(575,262)
  wait_for(lambda:preview_count(cap('preview-real-file'))>1000,'real selected image shown in preview pane',12)
  k('F11'); assert preview_count(cap('preview-f11-off'))==0
  c(300,194);cap('organize-close');c(298,447);wait_for(lambda:captions()==['Survivor'],'Organize Close leaves the other Explorer window')
  assert pid() == origin_pid
  k('LEFTALT','D');vmctl.type_text(VM, f'{tmp}/Survivor/Retained\n')
  wait_for(lambda:captions()==['Retained'],'surviving window navigates')
  k('LEFTALT','LEFT');wait_for(lambda:captions()==['Survivor'],'surviving window goes Back')
  assert pid() == origin_pid
  cap('close-surviving-window');k('LEFTCTRL','W');wait_for(lambda:not captions(),'surviving window closes')
  print('PASS 100% preview pixels from actual file, Layout mnemonic, F11 and Organize Close')
 user(scale + '1.5');time.sleep(.7)
 for fault in (('locked-key',) if args.lock_only else ('permissions', 'locked-key')):
  if fault == 'locked-key':
   user(f"sed -i 's/^Thumbnails=/Thumbnails[\\$i]=/' {options}")
  launch(42,45,730,405)
  before=fingerprint(); call(129,179,'F');wait_for(lambda:'Folder Options' in captions(),'Options opened')
  k('LEFTALT','O');k('SPACE');k('LEFTALT','V');k('LEFTALT','H');k('LEFTALT','T');cap(f'{fault}-pending')
  if fault == 'permissions':
   user(f'chmod a-w {options} {cfg}; test ! -w {options} && test ! -w {cfg}')
  else:
   user(f"grep -Fx 'Thumbnails[$i]=false' {options} && test -w {options} && test -w {cfg}")
  k('ENTER')
  im=cap(f'{fault}-result'); warning=words(im,(380,245,940,560)); print(f'{fault} warning OCR:',repr(warning))
  actual=fingerprint()
  if actual != before:
   print('Before:',before,'\nAfter:',actual,'\nOptions:',user(f'cat {options}'))
  assert 'Could not save Explorer' in warning and actual == before, (fault, warning, actual)
  if fault == 'permissions':
   user(f'chmod u+w {cfg} {options}; test -w {options} && test -w {cfg}')
   assert fingerprint()==before;cap('writable-while-warning')
  k('ENTER');wait_for(lambda:captions()==['Proof'],'same Explorer after warning');assert fingerprint()==before
  c(381,288); k('ENTER'); wait_for(lambda:captions()==['Child'],'same-window child after rejection')
  k('LEFTCTRL','W');wait_for(lambda:not captions(),'fresh-process check');launch(42,45,730,405);assert fingerprint()==before
  c(381,288);k('ENTER');wait_for(lambda:captions()==['Child'],'same-window child after relaunch');assert fingerprint()==before
  k('LEFTCTRL','W');wait_for(lambda:not captions(),'Explorer closed')
  print(f'PASS 150% {fault}: no partial General/View edits; exact Explorer/KDE/Dolphin bytes and same-window opening through relaunch')
finally:
 user(f'chmod u+w {cfg}; systemctl --user stop {unit}; rm -r {tmp}',check=False)
 user(scale + str(output['scale']));toggle(original_mode, executable=switcher)
