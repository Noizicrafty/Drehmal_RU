"""Install only the translation into an existing original Drehmal world."""
import argparse,json,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import install

ROOT=Path(__file__).resolve().parent.parent
def main():
 p=argparse.ArgumentParser(description='Русификатор существующего мира Drehmal')
 p.add_argument('--edition',choices=['base','dlc']);p.add_argument('--world',type=Path);p.add_argument('--target',type=Path)
 args=p.parse_args()
 if not args.edition:
  choice=input('Редакция: 1 — Apotheosis 2.2.2f; 2 — Primal Journey 3.0.6 [1]: ').strip()
  if choice not in ['','1','2']:raise ValueError('Выберите 1 или 2')
  args.edition='dlc' if choice=='2' else 'base'
 if not args.world:args.world=Path(input('Папка мира, в которой лежит level.dat: ').strip().strip('"'))
 world=args.world.expanduser().resolve()
 if not args.target:
  default=world.parent.parent if world.parent.name.lower()=='saves' else world.parent
  value=input('Папка игры с mods/config/resourcepacks ['+str(default)+']: ').strip().strip('"')
  args.target=Path(value) if value else default
 manifest=json.loads((ROOT/'manifests'/f'{args.edition}.json').read_text(encoding='utf8'))
 install.HERE=ROOT/'data'
 return install.patch(world,args.target.expanduser().resolve(),manifest)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('ОШИБКА:',e)
  (ROOT/'installation_error.log').write_text(traceback.format_exc(),encoding='utf8');sys.exit(1)
