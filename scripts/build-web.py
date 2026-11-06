#!/usr/bin/env python3
"""Build hashed demo assets. Source remains available; no runtime Node dependency."""
import hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];source=root/'assets';built=source/'built';built.mkdir(exist_ok=True)
manifest={}
with tempfile.TemporaryDirectory(prefix='kagnode-cli-web-') as scratch:
 for file in sorted(source.iterdir()):
  if file.suffix not in ('.css','.js'):continue
  out=Path(scratch)/file.name
  subprocess.run([os.environ.get('ESBUILD','esbuild'),str(file),'--minify','--target=es2020','--charset=utf8','--legal-comments=inline','--banner:'+file.suffix[1:]+'=/*! KagNode. CLI | Source retained in project repository. */','--outfile='+str(out)],check=True,capture_output=True)
  data=out.read_bytes();name=file.stem+'.'+hashlib.sha256(data).hexdigest()[:16]+file.suffix
  (built/name).write_bytes(data);manifest['/'+file.name]='/built/'+name
 for file in sorted(source.glob('*.html')):
  text=file.read_text()
  for old,new in manifest.items():text=text.replace('"'+old+'"','"'+new+'"')
  def inline(match):
   tag,attributes,code=match.groups();suffix='.js' if tag=='script' else '.css'
   if not code.strip() or tag=='script' and re.search(r'type=[\"\'](?:application/[^\"\']*json|importmap)',attributes):return match.group(0)
   out=subprocess.run([os.environ.get('ESBUILD','esbuild'),'--minify','--target=es2020','--charset=utf8','--loader='+suffix[1:]],input=code,text=True,capture_output=True,check=True).stdout
   return '<'+tag+attributes+'>'+out+'</'+tag+'>'
  text=re.sub(r'<(script|style)([^>]*)>(.*?)</\1>',inline,text,flags=re.S)
  (built/file.name).write_text(re.sub(r'>\s+<','><',text));manifest['/'+file.name]='/built/'+file.name
for file in built.iterdir():
 if '/built/'+file.name not in manifest.values():file.unlink()
(source/'ui-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Built',len(manifest),'minified demo assets and pages without source maps.')
