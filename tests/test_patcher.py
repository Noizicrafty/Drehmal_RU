import gzip,importlib.util,json,shutil,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
from patch_engine import Patcher
from nbt_io import nbt_strings
spec=importlib.util.spec_from_file_location('build',ROOT/'tools/build.py');build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
def tag(name,value):
 n=name.encode();v=value.encode();return b'\x08'+struct.pack('>H',len(n))+n+struct.pack('>H',len(v))+v
class PatcherTests(unittest.TestCase):
 def test_identifier_and_sign_font_context(self):
  en='{"text":"Burnt Templar"}';ru='{"text":"Обожжённый храмовник","font":"minecraft:ru_sign_5"}'
  d={'format':1,'text':{'damage':'ущерб','Burnt Templar':'Обожжённый храмовник'},'strings':{en:ru},'json_strings':{en:ru},'books':{},'chat':{},'members':{},'protected':[]}
  raw=b'\x0a\0\0'+tag('Name','damage')+tag('CustomName',en)+b'\x0a\x00\x0afront_text'+tag('Text1',en)+b'\0'+tag('Command',"summon cow ~ ~ ~ {CustomName:'"+en+"',Attributes:[{Name:damage,Base:12}]}")+b'\0'
  p=Patcher(d);out=p.nbt(raw);values={path:s for a,b,path,s in nbt_strings(out)}
  self.assertEqual(values[('Name',)],'damage')
  self.assertIn('Обожжённый',values[('CustomName',)])
  self.assertNotIn('ru_sign_',values[('CustomName',)])
  self.assertIn('ru_sign_',values[('front_text','Text1')])
  self.assertNotIn('ru_sign_',values[('Command',)])
  self.assertIn('Name:damage,Base:12',values[('Command',)])
  self.assertEqual(out,p.nbt(out))
 def test_known_translated_member_is_not_retranslated(self):
  import base64,hashlib
  original=b'tellraw @s {"text":"Artifact"}';translated='tellraw @s {"text":"Artifact"}\n'.encode()
  d={'text':{'Artifact':'Артефакт'},'strings':{},'json_strings':{},'books':{},'chat':{},'members':{hashlib.sha256(original).hexdigest():base64.b64encode(translated).decode()},'protected':[]}
  p=Patcher(d)
  self.assertEqual(p.member('a.mcfunction',original),translated)
  self.assertEqual(p.member('a.mcfunction',translated),translated)
 def test_baseline_corpus_keeps_verified_templates(self):
  d,report=build.compile_payload()
  self.assertFalse(report['custom_build']);self.assertEqual(len(d['books']),427);self.assertTrue(d['members'])
 def fixture(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
  shutil.copytree(ROOT/'translation',root/'translation');(root/'data').mkdir();shutil.copy2(ROOT/'data/translation_payload.json.gz',root/'data/translation_payload.json.gz')
  return root
 def test_override_updates_context_and_disables_old_snapshots(self):
  root=self.fixture();base=json.loads(gzip.decompress((root/'data/translation_payload.json.gz').read_bytes()))
  en=next(row[1] for rows in base['chat'].values() for row in rows if len(row[1])>35 and row[1] not in base['protected'])
  o={'text':{en:'Новый контекстный перевод.'},'strings':{},'json_strings':{},'books':{}}
  (root/'translation/overrides.json').write_text(json.dumps(o),encoding='utf8')
  d,report=build.compile_payload(root)
  rows=[row for rows in d['chat'].values() for row in rows if row[1]==en]
  self.assertTrue(rows);self.assertTrue(all(row[2]=='Новый контекстный перевод.' for row in rows));self.assertEqual(d['members'],{});self.assertTrue(report['custom_build'])
 def test_protected_name_cannot_be_overridden(self):
  root=self.fixture();names=json.loads((root/'translation/protected.json').read_text(encoding='utf8'))
  (root/'translation/overrides.json').write_text(json.dumps({'text':{names[0]:'Переведённое служебное имя'}}),encoding='utf8')
  with self.assertRaises(ValueError):build.compile_payload(root)
if __name__=='__main__':unittest.main()
