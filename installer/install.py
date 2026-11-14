import argparse,concurrent.futures,datetime,gzip,hashlib,json,msvcrt,os,shutil,sys,traceback,urllib.request,zipfile
from pathlib import Path
from patch_engine import Patcher

HERE=Path(__file__).resolve().parent
def digest(p):
 h=hashlib.sha512()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def safe(root,name):
 p=(root/name).resolve()
 if not p.is_relative_to(root.resolve()):raise ValueError('Небезопасный путь в архиве: '+name)
 return p
def extract(z,root,prefix=''):
 for info in z.infolist():
  if not info.filename.startswith(prefix) or info.is_dir():continue
  p=safe(root,info.filename[len(prefix):]);p.parent.mkdir(parents=True,exist_ok=True)
  with z.open(info) as src,p.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
def get_file(name,manifest):
 p=HERE/'originals'/name;spec=manifest['files'][name]
 if not p.exists() or p.stat().st_size!=spec['size'] or digest(p)!=spec['sha512']:raise ValueError('Оригинал отсутствует или повреждён: '+name)
 return p
def patch(world,profile,manifest,fresh=False):
 if not (world/'level.dat').is_file():raise ValueError('В выбранной папке нет level.dat')
 if not (world/'datapacks/hi_drehmal.zip').is_file():raise ValueError('Не найден datapacks/hi_drehmal.zip')
 with zipfile.ZipFile(world/'datapacks/hi_drehmal.zip') as z:
  has_dlc=any(n.startswith('data/dlc/functions/modify/') for n in z.namelist())
 if has_dlc!=(manifest['edition']=='dlc'):raise ValueError('Выбрана другая редакция мира. Используйте соответствующий установщик.')
 backup_root=profile/('Russian_Backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
 copied=set()
 def backup(p):
  if fresh or p in copied:return
  try:relative=p.relative_to(profile)
  except ValueError:relative=Path('world')/p.relative_to(world)
  target=backup_root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);copied.add(p)
 payload=HERE/'translation_payload.json.gz'
 if digest(payload)!=manifest['payload_sha512']:raise ValueError('Повреждены данные русификатора')
 if digest(HERE/'Drehmal_RU.zip')!=manifest['ru_pack_sha512']:raise ValueError('Повреждён русский ресурспак')
 patcher=Patcher(json.loads(gzip.decompress(payload.read_bytes())))
 lock_path=world/'session.lock';lock_path.touch(exist_ok=True)
 with lock_path.open('r+b') as lock:
  try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  except OSError:raise ValueError('Мир открыт в Minecraft. Закройте его и повторите установку.')
  try:patcher.world(world,backup)
  finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
 rp=profile/'resourcepacks';rp.mkdir(parents=True,exist_ok=True)
 target=rp/'Drehmal_RU.zip'
 if target.exists():backup(target)
 shutil.copy2(HERE/'Drehmal_RU.zip',target)
 options=profile/'options.txt';lines=options.read_text(encoding='utf8').splitlines() if options.exists() else []
 if options.exists():backup(options)
 lines=[s for s in lines if not s.startswith('lang:')]
 found=False
 for i,line in enumerate(lines):
  if line.startswith('resourcePacks:'):
   try:packs=json.loads(line.split(':',1)[1])
   except ValueError:packs=['vanilla']
   packs=[p for p in packs if p!='file/Drehmal_RU.zip']
   if (rp/'Drehmal_Original.zip').exists() and 'file/Drehmal_Original.zip' not in packs:packs.append('file/Drehmal_Original.zip')
   packs.append('file/Drehmal_RU.zip');lines[i]='resourcePacks:'+json.dumps(packs,ensure_ascii=False);found=True
 if not found:
  packs=['vanilla']+(['file/Drehmal_Original.zip'] if (rp/'Drehmal_Original.zip').exists() else [])+['file/Drehmal_RU.zip'];lines.append('resourcePacks:'+json.dumps(packs,ensure_ascii=False))
 lines.append('lang:ru_ru');options.write_text('\n'.join(lines)+'\n',encoding='utf8')
 report={'edition':manifest['edition'],'world':str(world),'stats':dict(patcher.stats),'backup':str(backup_root) if copied else None}
 (profile/'Russian_Installation_Report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print('Готово. Мир:',world,flush=True)
 if copied:print('Резервная копия:',backup_root,flush=True)
 return report
def install_full(profile,manifest):
 if profile.exists() and any(profile.iterdir()):raise ValueError('Для новой установки выберите пустую папку профиля. Для готового мира выберите режим русификации.')
 print('Проверка оригинальных архивов…',flush=True)
 world_zip=get_file(manifest['world'],manifest);pack=get_file(manifest['mrpack'],manifest);rp=get_file(manifest['resourcepack'],manifest)
 profile.mkdir(parents=True,exist_ok=True)
 (profile/'INSTALLING.txt').write_text('Установка не завершена. При ошибке используйте новую пустую папку.\n',encoding='utf8')
 with zipfile.ZipFile(pack) as z:
  index=json.loads(z.read('modrinth.index.json'));print('Установка модов и настроек…',flush=True)
  for f in index['files']:
   if f.get('env',{}).get('client')=='unsupported':continue
   source=HERE/'downloads'/f['hashes']['sha512'];p=safe(profile,f['path'])
   if not source.exists() or digest(source)!=f['hashes']['sha512']:raise ValueError('Отсутствует или повреждён мод: '+f['path'])
   p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,p)
  extract(z,profile,'overrides/');extract(z,profile,'client-overrides/')
 world=profile/'saves'/manifest['world_name'];world.mkdir(parents=True)
 print('Распаковка чистой карты…',flush=True)
 with zipfile.ZipFile(world_zip) as z:extract(z,world)
 # Some original archives wrap the world in a top-level directory.
 if not (world/'level.dat').exists():
  levels=list(world.glob('*/level.dat'))
  if len(levels)!=1:raise ValueError('Не удалось определить корень мира')
  inner=levels[0].parent
  for p in list(inner.iterdir()):shutil.move(str(p),str(world/p.name))
  inner.rmdir()
 (profile/'resourcepacks').mkdir(exist_ok=True);shutil.copy2(rp,profile/'resourcepacks/Drehmal_Original.zip')
 print('Установка русского перевода…',flush=True);report=patch(world,profile,manifest,True)
 deps=index['dependencies'];text='Minecraft '+deps['minecraft']+'; Fabric Loader '+deps['fabric-loader']+'; Java 17 или новее.\nПапка игры: '+str(profile)+'\nВыделите 6–8 ГБ памяти.\nВыберите эту папку игры в своём лаунчере и откройте мир '+manifest['world_name']+'.\n'
 (profile/'LAUNCH_RU.txt').write_text(text,encoding='utf8');(profile/'INSTALLING.txt').unlink()
 return report
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--edition',choices=['base','dlc'],required=True);parser.add_argument('--target',type=Path);parser.add_argument('--world',type=Path);parser.add_argument('--patch-only',action='store_true');args=parser.parse_args()
 manifest=json.loads((HERE/'manifest.json').read_text(encoding='utf8'))
 if args.edition!=manifest['edition']:raise ValueError('Батник не соответствует архиву')
 print('Drehmal — '+('Primal Journey 3.0.6' if args.edition=='dlc' else 'Apotheosis 2.2.2f')+' — русский перевод\n',flush=True)
 if not args.target:
  print('1 — новая установка в пустую папку\n2 — русификация уже установленного мира')
  args.patch_only=input('Режим [1]: ').strip()=='2'
  if args.patch_only:
   args.world=Path(input('Папка мира с level.dat: ').strip().strip('"'))
   default=args.world.parent.parent if args.world.parent.name=='saves' else args.world.parent
  else:default=HERE.parent/('Drehmal_Primal_Journey_RU_Profile' if args.edition=='dlc' else 'Drehmal_RU_Profile')
  value=input('Папка игры ['+str(default)+']: ').strip().strip('"');args.target=Path(value) if value else default
 profile=args.target.expanduser().resolve()
 if args.patch_only:
  if not args.world:raise ValueError('Для --patch-only укажите --world')
  return patch(args.world.expanduser().resolve(),profile,manifest)
 return install_full(profile,manifest)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('\nОШИБКА:',e,flush=True)
  log=HERE/'installation_error.log';log.write_text(traceback.format_exc(),encoding='utf8');print('Подробности:',log);sys.exit(1)
