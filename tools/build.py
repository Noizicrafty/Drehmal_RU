"""Compile editable translation sources and optional overrides into a patch kit."""
from pathlib import Path
import argparse,base64,copy,gzip,hashlib,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
from chat_components import leaves
from patch_engine import put
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encode_page(p):return json.dumps(p,ensure_ascii=False,separators=(',',':'))
def parse_page(p):
 try:return json.loads(p)
 except ValueError:return p
def sync_component(source,target,delta):
 try:a=json.loads(source);b=json.loads(target)
 except (ValueError,TypeError):return delta.get(source,target)
 available=dict(leaves(b))
 for path,en in leaves(a):
  if en in delta and path in available:b=put(b,path,delta[en])
 return json.dumps(b,ensure_ascii=False,separators=(',',':'))
def compile_payload(root=ROOT):
 baseline=json.loads(gzip.decompress((root/'data/translation_payload.json.gz').read_bytes()))
 d={'format':baseline['format']}
 for key in ['text','strings','json_strings','chat','protected']:d[key]=load(root/'translation'/f'{key}.json')
 d['members']=json.loads(gzip.decompress((root/'translation/member_templates.json.gz').read_bytes()))
 books={};book_ids={};book_changed=False
 for p in sorted((root/'translation/books').glob('*.json')):
  b=load(p);key=b['source_key'];pages=b['pages']
  if not 1<=len(pages)<=100:raise ValueError('Книга должна содержать 1–100 страниц: '+p.name)
  if key in books:raise ValueError('Повтор исходного текста книги: '+p.name)
  books[key]=[encode_page(page) for page in pages];book_ids[b['id']]=key
  if [parse_page(v) for v in baseline['books'].get(key,[])]!=pages:book_changed=True
 if set(books)!=set(baseline['books']):book_changed=True
 d['books']=books
 o=load(root/'translation/overrides.json')
 if set(o)-{'text','strings','json_strings','books'}:raise ValueError('Неизвестный раздел overrides.json')
 delta={en:ru for en,ru in d['text'].items() if baseline['text'].get(en)!=ru}
 delta.update(o.get('text',{}))
 for en,ru in delta.items():
  if not isinstance(ru,str):raise ValueError('Перевод text должен быть строкой')
  if en in d['protected'] and ru!=en:raise ValueError('Служебное имя нельзя переводить: '+en)
 d['text'].update(delta)
 for key in ['strings','json_strings']:
  for en,ru in list(d[key].items()):
   if delta:d[key][en]=sync_component(en,ru,delta)
  d[key].update(o.get(key,{}))
 for key,rows in d['chat'].items():
  for row in rows:
   if row[1] in delta:row[2]=delta[row[1]]
 for ident,pages in o.get('books',{}).items():
  if ident not in book_ids:raise ValueError('Неизвестный ID книги: '+ident)
  if not 1<=len(pages)<=100:raise ValueError('Книга должна содержать 1–100 страниц')
  d['books'][book_ids[ident]]=[encode_page(v) for v in pages]
 changed=book_changed or any(d[k]!=baseline[k] for k in ['text','strings','json_strings','chat','protected','members']) or any(o.values())
 # Old whole-file snapshots must never overwrite a new editorial change.
 if changed:d['members']={}
 return d,{'custom_build':changed,'books':len(books),'text_rules':len(d['text']),'whole_file_templates':len(d['members'])}
def build(output,runtime_zip=None):
 d,report=compile_payload();kit=output/'Drehmal_RU_Patch';kit.mkdir(parents=True,exist_ok=True)
 for name in ['installer','manifests']:shutil.copytree(ROOT/name,kit/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copy2(ROOT/'Install_RU.bat',kit/'Install_RU.bat')
 (kit/'data').mkdir(exist_ok=True)
 payload=gzip.compress(json.dumps(d,ensure_ascii=False,separators=(',',':')).encode('utf8'),compresslevel=9,mtime=0)
 (kit/'data/translation_payload.json.gz').write_bytes(payload)
 with zipfile.ZipFile(kit/'data/Drehmal_RU.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted((ROOT/'resourcepack').rglob('*')):
   if p.is_file():z.write(p,p.relative_to(ROOT/'resourcepack').as_posix())
 for kind in ['base','dlc']:
  p=kit/'manifests'/f'{kind}.json';m=load(p)
  m['payload_sha512']=hashlib.sha512(payload).hexdigest();m['ru_pack_sha512']=hashlib.sha512((kit/'data/Drehmal_RU.zip').read_bytes()).hexdigest()
  p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 if runtime_zip:
  with zipfile.ZipFile(runtime_zip) as z:z.extractall(kit/'runtime')
  for p in (kit/'runtime').glob('python*._pth'):
   s=p.read_text();p.write_text(s if '..\n' in s else s.replace('.\n','.\n..\n'))
 readme=ROOT/'docs/PATCH_README.txt';shutil.copy2(readme,kit/'README_RU.txt')
 shutil.make_archive(str(output/'Drehmal_RU_Patch'), 'zip',output,kit.name)
 (output/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps(report,ensure_ascii=False));print(output/'Drehmal_RU_Patch.zip')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'dist');p.add_argument('--runtime-zip',type=Path);a=p.parse_args();build(a.output.resolve(),a.runtime_zip)
