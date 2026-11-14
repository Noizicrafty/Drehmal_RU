import re,json
DEC=json.JSONDecoder()
def chat_spans(s):
 for m in re.finditer(r'\b(tellraw|title)\s+',s):
  pos=m.end();depth=0;quote=None
  while pos<len(s):
   c=s[pos]
   if quote:
    if c==quote and (pos==0 or s[pos-1]!='\\'):quote=None
   elif c in '\"\'':quote=c
   elif c=='[':depth+=1
   elif c==']':depth-=1
   elif c.isspace() and depth==0:break
   pos+=1
  while pos<len(s) and s[pos].isspace():pos+=1
  if m[1]=='title':
   mode=re.match(r'(title|subtitle|actionbar)\s+',s[pos:])
   if not mode:continue
   pos+=mode.end()
  try:obj,n=DEC.raw_decode(s[pos:])
  except:continue
  yield pos,pos+n,obj
 for m in re.finditer(r'\b(?:bossbar\s+(?:add\s+\S+|set\s+\S+\s+name)|scoreboard\s+objectives\s+(?:add\s+\S+\s+\S+|modify\s+\S+\s+displayname)|team\s+modify\s+\S+\s+(?:prefix|suffix|displayName))\s+',s,re.I):
  try:obj,n=DEC.raw_decode(s[m.end():])
  except:continue
  yield m.end(),m.end()+n,obj

def leaves(obj,path=()):
 if isinstance(obj,str):yield path,obj
 elif isinstance(obj,list):
  for i,v in enumerate(obj):yield from leaves(v,path+(i,))
 elif isinstance(obj,dict):
  if isinstance(obj.get('text'),str):yield path+('text',),obj['text']
  for key in ('extra','with','separator'):
   if key in obj:yield from leaves(obj[key],path+(key,))
  hover=obj.get('hoverEvent',{})
  if hover.get('action')=='show_text':
   key='contents' if 'contents' in hover else 'value'
   if key in hover:yield from leaves(hover[key],path+('hoverEvent',key))

def replace_chat(s,mapping):
 edits=[]
 for a,b,obj in chat_spans(s):
  changed=False
  for path,text in leaves(obj):
   new=mapping.get(text,text)
   if new==text:continue
   if not path:obj=new
   else:
    node=obj
    for key in path[:-1]:node=node[key]
    node[path[-1]]=new
   changed=True
  if changed:edits.append((a,b,json.dumps(obj,ensure_ascii=False,separators=(',',':'))))
 for a,b,new in sorted(edits,reverse=True):s=s[:a]+new+s[b:]
 return s
