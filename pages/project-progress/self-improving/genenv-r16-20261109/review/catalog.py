from pathlib import Path
import json, subprocess, hashlib, collections, re
from PIL import Image, ImageDraw, ImageFont
s=Path(__file__).resolve().parents[1]
def load(path):return json.loads((s/path).read_text())
def rel(p):return str(p.relative_to(s))
def link(label,path):return [label,str(path)]
def record(group,title,status,detail,media,links):
    assert (s/media).is_file(),media
    for _,p in links:assert (s/p).is_file(),p
    rows.append(dict(group=group,title=title,status=status,detail=detail,media=media,links=links))
rows=[]
for name,title in [('stove-origin','原始初态'),('stove-east','碗向东 3 cm'),('stove-west','碗向西 3 cm'),('drawer-east-v2','碗入抽屉 · 东侧')]:
    dirs=sorted(p.parent for p in (s/'runs').glob(name+'*/review.json'))
    for n,d in enumerate(dirs):
        j=load(d/'review.json');receipt=load(d/'receipt.json');req=load(d/'request.json');qualified=j['collection_qualified']
        err=max(v['xyz_error_m'] for v in receipt['reset_errors'].values())
        record('Tabero',f'{title} · {n+1}/3','通过' if qualified else '未通过',
          f'同源示教 #{req["source_demo"]}。初态位置误差 {err*1000:.4f} mm。原生连续成功 {j["max_native_steps"]} 帧，释放后最长合格窗口 {j["max_qualified_steps"]}/10 帧。',
          rel(d/'teacher.mp4'),[link('请求',rel(d/'request.json')),link('实际初态',rel(d/'teacher.reset.json')),link('逐帧评分',rel(d/'review.json')),link('命令与耗时',rel(d/'receipt.json'))])
record('Tabero','ACT 数据入口','通过','三个炉台初态各取一条回放。312 帧经项目转换器读入 ACT，双相机、双触觉、7 维状态与 20×7 动作块均可取样。三条回放共享一条源示教。','assets/tabero-window.png',[link('张量与数据身份','review/student-readback.json')])
for p in sorted((s/'runs').glob('*/trial-*/result.json')):
    j=load(p);d=p.parent;case=d.parent.name
    v2=j.get('rule')=='upward-support-retreat-v2'
    if case.startswith('confirmed-'):
        title=('香蕉近侧' if case=='confirmed-banana' else '失败反馈生成的方块布局')+' · 资格复验'
    elif case.startswith('grid-'):
        xi,yi=case.rsplit('_',2)[1:];title=['近','中','远'][int(xi)]+'距香蕉 · 横向 '+('−3 cm' if yi=='0' else '+3 cm')
    else:title={'cartesian-banana':'香蕉左置 · 抓放探针','cartesian-feedback':'方块反馈布局 · 抓放探针','yaw-banana':'香蕉左置 · 夹爪旋转 90°','chinese-native-v2':'中文请求 · 香蕉在碗左侧','audit-block':'方块原布局对照','audit-front-retry':'罐位于碗前 · 原生探针','audit-banana_right':'右侧香蕉 · 小碗目标'}[case]
    r=int(d.name.split('-')[1])+1
    status='通过' if j['qualified'] and v2 else '部分通过' if j['native'] else '未通过'
    rule='资格检查要求目标向上支撑、撤手 ≥5 cm' if v2 else '按两物接触与速度检查'
    record('RoboLab',f'{title} · s{j["seed"]} / {r}',status,
        f'{j["steps"]} 个控制步，最高抬升 {100*j["peak_lift_m"]:.1f} cm。原生成功 {int(j["native"])}，稳定窗口 {j["max_stable_s"]:.2f} s。{rule}。结束原因 {j["reason"]}。',
        rel(d/'scene.mp4'),[link('物理记录',rel(p)),link('逐步动作和状态',rel(d/'steps.jsonl')),link('任务模块',rel(Path(j['task'])))])
episodes=s/'runs/native1/robolab/AuditBananaFixedTask'
for line in (episodes/'results.jsonl').read_text().splitlines():
    j=json.loads(line);seed=j['seed'];ep=episodes/f'episode_{seed:03d}'
    a=list(map(json.loads,next((ep/'gpt_calls').glob('*.jsonl')).read_text().splitlines()))
    init=a[0]['observation']['objects']['banana']
    lift=max(x['observation']['objects']['banana'][2] for x in a)-init[2]
    record('RoboLab',f'原离散教师 · 香蕉左置 s{seed}','通过' if j['success'] else '未通过',
      f'保留原任务模块的 40 s 时限，记录 {j["steps"]} 帧、{j["decisions"]} 次决策。决策观测中香蕉最高抬升 {lift*100:.1f} cm，终止原因为 {j["end_reason"]}。',
      f'assets/teacher-episode_{seed:03d}.mp4',[link('教师记录',rel(ep/'summary.json')),link('动作与物体位置',rel(next((ep/'gpt_calls').glob('*.jsonl'))))])
record('UniVTAC','瓶入架 · 原始视频','部分通过','来自 UniVTAC 5.1 源轨迹，逐帧解码为 524 帧。模型读取 8 个有时间标记的采样帧，可见抬起与搬运；放置内部的接触和释放需要传感器证据。','assets/bottle-reference.mp4',[link('原始版本与阶段','review/bottle-source.json'),link('模型判读','review/video-answer.txt'),link('完整视频解码','review/ingest-video.json')])
record('UniVTAC','罐体规格 · 4 / 5 / 6 cm','部分通过','三个原版源 episode 可回读头部 RGB 与左右触觉。图中三组样本各保留原始文件哈希和帧号。','assets/can-reference.jpg',[link('源轨迹清单','review/can-source.json')])
record('UniVTAC','材料与形变 · CUDA','通过','新编译的 Python 3.12 绑定调用 sm_120 后端。相同体网格、接触对和落高下，10 kPa 材料最大压缩约 6.11 mm，1 MPa 约 0.085 mm。各记录 80 次 advance/retrieve。','assets/uipc-materials.png',[link('软材料','runs/uipc-materials/soft/result.json'),link('硬材料','runs/uipc-materials/firm/result.json'),link('编译入口','review/build_uipc.py')])
record('UniVTAC','瓶与架 · 6.0 初态','部分通过','旧单位四元数在 6.0 接口中被读成绕 x 轴翻转 180°。同一组网格的最低点分别落在地面下 499 mm 和 140 mm。适配层调整排列后继续执行到机器人及传感器初始化。','assets/uni-floor.png',[link('网格测量','review/uni-floor.json'),link('碰撞诊断','review/uni-native-13.log'),link('修正后日志','review/uni-native-14.log')])
record('生成接口','新几何 · 六棱柱','通过','英文请求生成了紫色六棱柱的视觉网格、凸碰撞网格、材质和来源记录。RoboTwin 创建真实动态物体，SAPIEN 步进 180 次，最后 30 步均有桌面接触冲量。','runs/mesh-runtime4/scene.mp4',[link('SAPIEN 测量','runs/mesh-runtime4/result.json'),link('网格来源',rel(next((s/'runs/new-mesh/objects').glob('*/generation_provenance.json')))),link('碰撞 OBJ',rel(next((s/'runs/new-mesh/objects').glob('*/collision/*.obj'))))])
record('生成接口','新关节 · 抽屉滑轨','通过','在本次诊断脚本中构造带限位和驱动的滑轨。160 个 PhysX 状态显示目标 120 mm、峰值 119.93 mm、闭合残差约 0.024 mm。视频以半速显示。后续机器人操作仍需任务绑定和教师。','runs/drawer-joint/motion.mp4',[link('关节场景','runs/drawer-joint/drawer.usda'),link('位移曲线','assets/drawer-travel.png'),link('全部物理步','runs/drawer-joint/readback.json')])
record('生成接口','USD 对象与材质修改','通过','移动、停用、灯光、加入有默认根节点的 USD 资产、质量、摩擦以及纹理替换均通过文件回读。缺失对象、无资产库和未知操作返回失败。物理合理性仍由下游仿真检查。','assets/mutator.png',[link('修复前','runs/mutation-before/review.json'),link('修复后','runs/mutation-after/review.json'),link('资产与材质','runs/asset-edits-fixed/review.json'),link('修改后 USD','runs/asset-edits-fixed/changed.usda')])
record('生成接口','反馈请求 · 坐标有效性','通过','NaN、越出工作区、缺少 y 的输入此前均能写入场景。修复后全部拒绝。既有诊断的 10 个方块坐标只移动质心约 3.6 mm，阶段强调仍需另行实现。','assets/mutator.png',[link('反例修复前','runs/guard-before/review.json'),link('修复后','runs/guard-after/review.json'),link('实际数据需求','review/feedback-input.json')])
record('生成接口','图片绑定 · 碗与炉台','部分通过','实际模型从输入中读出碗、炉具及其相对位置。单帧不能决定操作方向。复跑使用显式登记的炉台任务和原生初态，保留图片、模型回答、请求及实际物理回读。','assets/bowl-scene.png',[link('模型回答','review/image-answer.txt'),link('输入收据','review/ingest-image.json'),link('绑定请求','runs/stove-east-r1/request.json')])
# Produce diagnostic visuals only for compiler cases that stopped before rendering.
fontfile=s.parent/'.grill-qa/fonts/NotoSansCJKsc-Regular.otf'
def diagram(case,title,detail):
    p=s/'assets'/('diagnosis-'+case+'.png')
    img=Image.new('RGB',(900,290),'#eeeee6');draw=ImageDraw.Draw(img)
    titlefont=ImageFont.truetype(str(fontfile),33);body=ImageFont.truetype(str(fontfile),19)
    draw.text((35,28),title,fill='#1b392d',font=titlefont)
    lines=['']
    for char in detail[:125]:
        if draw.textlength(lines[-1]+char,font=body)>820:
            if len(lines)==2:break
            lines.append('')
        lines[-1]+=char
    draw.multiline_text((35,92),'\n'.join(lines),fill='#934b35',font=body,spacing=3)
    draw.text((35,171),'输入　→　解析　→　资产／求解　→　任务绑定',fill='#34564a',font=body)
    draw.text((35,226),'编译诊断 · 此次调用未记录仿真帧',fill='#5d695f',font=body);img.save(p)
    return rel(p)
for k,title in [('text','文字'),('image','图片'),('video','视频')]:
    j=load(f'review/x2-{k}.json'); receipt='review/managed-'+('image-separate' if k=='image' else k)+'.json'
    long=load(receipt); error=long['delivery']['error_code']
    pics=long['delivery']['images']
    media=rel(Path(pics[0])) if pics else diagram('canonical-'+k,'x2env · '+title,error)
    record('生成接口','x2env 原入口 · '+title,'未通过',f'首次终止码 {j.get("delivery",j)["error_code"]}。600 秒复跑的终止码 {error}。原生入口没有交付场景。',media,[link('首次收据',f'review/x2-{k}.json'),link('复跑收据',receipt),link('部署检查','review/providers.json')])
record('生成接口','x2env 查询、恢复与失败包','通过','已终止的文字、视频请求可查询。再次恢复时状态和版本均保持一致，两份失败包在新目录重新导出。',diagram('controller','工作流状态与归档','两份既有失败记录再次在新目录导出'),[link('状态与导出','review/controller.json')])
record('生成接口','SAPIEN 首次加载 · 三个启动故障','未通过','依次遇到 open3d 缺失、C++ 运行库版本不符、导入时强制读取杂物目录。后续六棱柱与 teal 方块均进入实际仿真。',diagram('sapien-init','SAPIEN 初始化','模型加载前中断，保留三次实际错误'),[link('依赖缺失','review/sapien-native.log'),link('运行库','review/sapien-native2.log'),link('杂物目录','review/sapien-native3.log')])
record('RoboLab','罐位于碗前 · 首次仿真中断','未通过','首次请求交换了操作物和目标物，被角色校验拒绝。纠正角色后的首次启动遇到 PhysX 显存分配错误。随后单独复跑取得完整 201 步录像。',diagram('front-oom','罐入碗 · 启动失败','PhysX 无法分配 1 GiB，场景未完成初始化'),[link('角色拒绝','review/probe-front.log'),link('显存错误','review/probe-front-correct.log'),link('复跑记录','review/probe-front-retry.log')])
entries=[('banana','香蕉资产漏映射'),('plate','方块与盘子的布局')]+[(x['case'],x['prompt']) for x in load('review/compiler-matrix.json')]
for name,title in entries:
    folder=s/'runs'/name; errors=list(folder.rglob('failure_report.json'));summary=folder/'example_summary.json'
    if errors:err=load(errors[0]);detail=err['code']+' · '+err['details'].get('error',err['blocker']);links=[link('失败收据',rel(errors[0]))]
    elif summary.exists():detail='资产目录、布局求解及原生任务模块已生成。该案例完成静态检查。';links=[link('场景摘要',rel(summary)),link('场景',rel(next(folder.glob('*.usda'))))]
    else:detail=(folder/'process.log').read_text().strip().splitlines()[-1];links=[link('绑定日志',rel(folder/'process.log'))]
    if summary.exists():
        media=diagram(name,title[:38],'编译完成 · 原生加载待验')
        record('生成接口',title,'部分通过',detail,media,links)
    else:record('生成接口',title,'未通过',detail,diagram(name,title[:38],detail),links)
record('生成接口','颜色约束 · 修复前','未通过','输入指定 teal。规则解析丢失了该颜色，编译器复用了已有方块。资产生成报告显示新增 0 个资产。',diagram('first-teal','颜色条件 · 原始结果','颜色词 teal 被丢弃，复用了 blue_block'),[link('解析规格',rel(next((s/'runs/proxy').glob('*/scene_spec.json')))),link('生成报告',rel(next((s/'runs/proxy').glob('*/asset_generation_report.json'))))])
record('生成接口','中文方位与数量词','通过','原请求因量词“一根”被拒绝。修复解析、主客体顺序及香蕉目录后，同一句话生成了 banana_1 在 bowl_1 左侧的场景，原生臂完成一次抓放。',rel(next((s/'runs/chinese-native-v2').glob('*/scene.mp4'))),[link('原请求',rel(next((s/'runs/cn').rglob('failure_report.json')))),link('生成规格',rel(next((s/'runs/cn-fixed').rglob('resolved_scene.json')))),link('实际回读',rel(next((s/'runs/chinese-native-v2').glob('*/result.json'))))])
record('生成接口','teal · 解析与新网格复跑','通过','修复后颜色保留为 teal。用仅含已生成六棱柱的目录重新提交，请求生成了带该材质的方块。SAPIEN 实跑 180 步，保留网格、材质与桌面接触。RoboLab 导入器遇到当前无法绑定的颜色会明确拒绝。','runs/teal-runtime/scene.mp4',[link('新网格',rel(next((s/'runs/teal-proxy/objects').glob('*/generation_provenance.json')))),link('物理回读','runs/teal-runtime/result.json'),link('RoboLab 颜色绑定日志','review/teal-robolab.log')])
record('生成接口','按实测距离生成移动提案','通过','移动提案使用机器人基座和目标的实测平面坐标。这个例子中目标距离缩短 10 cm；缺少坐标时不生成移动动作。','assets/mutator.png',[link('提案与距离','review/reach-proposal.json')])
for attempt in load('review/uni-outcomes.json'):
    name=attempt['name'];folder=s/'runs'/(name+'-startup');metadata=attempt['metadata']
    links=[link('启动收据',rel(folder/'startup.json'))]
    if (folder/'pregrasp.json').is_file():links.append(link('请求与初态',rel(folder/'pregrasp.json')))
    if (folder/'frames.jsonl').is_file():links.append(link('传感器与物体记录',rel(folder/'frames.jsonl')))
    if (folder/'calibration.json').is_file():links.append(link('空载标定',rel(folder/'calibration.json')))
    if (s/'runs'/('binding-'+name)/'request.json').is_file():links.append(link('视频与原生任务绑定',f'runs/binding-{name}/request.json'))
    if (folder/'native-result.json').is_file():links.append(link('原生结果',rel(folder/'native-result.json')))
    logname={'uni'+str(i):'uni-native-'+str(i) for i in range(19,26)}.get(name,name)
    if (s/'review'/f'{logname}.log').exists():links.append(link('原运行日志',f'review/{logname}.log'))
    if name.startswith('near-') or name=='far-fixed':links.append(link('瓶位置、轨迹与资格','review/bottle-qualification.json'))
    if (folder/'synchronized.mp4').is_file():links.append(link('双相机、双触觉同步录像',rel(folder/'synchronized.mp4')))
    if attempt['source_video']:links.append(link('原版录像',attempt['source_video']))
    sensed=attempt['telemetry']
    desc='6.0 头部和腕部相机启动，UIPC world 有效。'
    if sensed:desc+=f'共有 {sensed["n"]} 个采样状态，物理步与 UIPC 计数一致 {sensed["physics_equal_uipc"]} 次。'
    desc+=('原生结果 '+str(metadata['result'])+'。') if metadata else '本次停在任务完成前。'
    title={'uni19':'触觉 pad · reset 诊断','uni20':'UIPC 接触求解诊断','uni21':'预抓取与关节命令','uni22':'传感器与动作采样','uni23':'关节索引调试','uni24':'关节目标调试','uni25':'瓶入架 · 原始条件','bottle-near':'瓶入架 · 架近 / 瓶右','bottle-far':'瓶入架 · 架远 / 瓶左','bottle-air':'瓶入架 · 空载标定','air-isolated':'移动物体的空载探针','near-fixed':'修正抓取角 · 架近','far-fixed':'修正抓取角 · 架远','near-video-r2':'视频绑定 · 近架第 2 次','near-video-r3':'视频绑定 · 近架第 3 次'}.get(name,name.replace('can-v2-','罐 · 复跑 / ').replace('can-','罐 · 初跑 / ')+' cm')
    if name=='air-isolated':desc+='移动道具进行空载校验时，UIPC 抛出负碰撞时间断言，未产生可用零点。'
    if name=='near-video-r2':desc+='架子移位，瓶体结束时仍在低处。'
    if metadata and metadata.get('can_size'):desc+=f'加载尺寸 {metadata["can_size"]} cm。'
    record('UniVTAC',title,'部分通过' if metadata and metadata['result']=='success' else '未通过',desc,rel(folder/('synchronized.mp4' if (folder/'synchronized.mp4').is_file() else 'sampled.mp4' if (folder/'sampled.mp4').exists() else 'head.png')),links)
attempts=load('review/uni-attempts.json')
for i in range(1,19):
    name='uni-native-'+str(i);j=next(a for a in attempts if a['name']==name)
    reason=j['errors'][0] if j['errors'] else '初始化未生成可评分的轨迹，见原始日志。'
    record('UniVTAC',f'6.0 迁移 · 启动 {i:02d}','未通过',reason,diagram(name,'6.0 启动 '+str(i),reason),[link('原始启动日志','review/'+j['log'])])
(s/'assets/evidence.js').write_text('window.EVIDENCE='+json.dumps(rows,ensure_ascii=False).replace('</','<\\/')+';\n')
(s/'review/catalog.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(len(rows))
