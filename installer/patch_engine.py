"""Portable text-only patcher for Minecraft Java worlds. Standard library only."""
import base64,collections,copy,gzip,hashlib,io,json,re,struct,zipfile,zlib
from pathlib import Path
from nbt_io import nbt_strings,region_chunks
from chat_components import chat_spans,leaves

def norm(s):return re.sub(r'\s+','',s.replace('\\n','\n').replace('\\r','\r'))
def plain(s):
 try:o=json.loads(s)
 except:return s
 def walk(o):
  if isinstance(o,str):return o
  if isinstance(o,list):return ''.join(map(walk,o))
  if isinstance(o,dict):return o.get('text','')+walk(o.get('extra',[]))
  return ''
 return walk(o)
def quoted(s,start):
 q=s[start];p=start+1;out=[]
 while p<len(s):
  c=s[p]
  if c==q:return ''.join(out),p+1
  if c=='\\' and p+1<len(s) and s[p+1] in [q,'\\']:out.append(s[p+1]);p+=2;continue
  out.append(c);p+=1
 raise ValueError('Unclosed SNBT string')
def page_spans(s):
 for m in re.finditer(r'\bpages\s*:\s*\[',s):
  p=m.end();pages=[]
  try:
   while True:
    while s[p].isspace():p+=1
    if s[p]==']':yield m.end()-1,p+1,pages;break
    if s[p] not in '\"\'':break
    value,p=quoted(s,p);pages.append(value)
    while s[p].isspace():p+=1
    if s[p]==',':p+=1
    elif s[p]!=']':break
  except (IndexError,ValueError):continue
def snbt_string(s):return "'"+s.replace('\\','\\\\').replace("'","\\'")+"'"
def put(o,path,value):
 if not path:return value
 node=o
 for k in path[:-1]:node=node[k]
 node[path[-1]]=value
 return o
def signature(o):return json.dumps(list(leaves(o)),ensure_ascii=False,separators=(',',':'))
def visible_name(path):
 return any(k in path for k in ['display','CustomBossEvents'])
def sign_path(path):return any(k in path for k in ['front_text','back_text','Text1','Text2','Text3','Text4'])
def restore_fonts(new,old):
 if isinstance(new,dict):
  if isinstance(new.get('font'),str) and new['font'].startswith('minecraft:ru_sign_'):
   original=old.get('font') if isinstance(old,dict) else None
   if isinstance(original,str) and not original.startswith('minecraft:ru_sign_'):new['font']=original
   else:new.pop('font')
  for k,v in list(new.items()):restore_fonts(v,old.get(k) if isinstance(old,dict) else None)
 elif isinstance(new,list):
  for i,v in enumerate(new):restore_fonts(v,old[i] if isinstance(old,list) and i<len(old) else None)
 return new
def font_value(s,old):
 try:o=json.loads(s);before=copy.deepcopy(o);original=json.loads(old)
 except (ValueError,TypeError):return s
 o=restore_fonts(o,original)
 return json.dumps(o,ensure_ascii=False,separators=(',',':')) if o!=before else s

class Patcher:
 def __init__(self,payload):
  self.data=payload;self.stats=collections.Counter();self.misses=collections.Counter()
  self.rules=payload['text'];self.exact=payload['strings'];self.books=payload['books'];self.chat=payload['chat'];self.members=payload['members'];self.json_strings=payload['json_strings'];self.protected=set(payload['protected'])
  self.finished_members={hashlib.sha256(base64.b64decode(v).replace(b'\r\n',b'\n')).hexdigest() for v in self.members.values()}
 def book(self,pages):
  key=norm(''.join(map(plain,pages)))
  if key in self.books:
   new=self.books[key]
   if pages!=new:self.stats['book_copies']+=1
   return new
  return pages
 def obj(self,o):
  if isinstance(o,dict):
   out={}
   for k,v in o.items():
    if k in {'text','title','description'} and isinstance(v,str):out[k]=self.rules.get(v,v)
    elif k=='pages' and isinstance(v,list) and all(isinstance(t,str) for t in v):out[k]=self.book(v)
    elif isinstance(v,(dict,list)):out[k]=self.obj(v)
    elif isinstance(v,str) and ('"text"' in v or 'pages:' in v):out[k]=self.text(v)
    else:out[k]=v
   return out
  if isinstance(o,list):return [self.obj(v) if isinstance(v,(dict,list)) else self.text(v) if isinstance(v,str) and ('"text"' in v or 'pages:' in v) else v for v in o]
  return o
 def component(self,s,sign=False):
  try:o=json.loads(s)
  except:return self.rules.get(s,s)
  if isinstance(o,str):return json.dumps(self.rules.get(o,o),ensure_ascii=False)
  key=json.dumps(o,sort_keys=True,ensure_ascii=False,separators=(',',':'))
  if key in self.json_strings:
   value=self.json_strings[key]
   return value if sign else font_value(value,s)
  new=self.obj(o)
  if not sign:new=restore_fonts(new,o)
  return json.dumps(new,ensure_ascii=False,separators=(',',':')) if new!=o else s
 def text(self,s):
  if s in self.exact:return self.exact[s]
  edits=[]
  for a,b,pages in page_spans(s):
   new=self.book(pages)
   if new!=pages:edits.append((a,b,'['+','.join(snbt_string(v) for v in new)+']'))
  for a,b,v in sorted(edits,reverse=True):s=s[:a]+v+s[b:]
  # Chat objects retain this release's command targets, click actions and styles.
  edits=[]
  for a,b,o in chat_spans(s):
   before=copy.deepcopy(o);context=self.chat.get(signature(o))
   if context:
    for path,en,ru in context:o=put(o,path,ru)
   else:
    for path,t in list(leaves(o)):o=put(o,path,self.rules.get(t,t))
   if o!=before:edits.append((a,b,json.dumps(o,ensure_ascii=False,separators=(',',':'))));self.stats['chat_messages']+=1
  for a,b,v in sorted(edits,reverse=True):s=s[:a]+v+s[b:]
  # JSON text components embedded as quoted SNBT values (names, lore, signs).
  edits=[];p=0
  while p<len(s):
   if s[p] not in '\"\'':p+=1;continue
   a=p
   try:value,p=quoted(s,p)
   except ValueError:break
   if value.lstrip().startswith(('{','[')) and '"text"' in value:
    prefix=s[max(0,a-100):a]
    sign=bool(re.search(r'(?:messages|Text[1-4])[^\n]{0,80}$',prefix))
    new=self.component(value,sign)
    if new!=value:edits.append((a,p,snbt_string(new) if s[a]=="'" else json.dumps(new,ensure_ascii=False)))
  for a,b,v in sorted(edits,reverse=True):s=s[:a]+v+s[b:]
  # Unquoted JSON in loot tables and item modifiers. Never translate identifiers.
  def sub(m):
   try:en=json.loads('"'+m[1]+'"')
   except:return m[0]
   ru=self.rules.get(en,en)
   return m[0][:m.start(1)-m.start()]+json.dumps(ru,ensure_ascii=False)[1:-1]+m[0][m.end(1)-m.start():] if ru!=en else m[0]
  return re.sub(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"',sub,s)
 def nbt(self,data):
  ls=[];ss=list(nbt_strings(data,ls));edits=[]
  for a,b,path in ls:
   pages=[s for x,y,pa,s in ss if a<=x<b and pa==path];new=self.book(pages)
   if new!=pages:
    raw=[v.encode('utf8') for v in new];assert all(len(v)<=65535 for v in raw)
    edits.append((a,b,b'\x08'+struct.pack('>i',len(raw))+b''.join(struct.pack('>H',len(v))+v for v in raw)))
  for a,b,path,s in ss:
   if any(x<=a<y for x,y,pa in ls):continue
   if not path:continue
   key=path[-1]
   if key=='Name' and not visible_name(path):continue
   if key=='Command':new=self.text(s)
   elif key in {'CustomName','Name','Lore','Text1','Text2','Text3','Text4','messages','filtered_messages','title','DisplayName','MemberNamePrefix','MemberNameSuffix','text'}:
    new=self.exact.get(s)
    if new is None:new=self.component(s,sign_path(path))
    if not sign_path(path):new=font_value(new,s)
   else:continue
   if new!=s:
    raw=new.encode('utf8',errors='surrogateescape');assert len(raw)<=65535;edits.append((a,b,struct.pack('>H',len(raw))+raw));self.stats['nbt_strings']+=1
  out=data
  for a,b,v in sorted(edits,reverse=True):out=out[:a]+v+out[b:]
  return out
 def member(self,name,raw):
  key=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
  if key in self.finished_members:return raw
  if key in self.members:
   self.stats['exact_members']+=1;return base64.b64decode(self.members[key])
  if name.endswith(('.mcfunction','.json','.mcmeta')):
   src=raw.decode('utf-8-sig')
   if name.endswith(('.json','.mcmeta')):
    try:o=json.loads(src);out=self.obj(o)
    except (ValueError,TypeError):out=None
    if out is not None and out!=o:return json.dumps(out,ensure_ascii=False,indent=2).encode('utf8')
   dst=self.text(src)
   if dst!=src:return dst.encode('utf8')
  elif name.endswith('.nbt'):
   gz=raw.startswith(b'\x1f\x8b');data=gzip.decompress(raw) if gz else raw;out=self.nbt(data)
   if out!=data:return gzip.compress(out) if gz else out
  return raw
 def archive(self,p,backup):
  with zipfile.ZipFile(p) as z:
   infos=z.infolist();updates={}
   for info in infos:
    if info.is_dir() or not info.filename.endswith(('.mcfunction','.json','.nbt','.mcmeta')):continue
    raw=z.read(info.filename);out=self.member(info.filename,raw)
    if out!=raw:updates[info.filename]=out
   if not updates:return
   backup(p);tmp=p.with_name(p.name+'.ru-tmp')
   with zipfile.ZipFile(tmp,'w') as dest:
    for info in infos:dest.writestr(copy.copy(info),updates.get(info.filename,z.read(info.filename)))
  with zipfile.ZipFile(tmp) as test:assert test.testzip() is None
  tmp.replace(p);self.stats['datapack_files']+=len(updates)
 def world(self,world,backup):
  for p in (world/'datapacks').glob('*.zip'):self.archive(p,backup)
  for j,p in enumerate(world.rglob('*.mca')):
   if p.parent.name=='poi':continue
   updates=[]
   for i,data in region_chunks(p):
    if not any(t in data for t in [b'CustomName',b'Command',b'pages',b'Lore',b'messages',b'Text1']):continue
    out=self.nbt(data)
    if out!=data:updates.append((i,zlib.compress(out)));self.stats['chunks']+=1
   if updates:
    backup(p)
    with p.open('r+b') as f:
     f.seek(0,2);f.write(b'\0'*((-f.tell())%4096))
     for i,comp in updates:
      f.seek(0,2);off=f.tell()//4096;block=struct.pack('>I',len(comp)+1)+b'\2'+comp;n=(len(block)+4095)//4096
      if n>255:raise ValueError('Chunk exceeds Anvil sector limit')
      f.write(block+b'\0'*(n*4096-len(block)));f.seek(i*4);f.write(((off<<8)|n).to_bytes(4,'big'))
    self.stats['regions']+=1
   if j%200==0:print('  Регионов проверено:',j,'; изменено:',self.stats['regions'],flush=True)
  for p in world.rglob('*.dat'):
   raw=p.read_bytes()
   if not raw.startswith(b'\x1f\x8b'):continue
   data=gzip.decompress(raw);out=self.nbt(data)
   if out!=data:backup(p);p.write_bytes(gzip.compress(out));self.stats['dat']+=1
