from pathlib import Path
import json, io
import numpy as np
from PIL import Image,ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
import h5py
root=Path(__file__).resolve().parents[1]
asset=root/'assets'
font=Path('/workspace/summary-web/.grill-qa/fonts/NotoSansCJKsc-Regular.otf')
font_manager.fontManager.addfont(str(font));plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'axes.facecolor':'#f7f6f1','figure.facecolor':'#f7f6f1','axes.labelcolor':'#253a33','text.color':'#253a33','axes.edgecolor':'#86948c','xtick.color':'#46574d','ytick.color':'#46574d','font.size':12})
def load(p):return json.loads(p.read_text())
def out(name):plt.tight_layout();plt.savefig(asset/name,dpi=145,bbox_inches='tight');plt.close()
fig,ax=plt.subplots(figsize=(8,3.2))
grid=load(root/'review/banana-grid.json')
for row in grid['rows']:
    d=load(next((root/'runs'/('grid-'+row['case'])).glob('*/result.json')))
    x,y=d['initial_base_xyz']['banana'][:2]
    ax.scatter([x],[y],s=360,c='#247653' if d['qualified'] else '#ce934b' if d['native'] else '#ad4f42',edgecolors='#172d24')
    ax.annotate('支撑' if d['qualified'] else '原生成' if d['native'] else '失败',(x,y),xytext=(0,14),textcoords='offset points',ha='center',fontsize=10)
ax.set(xlim=(.455,.565),ylim=(-.17,-.055),xlabel='香蕉 x · m',ylabel='香蕉 y · m',title='六个实例的物理初态与单次教师结果');ax.grid(alpha=.12);out('banana-grid.png')
fig,ax=plt.subplots(1,2,figsize=(8.3,3.1))
for k,text in [('soft','10 kPa'),('firm','1 MPa')]:
 d=load(root/'runs/uipc-materials'/k/'result.json');x=np.array(d['thickness_m'])*1000
 ax[0].plot(np.array(d['y_min'])*1000,label=text);ax[1].plot(x,label=text)
for a in ax:a.legend(frameon=False);a.set_xlabel('UIPC 步数');a.grid(alpha=.15)
ax[0].set_title('体网格最低点 · mm');ax[1].set_title('体网格厚度 · mm');out('uipc-materials.png')
fig,ax=plt.subplots(figsize=(7,3.3))
for i,d in enumerate(load(root/'review/uni-floor.json')):
 ax.bar(i-.14,d['identity_bottom']*1000,width=.27,color='#247653',label='约定一致' if i==0 else None);ax.bar(i+.14,d['x180_bottom']*1000,width=.27,color='#ad4f42',label='顺序误读' if i==0 else None)
ax.axhline(0,c='black',lw=.8);ax.set(xticks=[0,1],xticklabels=['Shelf.usd','BottleLift.usd'],ylabel='模型最低点相对地面 · mm');ax.legend(frameon=False);out('uni-floor.png')
fig,ax=plt.subplots(figsize=(7.6,3.3))
for name,label in [('stove-east','炉台 · 东侧'),('stove-west','炉台 · 西侧'),('drawer-east-v2-r1','抽屉 · 东侧')]:
 d=load(root/'runs'/name/'review.json'); rows=d['measured_frames']; cols=list(rows[0]); print(name,cols)
 ax.bar(label,d['max_qualified_steps'],color='#247653' if d['collection_qualified'] else '#ad4f42')
ax.axhline(10,color='#8e6021',ls='--',lw=1.4,label='0.5 秒 / 10 帧');ax.legend(frameon=False);ax.set_ylabel('最长连续合格窗口 · 帧');out('tabero-window.png')
fig,ax=plt.subplots(figsize=(8,2.7))
d=load(root/'runs/drawer-joint/readback.json');a=d['steps'];t=np.array([v['clock'] for v in a]);ax.plot(t-t[0],[1000*v['command'] for v in a],ls='--',label='目标');ax.plot(t-t[0],[1000*v['xyz'][0] for v in a],label='PhysX 回读');ax.set(xlabel='仿真时间 · s',ylabel='位移 · mm');ax.legend(frameon=False);out('drawer-travel.png')
fig,ax=plt.subplots(figsize=(8.6,3.5));cases=['move','remove','light','missing','unknown','add','texture','friction']; labels=['移动','停用','灯光','缺失对象','未知操作','缺少资产','缺少纹理','未知摩擦操作']
for i,p in enumerate(['mutation-before','mutation-after']):
 d=load(root/'runs'/p/'review.json')
 for k,row in enumerate(d):
  ok=row['accepted']==(row['case'] in ['move','remove','light']) and (not row['accepted'] or row['readback'])
  ax.scatter(k,i,s=220,marker='s',c='#247653' if ok else '#ad4f42')
ax.set(xlim=(-.5,7.5),ylim=(-.7,1.7),yticks=[0,1],yticklabels=['修复前','修复后'],xticks=range(8),xticklabels=labels,title='USD 修改结果与文件回读一致性');ax.tick_params(axis='x',labelrotation=15);out('mutator.png')
# Three actual can source episodes with head view and matched optical observation.
src=Path('/runtime/TacHarness/outputs/univtac-lift-can')
meta=load(src/'source-metadata.json');strip=Image.new('RGB',(960,295),'#172a22');draw=ImageDraw.Draw(strip);rows=[]
for col,(ep,size) in enumerate([(1,4),(0,5),(2,6)]):
 p=src/'source'/f'{ep:03}.hdf5'
 with h5py.File(p) as h:
  assert meta[str(ep)]['can_size']==size
  n=len(h['step']);i=n//2
  for key,x,y,w,ht in [('observation/head/rgb',0,0,320,180),('tactile/left_tactile/rgb',0,180,160,90),('tactile/right_tactile/rgb',160,180,160,90)]:
   raw=h[key][i];im=Image.open(io.BytesIO(raw)).convert('RGB').resize((w,ht));strip.paste(im,(col*320+x,y))
  draw.text((col*320+5,275),f'{size} cm | episode {ep} | frame {i}/{n}',fill='white')
  rows.append(dict(ep=ep,size_cm=size,frame=i,total=n,source=load(src/'source'/f'{ep:03d}.receipt.json')['sha256']))
strip.save(asset/'can-reference.jpg',quality=92);(root/'review/can-source.json').write_text(json.dumps(rows,indent=2))
