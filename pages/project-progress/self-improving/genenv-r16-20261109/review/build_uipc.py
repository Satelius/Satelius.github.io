"""Rebuild only the CPython binding for Sim 6, sharing the existing sm_120 native libraries."""
import os, shlex, json, sysconfig, subprocess, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
base=Path('/runtime/UniVTAC/third_party/TacEx/source/tacex_uipc/build')
root=Path('/workspace/TacHarness-genenv/outputs/genenv-audit-20261109/uni60')
old=Path('/runtime/conda-envs/UniVTAC')
os.environ['UNIVTAC_GXX12']=str(old/'bin/x86_64-conda-linux-gnu-c++')
overlay=root/'overlay';overlay.mkdir(parents=True,exist_ok=True)
src=old/'lib/python3.11/site-packages/uipc'
shutil.copytree(src,overlay/'uipc',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','pyuipc*.so'))
items=[i for i in json.loads((base/'compile_commands.json').read_text()) if 'pyuipc.dir' in i['command']]
def compile(i):
    cmd=shlex.split(i['command']); obj=root/'obj'/i['output'];obj.parent.mkdir(parents=True,exist_ok=True)
    if obj.exists() and obj.stat().st_size:return
    cmd[cmd.index('-o')+1]=str(obj)
    cmd[cmd.index(str(old/'include/python3.11'))]=sysconfig.get_paths()['include']
    cmd=[v for v in cmd if v not in ('-flto=auto','-fno-fat-lto-objects','-O3','-O2')]
    cmd.append('-O0');subprocess.run(cmd,check=True,cwd=i['directory'])
with ThreadPoolExecutor(8) as pool: list(pool.map(compile,items))
d=Path(items[0]['directory']);cmd=shlex.split((d/'CMakeFiles/pyuipc.dir/link.txt').read_text())
cmd=[str(root/'obj'/(d.relative_to(base))/v) if v.endswith('.o') else v for v in cmd if v!='-flto=auto']
cmd[cmd.index('-o')+1]=str(overlay/'uipc/modules/Release/bin'/('pyuipc'+sysconfig.get_config_var('EXT_SUFFIX')))
subprocess.run(cmd,cwd=d,check=True)
print('linked',cmd[cmd.index('-o')+1],flush=True)
