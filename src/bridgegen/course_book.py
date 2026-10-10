"""Course-design book with complete result traceability for V0.12."""
from pathlib import Path
import json,re
import numpy as np
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.shared import Cm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .mathtype import add_equation
from .units import bridge_description

def book_pages(r,figs):
    c=r['input'];g=r['geometry'];a=r['analysis'];d=r['calculation_details'];t=r['loads']['traffic'];rx=r['reactions'];profile=r['code_profile']
    p=lambda s:('p',s)
    h=lambda s:('h2',s)
    eq=lambda s:('equation',s)
    tab=lambda title,heads,rows:('table',title,heads,[[str(v) for v in row] for row in rows])
    image=lambda key,caption:('image',str(figs[key]),caption)
    span=' + '.join(f'{v:g}' for v in g['spans']);fmt=lambda v,n=3:f'{float(v):.{n}f}'
    traces=d['live_trace'];controls=r['controls'][:8]
    desc=bridge_description(c,g);lanes=desc['lanes_per_deck']
    cases={v['id']:v for v in t['transverse_cases']}
    fully_loaded=max(t['transverse_cases'],key=lambda v:v['vertical_multiplier'])
    lane_factor=fully_loaded['lane_factor'];effective=fully_loaded['vertical_multiplier']
    def multiplier(trace,kind,bound):
        return cases[trace[kind]['transverse_case_'+bound]]['vertical_multiplier']
    def effect_rows(kind,keys):
        return [[v['name'],fmt(v['x'],2),*[fmt(a[kind+'_'+key][v['station_index']]/1000) for key in keys]] for v in traces]
    L=c['main_span'];ls=g['spans'][0];rs=g['spans'][2];length=g['total_length']
    mid=next(v for v in traces if v['name']=='主跨跨中');pier=next(v for v in traces if v['name']=='左主墩左侧')
    identity=[]
    if c.get('designer_name') or c.get('student_id'):
        identity.append(p(f'设计人：{c.get("designer_name","")}    学号：{c.get("student_id","")}'))
    for key,label in [('institution','学校'),('class_name','班级'),('supervisor','指导老师')]:
        if c.get(key):identity.append(p(label+'：'+c[key]))
    pages=[('封面',[p('桥梁工程课程设计'),p(desc['title']),p('作用效应、预应力与纵向整体验算计算书'),p(c['project_name']),
                   p('跨径布置：'+span+' m'),p('横断面：'+desc['arrangement']),*identity,p('计算日期：'+r['created_at'][:10])]),
    ('第1章 设计依据与计算模型',[
        h('1.1 计算依据与范围'),
        p('本计算书按《公路桥涵设计通用规范》（JTG D60—2015）计算恒载、公路Ⅰ级汽车荷载、横向车道工况及作用组合；按《公路钢筋混凝土及预应力混凝土桥涵设计规范》（JTG 3362—2018）计算预应力、普通钢筋初配、正截面抗弯、斜截面抗剪、抗裂、使用阶段压应力、活载挠度和施工阶段压应力。'),
        p(f'计算对象为单幅主梁。'+('左右幅尺寸相同、互为镜像，各幅分别承受自身恒载及本幅汽车荷载。' if desc['deck_count']==2 else '双向两条车道位于同一幅桥面，共同作用于本幅主梁。')+f'本幅共有{lanes}条车道。本计算书按任务书完成纵向主梁计算与具名验算；横向板壳、局部实体、空间扭转和下部结构承载力属于本次课程设计范围外，不影响课程任务完成状态。'),
        h('1.2 设计参数'),
        tab('表1-1 主要设计参数',['项目','采用值'],[
            ['跨径布置',span+' m'],['横断面布置',desc['arrangement']],['单幅梁宽 / 两幅净距（单幅不计）',f'{g["width"]:.2f} / {desc["gap"]:.2f} m'],
            ['含净距总宽',f'{g["total_width"]:.2f} m'],['混凝土等级',c['concrete']],
            ['混凝土弹性模量',f'{r["material"]["E"]:g} MPa'],['混凝土容重',f'{c["concrete_weight"]:g} kN/m³'],
            ['结构重要性系数',f'{c["importance_factor"]:g}'],['汽车荷载等级','公路Ⅰ级'],
            ['规范配置',profile['id']],['计算状态',r['status_code']]]),
        h('1.3 计算模型及符号'),
        p(f'每幅采用变截面欧拉—伯努利平面连续梁模型，共{r["verification"]["elements"]}个单元、{r["verification"]["mesh_nodes"]}个节点。各支点约束竖向位移，转角自由；单元按中点截面取面积和惯性矩。梁单元采用三次位移插值、一致荷载向量和一致质量矩阵。'),
        eq(r'K u=F,\quad (EI)_e=E_c I_e'),
        p('纵向坐标从左桥台支承轴线起算。弯矩以下缘受拉为正，剪力按截面左侧向上为正；支点左、右侧分别列值。全部内力和反力均为单幅结果。恒载按成桥连续体系施加。')]),
    ('第2章 几何尺寸与截面特性',[
        h('2.1 横断面尺寸'),
        eq(rf'B={lanes}\times{c["lane_width"]:g}+2\times{c["barrier_width"]:g}+{c["inner_margin"]:g}+{c["outer_margin"]:g}={g["width"]:g}\;\mathrm{{m}}'),
        p(f'上式各项依次为{lanes}条车道、两侧护栏占宽、两侧预留带。单幅为单箱单室，顶板设横坡，箱底横向水平；箱内顶板与腹板交接设加腋，底板与腹板交接设倒角。'),
        tab('表2-1 箱梁构造尺寸',['项目','尺寸'],[
            ['悬臂长度 / 顶面横坡',f'{c["cantilever_width"]:g} m / {c["cross_slope"]*100:g}%'],
            ['顶板中部 / 悬臂端厚度',f'{c["top_thickness"]:g} / {c["tip_thickness"]:g} m'],
            ['跨中 / 墩顶底板厚度',f'{c["bottom_mid"]:g} / {c["bottom_pier"]:g} m'],
            ['跨中 / 墩顶腹板厚度',f'{c["web_mid"]:g} / {c["web_pier"]:g} m'],
            ['上部加腋（水平×竖向）',f'{c["top_haunch_horizontal"]:g} × {c["top_haunch_vertical"]:g} m'],
            ['下部倒角（水平×竖向）',f'{c["bottom_chamfer_horizontal"]:g} × {c["bottom_chamfer_vertical"]:g} m']]),
        h('2.2 梁高与纵向变截面'),p('梁高按参考尺寸与主跨之比初选，跨中与墩顶分别为：'),
        eq((rf'h_m=\max\left(1.8,{c["height_mid"]:g}\times\frac{{{L:g}}}{{{c["height_reference_span"]:g}}}\right)' if c['height_mid']*L/c['height_reference_span']<1.8 else rf'h_m={c["height_mid"]:g}\times\frac{{{L:g}}}{{{c["height_reference_span"]:g}}}')+rf'={g["height_mid"]:g}\;\mathrm{{m}}'),
        p('跨中梁高按比例缩放后采用1.80 m构造下限；箱室净高还应满足板厚、加腋和倒角共同形成的几何约束。'),
        eq(rf'h_p={c["height_pier"]:g}\times\frac{{{L:g}}}{{{c["height_reference_span"]:g}}}={g["height_pier"]:g}\;\mathrm{{m}}'),
        eq(rf'h(x)=h_m+(h_p-h_m)t(x)^{{{c["height_curve_exponent"]:g}}}'),
        p(f'左边跨内，t=x/{ls:g}；主跨内，t为距主跨跨中距离的绝对值除以{L/2:g}；右边跨内，t=({length:g}−x)/{rs:g}。底板厚度和腹板厚度采用相同幂函数，由跨中值过渡至墩顶值。'),
        h('2.3 截面面积与惯性矩'),
        p('截面由实体外轮廓减去箱室空腔组成。对两条多边形边界进行带符号积分求面积、形心及惯性矩，加腋和倒角均计入实体混凝土。'),
        eq(r'A=A_o-A_v,\quad I=I_{o,0}-I_{v,0}-Ay_c^{2}'),
        p('下标o、v分别表示外轮廓和空腔；惯性矩下标0表示相对同一横向基准轴，y的下标c表示混凝土截面形心距该轴的距离。'),
        tab('表2-2 单幅主要截面特性',['截面','梁高 / m','面积 / m²','惯性矩 / m⁴','上缘W / m³','下缘W / m³'],[[v['name'],fmt(v['height']),fmt(v['area']),fmt(v['inertia']),fmt(v['section_modulus_top']),fmt(v['section_modulus_bottom'])] for v in controls[:5]])]),
    ('第3章 恒载作用及内力计算',[
        h('3.1 一期恒载：主梁自重'),
        p('主梁自重由各单元中点的实际混凝土截面面积计算，沿桥长为变值分布。第e单元的自重线荷载为：'),
        eq(r'g_{1,e}=\gamma_c A_e'),
        p('左主墩和主跨跨中截面的自重线荷载分别为：'),
        *[eq(rf'g_{{1,{i+1}}}={c["concrete_weight"]:g}\times{v["area"]:.4f}={c["concrete_weight"]*v["area"]:.3f}\;\mathrm{{kN/m}}') for i,v in enumerate([controls[2],controls[4]])],
        p('以上为截面自重取值示例，有限元计算使用单元中点面积。'),
        tab('表3-1 典型单元自重',['单元范围 / m','面积 / m²','自重 / (kN/m)'],[
            [f'{d["elements"]["x0"][j]:.2f}～{d["elements"]["x1"][j]:.2f}',fmt(d['elements']['area'][j],4),fmt(d['elements']['dead1'][j])]
            for j in sorted(set([0,int(np.argmax(d['elements']['dead1'])),int(np.argmin(abs((np.array(d['elements']['x0'])+np.array(d['elements']['x1']))/2-mid['x']))),len(d['elements']['x0'])-1]))]),
        eq(rf'G_1=\sum_e g_{{1,e}}l_e={d["dead1_weight"]:.3f}\;\mathrm{{kN}}'),
        p(f'单幅主梁几何体积为{r["quantities"]["concrete_per_deck_m3"]:.3f} m³。各单元自重线荷载为{r["loads"]["dead1_min"]:.3f}～{r["loads"]["dead1_max"]:.3f} kN/m。此项数量对应模型中的纵向主梁实体。'),
        h('3.2 二期恒载：铺装、护栏及附加恒载'),
        p('铺装宽度取单幅梁宽扣除两侧护栏占宽。护栏线荷载输入值表示本幅两侧护栏合计。'),
        eq(rf'b_s={g["width"]:g}-2\times{c["barrier_width"]:g}={d["pavement_width"]:g}\;\mathrm{{m}}'),
        eq(rf'g_s={d["pavement_width"]:g}\times{c["pavement_thickness"]:g}\times{c["pavement_weight"]:g}={d["pavement_load"]:.3f}\;\mathrm{{kN/m}}'),
        eq(rf'g_2={d["pavement_load"]:.3f}+{c["barrier_line_load"]:g}+{c["other_dead_load"]:g}={r["loads"]["dead2"]:.3f}\;\mathrm{{kN/m}}'),
        tab('表3-2 二期恒载汇总',['项目','线荷载 / (kN/m)'],[['铺装',fmt(d['pavement_load'])],['两侧护栏合计',fmt(c['barrier_line_load'])],['其他附加恒载',fmt(c['other_dead_load'])],['二期恒载合计',fmt(r['loads']['dead2'])]]),
        eq(rf'G_2={r["loads"]["dead2"]:.3f}\times{length:g}={d["dead2_weight"]:.3f}\;\mathrm{{kN}}'),
        h('3.3 恒载内力计算'),
        p('分别组装一期、二期恒载的一致节点荷载，求解节点位移后，按单元端力恢复弯矩和剪力。变截面连续梁内力由整桥刚度方程求解。下式q为有符号的竖向荷载，自重向下取负。'),
        eq(r'F_e=q_e[l_e/2,\;l_e^2/12,\;l_e/2,\;-l_e^2/12]^T'),
        eq(r'K u_{G1}=F_{G1},\quad K u_{G2}=F_{G2}'),eq(r'S_G=S_{G1}+S_{G2}'),
        tab('表3-3 单幅恒载弯矩（MN·m）',['截面','x / m','一期','二期','合计'],effect_rows('M',['dead1','dead2','dead'])),
        tab('表3-4 单幅恒载剪力（MN）',['截面','x / m','一期','二期','合计'],effect_rows('V',['dead1','dead2','dead']))]),
    ('第4章 汽车活载作用及内力计算',[
        h('4.1 车道荷载取值'),
        p(f'采用公路Ⅰ级车道荷载，每幅共有{lanes}条车道，全部车道启用时横向车道系数为{lane_factor:g}；各实际车道工况分别按启用车道数读取规范系数。连续梁按最大计算跨径{L:g} m确定集中荷载；本程序主跨范围为50～150 m，均不小于50 m，弯矩计算采用集中荷载{t["pk"]:g} kN。计算剪力和反力时集中荷载乘{t["shear_point_factor"]:g}。'),
        eq(rf'q_k={t["qk"]:g}\;\mathrm{{kN/m}},\quad P_k={t["pk"]:g}\;\mathrm{{kN}}'),
        eq(rf'P_{{k,V}}={t["shear_point_factor"]:g}\times{t["pk"]:g}={t["shear_point_factor"]*t["pk"]:g}\;\mathrm{{kN}}'),eq(rf'n\xi={lanes}\times{lane_factor:g}={effective:g}'),
        h('4.2 基频与冲击系数'),
        p('质量由主梁自重及二期恒载换算，一致质量矩阵与刚度矩阵施加相同支承约束，求解一阶竖弯自振频率：'),
        eq(r'm_e=\frac{g_{1,e}+g_2}{9.80665}'),eq(r'(K-\omega_1^2 M)\phi_1=0'),
        eq(rf'f_1=\frac{{\omega_1}}{{2\pi}}={t["frequency_hz"]:.4f}\;\mathrm{{Hz}}'),
        p('按JTG D60—2015第4.3.2条，频率小于1.5 Hz时冲击系数为0.05；1.5～14 Hz时为0.1767 ln(f)−0.0157；大于14 Hz时为0.45。'),
        eq(rf'\mu={t["impact"]:.4f},\quad 1+\mu={1+t["impact"]:.4f}'),
        h('4.3 横向车道位置与工况'),
        p(f'本幅{lanes}条车道按实际中心线分别编号，枚举所有非空车道组合，共{len(t["transverse_cases"])}个横向工况。每个工况按启用车道数乘以对应横向车道系数，纵向整体弯矩、剪力和位移采用单箱整体截面求和，并保存控制横向工况。偏载的横向位置和偏心距已记录，空间扭转响应留待后续空间模型计算。'),
        tab('表4-1 横向车道工况',['工况编号','工况名称','启用车道','车道中心 / m','竖向倍率','合力偏心 / m'],[
            [v['id'],v['name'],'、'.join(map(str,v['active_lanes'])),'、'.join(fmt(x,2) for x in v['lane_centres_m']),fmt(v['vertical_multiplier'],2),fmt(v['resultant_eccentricity_m'],2)] for v in t['transverse_cases']]),
        h('4.4 纵向影响线与最不利布载'),
        p('沿每个梁单元以4点高斯积分求影响线同号区段面积；集中荷载位置同时检查高斯点、全部节点和单元端点的两侧邻近点。均布荷载只布在相应正号或负号区段，集中荷载布在相应极值点，获得离散搜索包络。'),
        eq(r'S_{Q,+}=n\xi(q_k\Omega_++P_k\eta_{\max})'),eq(r'S_{Q,-}=n\xi(q_k\Omega_-+P_k\eta_{\min})'),
        p(f'Ω为同号影响线面积，η为对应极值纵标；负号区段的面积和纵标均保留负号。弯矩影响线纵标单位为m、面积单位为m²；剪力影响线纵标无量纲、面积单位为m。剪力式中的集中荷载改用{t["pk"]*t["shear_point_factor"]:g} kN。下列活载结果均未乘冲击系数。'),
        tab('表4-2 主跨跨中弯矩影响线数据',['参数','正号区段','负号区段'],[
            ['面积 / m²',fmt(mid['M']['positive_area'],4),fmt(mid['M']['negative_area'],4)],
            ['极值纵标 / m',fmt(mid['M']['eta_max'],4),fmt(mid['M']['eta_min'],4)],
            ['极值加载位置 / m',fmt(mid['M']['load_x_max'],3),fmt(mid['M']['load_x_min'],3)]]),
        eq(rf'M_{{Q,+}}={multiplier(mid,"M","max"):g}({t["qk"]:g}\times{mid["M"]["positive_area"]:.4f}+{t["pk"]:g}\times{mid["M"]["eta_max"]:.4f})'),
        eq(rf'M_{{Q,+}}={a["M_live_max"][mid["station_index"]]:.3f}\;\mathrm{{kN\cdot m}}'),
        p('以左主墩左侧剪力负包络为例：'),
        eq(rf'V_{{Q,-}}={multiplier(pier,"V","min"):g}[{t["qk"]:g}\times({pier["V"]["negative_area"]:.4f})+{t["pk"]*t["shear_point_factor"]:g}\times({pier["V"]["eta_min"]:.4f})]'),
        eq(rf'V_{{Q,-}}={a["V_live_min"][pier["station_index"]]:.3f}\;\mathrm{{kN}}'),
        h('4.5 活载内力汇总'),
        tab('表4-3 单幅汽车活载标准值（未计冲击）',['截面','x / m','M最小\nMN·m','M最大\nMN·m','V最小\nMN','V最大\nMN'],[
            [v['name'],fmt(v['x'],2),*[fmt(a[k][v['station_index']]/1000) for k in ['M_live_min','M_live_max','V_live_min','V_live_max']]] for v in traces])]),
    ('第5章 作用组合与支承反力',[
        h('5.1 组合表达式'),
        p('本章组合由已计算的一期恒载、二期恒载与汽车荷载组成。系数从规范配置读取。基本组合对两项恒载分别采用1.0或1.2的分项系数，枚举各组系数并取最大、最小效应；结构重要性系数按输入值取用。'),
        eq(r'S_d=\gamma_0[\gamma_{G1}S_{G1}+\gamma_{G2}S_{G2}+1.4(1+\mu)S_Q]'),
        eq(r'S_{\mathrm{std}}=S_{G1}+S_{G2}+(1+\mu)S_Q'),
        eq(r'S_{\mathrm{freq}}=S_{G1}+S_{G2}+0.7S_Q'),eq(r'S_{\mathrm{quasi}}=S_{G1}+S_{G2}+0.4S_Q'),
        p('标准组合计冲击，频遇与准永久组合不计冲击。各截面上下包络通常对应不同纵向车位、横向工况和恒载系数组合，不能作为同一次加载工况使用。'),
        tab('表5-1 规范组合配置',['组合编号','组合名称','恒载系数','汽车系数','计冲击','计重要性系数'],[
            [v['id'],v['name'],' / '.join(fmt(x,1) for x in v['gamma_g_options']),fmt(v['gamma_q']*v['vehicle_factor'],2),'是' if v['include_impact'] else '否','是' if v['apply_importance_factor'] else '否'] for v in r['combinations']]),
        h('5.2 组合代入示例'),*combination_example(r,mid,eq,p),h('5.3 单幅组合内力'),
        tab('表5-2 单幅基本组合包络',['截面','x / m','M最小\nMN·m','M最大\nMN·m','V最小\nMN','V最大\nMN'],[
            [v['name'],fmt(v['x'],2),*[fmt(a[k][v['station_index']]/1000) for k in ['M_uls_min','M_uls_max','V_uls_min','V_uls_max']]] for v in traces]),
        *[tab(f'表5-{i+3} {label}弯矩及剪力包络',['截面','M最小\nMN·m','M最大\nMN·m','V最小\nMN','V最大\nMN'],[
            [v['name'],*[fmt(a[f'{k}_{combo}_{bound}'][v['station_index']]/1000) for k,bound in [('M','min'),('M','max'),('V','min'),('V','max')]]] for v in traces])
          for i,(combo,label) in enumerate([('standard','标准组合'),('frequent','频遇组合'),('quasi','准永久组合')])],
        h('5.4 控制组合与车辆位置追溯'),
        tab('表5-6 控制截面最大弯矩来源',['截面','组合','恒载系数G1/G2','横向工况','集中荷载纵向位置 / m'],[
            [v['name'],v['governing']['M_max']['combination_id'],
             f'{v["governing"]["M_max"]["factors"]["gamma_g1"]:.1f} / {v["governing"]["M_max"]["factors"]["gamma_g2"]:.1f}',
             v['governing']['M_max']['transverse_case_name'],fmt(v['governing']['M_max']['point_load_x_m'],2)] for v in controls]),
        h('5.5 支承反力与恒载平衡'),
        p('支承反力向上为正。汽车反力按对应影响线独立求包络，集中荷载取432 kN；汽车列未计冲击，基本组合列已计冲击和分项系数。'),
        tab('表5-7 单幅恒载反力（kN）',['支点','一期恒载','二期恒载','合计'],[[n,*[fmt(rx[k][i],2) for k in ['dead1','dead2','dead']]] for i,n in enumerate(rx['names'])]),
        tab('表5-8 单幅汽车及基本组合反力（kN）',['支点','汽车最小','汽车最大','基本最小','基本最大'],[[n,*[fmt(rx[k][i],2) for k in ['live_min','live_max','uls_min','uls_max']]] for i,n in enumerate(rx['names'])]),
        eq(rf'G=G_1+G_2={r["loads"]["total_dead_weight_per_deck"]:.3f}\;\mathrm{{kN}}'),
        eq(rf'\sum_i R_{{G,i}}={sum(rx["dead"]):.3f}\;\mathrm{{kN}}'),
        p(f'恒载反力合计与施加重力之差的绝对值为{r["verification"]["force_balance_error_kn"]:.3e} kN。反力包络的各极值对应不同加载位置，不对其直接求和平衡。'),
        h('5.6 竖向位移作用效应'),
        p('位移与内力使用同一有限元模型和荷载工况。下表标准组合总位移已经叠加长期有效预应力产生的反拱，向上为正；活载挠度限值另见第9章。'),
        tab('表5-9 单幅标准组合总竖向位移',['截面','x / m','最小值 / mm','最大值 / mm'],[
            [v['name'],fmt(v['x'],2),fmt(a['deflection_standard_total_min'][v['station_index']]*1000,2),fmt(a['deflection_standard_total_max'][v['station_index']]*1000,2)] for v in traces]),
        image('内力包络','图5-1 单幅基本组合弯矩及剪力包络'),
        image('位移包络','图5-2 单幅标准组合竖向位移包络')])]
    ps=r['prestress'];loss=ps['loss_summary'];cs=r['construction_stages'];stage_rows=cs['stages']
    pages.extend([
    ('第6章 预应力钢束初估与作用效应',[
        h('6.1 钢绞线与张拉参数'),
        p('每幅主梁采用等效纵向钢束组表示全部纵向钢束。钢束根数按频遇组合、预应力度类别和腹板主拉应力条件初估，并形成平滑的整束数量包络；跨径布置对称时保持钢束包络对称。不同截面可有不同有效束数；该模型用于全桥作用效应和纵向整体验算，不替代实际分束、锚固齿块和局部构造设计。'),
        tab('表6-1 预应力材料及初估配束',['项目','计算采用值'],[
            ['钢绞线公称直径 / 单根面积',f'{ps["strand_diameter_mm"]:.1f} mm / {ps["strand_area_mm2"]:.1f} mm²'],
            ['抗拉强度标准值 / 弹性模量',f'{ps["strand_fpk_mpa"]:.0f} / {ps["strand_E_mpa"]:.0f} MPa'],
            ['张拉控制应力',f'{ps["jacking_stress_mpa"]:.2f} MPa'],
            ['每束根数 / 束数 / 总根数',f'{ps["strands_per_tendon"]} / {ps["tendon_count"]} / {ps["strand_count"]}'],
            ['总钢束面积 / 张拉力',f'{ps["total_area_mm2"]:.0f} mm² / {ps["jacking_force_kn"]:.2f} kN'],
            ['最大有效力需求',f'{ps["required_effective_force_max_kn"]:.2f} kN']]),
        h('6.2 钢束合力线与所需有效预应力'),
        p('偏心距以截面形心为基准，向下为正。正弯矩区钢束位于形心下方，负弯矩区位于形心上方；合力线经平滑后限制在输入的保护层范围内。'),
        *end_anchor_blocks(ps,p,eq,tab,fmt),
        eq(r'\sigma_t=\frac{P}{A}-\frac{Pe}{W_t}+\frac{M}{W_t},\quad \sigma_b=\frac{P}{A}+\frac{Pe}{W_b}-\frac{M}{W_b}'),
        eq(r'P_{e,\mathrm{req}}=1.05\frac{|M_{\mathrm{freq}}|-\sigma_{allow}W}{W/A+|e|}'),
        eq(rf'P_{{e,\mathrm{{req,max}}}}={ps["required_effective_force_max_kn"]:.3f}\;\mathrm{{kN}}'),
        h('6.3 摩阻、锚缩及长期损失'),
        p('按两端张拉计算摩阻损失；同一截面取由左端或右端张拉所得的较大剩余应力。锚具回缩、混凝土弹性压缩、收缩徐变和钢束松弛使用界面中的可编辑参数。'),
        eq(r'\sigma_{p,f}(x)=\sigma_{con}\exp[-(\mu\theta+kx)]'),
        eq(r'\Delta\sigma_{p,a}=E_p\frac{\Delta l}{L/2}'),
        eq(r'\sigma_{p,e}=\sigma_{p,f}-\Delta\sigma_{p,a}-\Delta\sigma_{p,es}-\Delta\sigma_{p,sh}-\Delta\sigma_{p,cr}-\Delta\sigma_{p,r}'),
        tab('表6-2 单幅预应力损失汇总',['损失项目','平均或采用值 / MPa'],[
            ['摩阻',fmt(loss['friction_mpa_mean'],2)],['锚缩',fmt(loss['anchorage_mpa_mean'],2)],
            ['弹性压缩',fmt(loss['elastic_shortening_mpa_mean'],2)],['收缩',fmt(loss['shrinkage_mpa'],2)],
            ['徐变',fmt(loss['creep_mpa'],2)],['松弛',fmt(loss['relaxation_mpa'],2)],
            ['总损失平均值',fmt(loss['total_mpa_mean'],2)]]),
        p(f'长期有效预应力范围为{ps["effective_force_min_kn"]:.2f}～{ps["effective_force_max_kn"]:.2f} kN，平均总损失率为{loss["total_ratio_mean"]*100:.2f}%。'),
        h('6.4 预应力主效应、次效应及成桥应力'),
        eq(r'M_p(x)=-P_e(x)e(x)'),
        eq(r'K u_p=F_p,\quad M_{p,tot}=M_{p,pri}+M_{p,sec}'),
        tab('表6-3 主要截面标准组合应力（压应力为正）',['截面','x / m','上缘最小 / MPa','上缘最大 / MPa','下缘最小 / MPa','下缘最大 / MPa'],[
            [v['name'],fmt(v['x'],2),fmt(v['stress_top_standard_min'],2),fmt(v['stress_top_standard_max'],2),fmt(v['stress_bottom_standard_min'],2),fmt(v['stress_bottom_standard_max'],2)] for v in r['controls'][:8]]),
        p('表中数值为毛截面弹性应力计算结果；使用阶段压应力和抗裂限值判定见第9章。'),
        image('钢束与损失','图6-1 单幅钢束合力线及预应力损失')]),
    ('第7章 对称悬臂施工阶段计算',[
        h('7.1 施工阶段模型'),
        p(f'采用简化对称悬臂根部截面法，分别建立P1与P2两个主墩的施工序列。标准节段长度取{cs["segment_length_m"]:.2f} m，每个悬臂端挂篮等效荷载取{cs["form_traveler_load_kn"]:.2f} kN；每个主墩计算{cs["segment_stage_count"]}个悬臂节段阶段，并增加合龙体系转换和成桥标准组合阶段。'),
        eq(r'M_{G,c}=-\int_0^l q(s)s\,\mathrm{d}s-P_{tr}l'),
        eq(r'M_{net}=M_{G,c}-P_e e'),
        eq(r'\delta_{tip}=\int_0^l\frac{M(s)m(s)}{E_cI(s)}\,\mathrm{d}s'),
        h('7.2 阶段作用效应'),
        tab('表7-1 双主墩悬臂施工阶段根部作用效应',['控制主墩','阶段','悬臂长 / m','已张拉束数','外荷载弯矩 / MN·m','净弯矩 / MN·m'],[
            [v['governing_pier_id'],v['stage_id'],fmt(v['active_length_each_side_m'],2),f'{v["activated_tendons"]}/{v["total_tendons"]}',fmt(v['external_root_moment_knm']/1000,3),fmt(v['net_root_moment_knm']/1000,3)] for v in stage_rows]),
        h('7.3 阶段截面应力'),
        tab('表7-2 双主墩根部截面阶段应力（压应力为正）',['控制主墩','阶段','体系','上缘 / MPa','下缘 / MPa'],[
            [v['governing_pier_id'],v['stage_id'],v['system'],fmt(v['top_stress_mpa'],2),fmt(v['bottom_stress_mpa'],2)] for v in stage_rows]),
        p(f'按绝对值控制的主墩和阶段为“{cs["governing_pier_id"]}－{cs["governing_stage_name"]}”，最大阶段应力绝对值为{cs["max_abs_stage_stress_mpa"]:.2f} MPa。施工阶段混凝土压应力限值判定见第9章。'),
        image('施工阶段','图7-1 墩顶根部净弯矩与阶段应力变化'),
        h('7.4 本版计算边界'),
        p('已计算内容为分项恒载、公路Ⅰ级汽车荷载、组合内力与位移、分区钢束初估、预应力损失、主次效应、按需求取整束的施工张拉进度、施工阶段根部内力及截面应力。纵向整体验算见后续章节。')])])
    sv=r['structural_verification'];checks=sv['checks'];rb=sv['reinforcement'];mat=sv['material']
    flex=checks['flexure'];shear=checks['shear'];crack=checks['crack_resistance']
    pages.extend([
    ('第8章 普通钢筋初配与承载能力验算',[
        h('8.1 材料设计值与普通钢筋初配'),
        tab('表8-1 承载力计算材料参数',['参数','采用值'],[
            ['混凝土轴心抗压强度设计值 fcd',f'{mat["fcd_mpa"]:.2f} MPa'],
            ['混凝土轴心抗拉强度设计值 ftd',f'{mat["ftd_mpa"]:.2f} MPa'],
            ['HRB400抗拉强度设计值 fsd',f'{rb["fsd_mpa"]:.0f} MPa'],
            ['1860级钢绞线抗拉强度设计值 fpd',f'{rb["fpd_mpa"]:.0f} MPa']]),
        p('纵向普通钢筋先按输入的单面毛截面配筋率计算并向上取偶数根，再逐两根增加，直至全桥正截面承载力满足且受压区高度不超限。该结果为沿全桥统一配置的初配面积。'),
        tab('表8-2 普通钢筋与箍筋初配',['部位','初配结果'],[
            ['上缘纵筋',f'{rb["top_bar_count"]}Φ{rb["bar_diameter_mm"]:.0f}，As={rb["top_area_mm2"]:.0f} mm²'],
            ['下缘纵筋',f'{rb["bottom_bar_count"]}Φ{rb["bar_diameter_mm"]:.0f}，As={rb["bottom_area_mm2"]:.0f} mm²'],
            ['双腹板箍筋',f'{shear["stirrup"]["total_legs"]}Φ{shear["stirrup"]["diameter_mm"]:.0f}@{shear["stirrup"]["spacing_mm"]:.0f} mm'],
            ['输入初始箍筋间距',f'{shear["stirrup"]["input_max_spacing_mm"]:.0f} mm']]),
        h('8.2 正截面抗弯承载力'),
        p('对实际带倒角箱形实体截面按水平等效矩形应力块积分求混凝土受压合力和合力点；预应力钢束按各截面有效束数计入，普通钢筋位于相应受拉缘。基本组合已经包含结构重要性系数。'),
        eq(r'f_{cd}A_c=f_{sd}A_s+f_{pd}A_p'),
        eq(r'M_u=f_{sd}A_s z_s+f_{pd}A_p z_p'),
        eq(r'\gamma_0 M_d\leq M_u,\quad x\leq\xi_b h_0'),
        tab('表8-3 正截面抗弯控制结果',['弯矩方向','需求 / MN·m','承载力 / MN·m','最大利用率','最大x/h0','判定'],[
            ['正弯矩',fmt(flex['positive']['demand_knm']/1000,3),fmt(flex['positive']['capacity_knm']/1000,3),fmt(flex['positive']['max_utilization'],3),fmt(flex['positive']['maximum_compression_depth_ratio'],3),flex['positive']['status']],
            ['负弯矩',fmt(flex['negative']['demand_knm']/1000,3),fmt(flex['negative']['capacity_knm']/1000,3),fmt(flex['negative']['max_utilization'],3),fmt(flex['negative']['maximum_compression_depth_ratio'],3),flex['negative']['status']]]),
        h('8.3 斜截面抗剪承载力'),
        eq(r'\max(\left|\gamma_0V_{d,min}-V_{pb}\right|,\left|\gamma_0V_{d,max}-V_{pb}\right|)\leq V_{cs}'),
        eq(r'V_{cs}=0.45\times10^{-3}\alpha_1\alpha_2\alpha_3bh_0\sqrt{(2+0.6P)\sqrt{f_{cu,k}}\rho_{sv}f_{sv}}'),
        p(f'计算采用α1={shear["coefficients"]["alpha1"]:.1f}、α2={shear["coefficients"]["alpha2"]:.1f}、α3={shear["coefficients"]["alpha3"]:.1f}。控制截面x={shear["critical_x_m"]:.3f} m，剪力需求为{shear["demand_kn"]:.2f} kN，承载力为{shear["capacity_kn"]:.2f} kN，最大利用率为{shear["max_utilization"]:.3f}，判定为{shear["status"]}。腹板截面尺寸上限验算利用率为{shear["web_dimension_max_utilization"]:.3f}，判定为{shear["web_dimension_status"]}。'),
        image('验算利用率','图8-1 正截面抗弯与斜截面抗剪利用率')]),
    ('第9章 正常使用、施工阶段限值与计算边界',[
        h('9.1 抗裂验算'),
        p(f'本方案按现浇预应力混凝土{c["prestress_class"]}类构件验算。频遇组合下正截面边缘最大拉应力为{crack["maximum_edge_tension_mpa"]:.3f} MPa，限值为{crack["edge_limit_mpa"]:.3f} MPa，判定为{crack["edge_status"]}。'),
        eq(r'\sigma_{st}-\sigma_{pc}\leq0' if c['prestress_class']=='full' else r'\sigma_{st}-\sigma_{pc}\leq0.5f_{tk}'),
        p(f'按毛截面形心处第一矩和双腹板实际总宽计算剪应力，再与有效预压应力组合求主拉应力。最大主拉应力为{crack["maximum_principal_tension_mpa"]:.3f} MPa，限值为{crack["principal_limit_mpa"]:.3f} MPa，控制位置x={crack["principal_critical_x_m"]:.3f} m，判定为{crack["principal_status"]}。'),
        eq(r'\sigma_{tp}=\sqrt{(\sigma_x/2)^2+\tau^2}-\sigma_x/2'),
        h('9.2 使用阶段与施工阶段混凝土压应力'),
        tab('表9-1 混凝土压应力验算',['项目','最大值 / MPa','限值 / MPa','判定'],[
            ['使用阶段标准组合',fmt(checks['concrete_stress']['maximum_compression_mpa'],3),fmt(checks['concrete_stress']['compression_limit_mpa'],3),checks['concrete_stress']['status']],
            ['施工阶段短暂状况',fmt(checks['temporary_concrete_stress']['maximum_compression_mpa'],3),fmt(checks['temporary_concrete_stress']['compression_limit_mpa'],3),checks['temporary_concrete_stress']['status']]]),
        eq(r'\sigma_{kc}+\sigma_{pt}\leq0.50f_{ck}'),
        eq(r'\sigma_{cc}\leq0.80f_{ck}'),
        h('9.3 活载挠度和长期反拱'),
        p('依据JTG 3362—2018第6.5.2～6.5.4条，活载挠度以不含冲击的频遇汽车荷载、长期增长系数及0.95EcI0刚度计算，再与各跨L/600比较。I0按最终等效钢筋位置、面积和材料模量计算换算形心及惯性矩，忽略单根钢筋自身局部惯性矩。长期总位移采用频遇组合并叠加长期反拱；反拱单独采用EcI0计算，长期系数取2.0。'),
        eq(r'B_0=0.95E_c I_0,\quad\eta_{\theta}\,0.7f_{Q,\mathrm{no\ impact}}\leq L/600'),
        eq(r'f_{lt}=\eta_{\theta}f_{\mathrm{frequent}}+2.0f_p'),
        tab('表9-2 各跨活载挠度验算',['跨号','最大活载挠度 / mm','限值 / mm','利用率','判定'],[
            [v['span'],fmt(v['maximum_frequent_long_term_mm'],3),fmt(v['limit_mm'],3),fmt(v['utilization'],3),v['status']] for v in checks['deflection']['span_checks']]),
        tab('表9-3 建议预拱度',['跨号','恒载长期下挠 / mm','预应力长期上拱 / mm','建议向上预拱 / mm'],[
            [v['span'],fmt(v['dead_long_term_downward_mm'],3),fmt(v['prestress_long_term_upward_mm'],3),fmt(v['recommended_upward_camber_mm'],3)] for v in checks['deflection']['recommended_camber']]),
        h('9.4 具名验算汇总'),
        tab('表9-4 纵向平面梁具名验算',['验算项目','判定'],[
            ['正截面抗弯',checks['flexure']['status']],['斜截面抗剪',checks['shear']['status']],
            ['抗裂',checks['crack_resistance']['status']],['使用阶段混凝土压应力',checks['concrete_stress']['status']],
            ['活载挠度',checks['deflection']['status']],['施工阶段混凝土压应力',checks['temporary_concrete_stress']['status']]]),
        p(f'本次共完成{sv["summary"]["total"]}项具名验算，其中{sv["summary"]["passed"]}项判定为PASS。该汇总只覆盖表列项目。'),
        h('9.5 课程设计范围说明'),
        *[p('• '+text) for text in sv['out_of_course_scope']],
        p(f'以上项目标记为OUT_OF_COURSE_SCOPE，不给出虚构数值，也不影响本次任务书范围的完成判定。本次课程设计状态为{r["status_code"]}。')])])
    pages.append(('第10章 计算追溯与参数敏感性',[ 
        h('10.1 计算追溯方法'),
        p('程序将主要结果的输入、公式、中间值、结果、单位、来源和JSON定位同时保存。计算书列出关键索引，完整记录见成果目录中的计算追溯表CSV和设计结果JSON；计算数据CSV保存沿桥离散结果。'),
        tab('表10-1 主要计算记录追溯索引',['记录号','章节','名称','结果','单位'],[
            [v['id'],v['chapter'],v['name'],str(v['result']),v['unit']]
            for v in r['calculation_trace'] if v['id'] in {
                'G1','G2','FREQ','IMPACT','P_REQUIRED','P_LOSS','ULS_FLEXURE',
                'ULS_SHEAR','SLS_CRACK','SLS_CONCRETE_STRESS','SLS_DEFLECTION',
                'TEMP_CONCRETE_STRESS'}]),
        h('10.2 荷载参数敏感性'),
        p('保持结构尺寸、材料、组合系数和最不利布载算法不变，分别将恒载或汽车荷载提高5%，重新形成基本组合弯矩和剪力包络。该结果用于识别输入敏感程度，不替代重新选定参数后的正式验算。'),
        tab('表10-2 基本组合敏感性复算',['工况','恒载倍率','汽车倍率','最大绝对弯矩 / MN·m','变化','最大绝对剪力 / MN','变化'],[
            [v['name'],fmt(v['permanent_factor'],2),fmt(v['traffic_factor'],2),
             fmt(v['M_abs_max']/1000,3),f'{v["moment_change_ratio"]*100:.2f}%',
             fmt(v['V_abs_max']/1000,3),f'{v["shear_change_ratio"]*100:.2f}%']
            for v in r['sensitivity']]),
        h('10.3 结论'),
        p(f'当前跨径布置为{span} m，边跨模式为{c["side_span_mode"]}。课程范围内具名验算通过{sv["summary"]["passed"]}/{sv["summary"]["total"]}项，状态为{r["status_code"]}。')]))
    cc=r.get('crosscheck')
    if cc:
        counts=cc['counts']
        pages.append(('第11章 独立交叉验证',[
            h('11.1 方法与输入边界'),
            p('主程序采用位移法有限元；独立程序在单独进程中释放两处内支点，以力法协调方程、虚功积分和柔度特征值计算。截面独立重建并用水平条带积分；仅接收输入参数和最终钢束、钢筋方案，不读取主程序截面性质、荷载效应或应力结果。'),
            h('11.2 本次复核结果'),
            p(cc['message']),
            tab('表11-1 独立复核状态',['项目','本次结果'],[
                ['执行',cc['execution_status']],['数值对照',cc['numerical_status']],['规范规则',cc['rule_status']],
                ['固定方案验算',cc['design_status']],['覆盖范围',cc['coverage_status']],
                ['逐项对照',f"PASS {counts['PASS']} / WARN {counts['WARN']} / FAIL {counts['FAIL']} / ERROR {counts['ERROR']}"]]),
            p('复核编号：'+cc['provenance']['run_id']),
            p('输入SHA-256：'+cc['provenance']['input_hash']),
            p('详细双值、控制位置、容差和收敛记录见成果目录中的交叉复核报告HTML与JSON。PARTIAL表示简化损失、静定悬臂或范围外内容未完成全面验证；不等同于整桥工程复核通过。'),
            *[p(v['id']+'：'+v['status']+'；'+v['message']) for v in cc.get('rules',[]) if v['status']!='PASS']]))
    return pages


def end_anchor_blocks(prestress,p,eq,tab,fmt):
    rule=prestress.get('end_anchor_rule')
    if not rule:return []
    automatic=rule['mode']=='auto_kern'
    return [
        p(('桥台端钢束合力线按实际毛截面核心范围自动初选，同时满足钢束保护距离。' if automatic else '本次桥台端钢束偏心采用用户明确输入，保留该值参与实际应力验算。')+'端部初选依据线弹性偏心压力应力公式，不改变规范应力限值；实际锚固区局部验算属于课程范围之外。'),
        eq(r'-\frac{W_b}{A}\leq e_{end}\leq\frac{W_t}{A}'),
        tab('桥台端钢束合力线与截面核心（单幅）',['端部位置 / m','核心下界 / m','核心上界 / m','采用偏心 / m'],[
            [fmt(x,2),fmt(lo,4),fmt(hi,4),fmt(e,4)]
            for x,lo,hi,e in zip(rule['x_m'],rule['kern_lower_m'],rule['kern_upper_m'],rule['eccentricity_m'])]),
        p('正常使用与施工应力按实际完整作用效应计算，未通过的结果仍如实列示。')]

def combination_example(r,v,eq,p):
    a=r['analysis'];j=v['station_index'];g1=a['M_dead1'][j];g2=a['M_dead2'][j];q=a['M_live_max'][j]
    f1=1.2 if g1>=0 else 1.;f2=1.2 if g2>=0 else 1.;mu=r['loads']['traffic']['impact'];imp=r['input']['importance_factor']
    return [p('以主跨跨中最大弯矩基本组合为例，先列各作用的单独效应（kN·m）：'),
        eq(rf'M_{{G1}}={g1:.3f},\quad M_{{G2}}={g2:.3f},\quad M_{{Q,+}}={q:.3f}'),
        eq(rf'M_{{Gd}}={imp:g}[{f1:g}\times({g1:.3f})+{f2:g}\times({g2:.3f})]={imp*(f1*g1+f2*g2):.3f}'),
        eq(rf'M_{{d,+}}={imp*(f1*g1+f2*g2):.3f}+{imp:g}\times1.4\times{1+mu:.4f}\times{q:.3f}={a["M_uls_max"][j]:.3f}'),
        p('计算保留内部完整精度；显示数值取小数，逐项代入时可能存在末位舍入差。')]

def set_fonts(run):
    run.font.name='Times New Roman';run.font.color.rgb=RGBColor(0,0,0)
    fonts=run._r.get_or_add_rPr().get_or_add_rFonts()
    for attr in list(fonts.attrib):del fonts.attrib[attr]
    for key,val in [('ascii','Times New Roman'),('hAnsi','Times New Roman'),('cs','Times New Roman'),('eastAsia','宋体')]:fonts.set(qn('w:'+key),val)

def table_widths(n):return [5.2,9.45] if n==2 else [3.7]+[(14.65-3.7)/(n-1)]*(n-1)


def _clear_story(story):
    story.is_linked_to_previous=False
    root=story._element
    for node in list(root):root.remove(node)
    root.append(OxmlElement('w:p'))


def _configure_page_numbers(doc):
    """A separate cover section; one PAGE field for the numbered body."""
    doc.settings.odd_and_even_pages_header_footer=False
    for section in doc.sections:
        section.different_first_page_header_footer=False
        for story in [section.header,section.first_page_header,section.even_page_header,
                      section.footer,section.first_page_footer,section.even_page_footer]:
            _clear_story(story)
    body=doc.sections[1]
    number=body._sectPr.find(qn('w:pgNumType'))
    if number is None:number=OxmlElement('w:pgNumType');body._sectPr.append(number)
    number.set(qn('w:start'),'1');number.set(qn('w:fmt'),'decimal')
    footer=body.footer.paragraphs[0]
    footer.alignment=1;footer.paragraph_format.first_line_indent=Pt(0)
    footer.paragraph_format.space_before=Pt(0);footer.paragraph_format.space_after=Pt(0)
    footer.paragraph_format.line_spacing=1
    # A dirty complex field lets Word/WPS refresh actual page values on open/print.
    for tag,value in [('begin',None),('instruction',' PAGE '),('separate',None),('text','1'),('end',None)]:
        run=footer.add_run();run.font.size=Pt(10.5)
        if tag=='instruction':
            node=OxmlElement('w:instrText');node.set(qn('xml:space'),'preserve');node.text=value
        elif tag=='text':
            node=OxmlElement('w:t');node.text=value
        else:
            node=OxmlElement('w:fldChar');node.set(qn('w:fldCharType'),tag)
            if tag=='begin':node.set(qn('w:dirty'),'true')
        run._r.append(node)
    update=doc.settings.element.find(qn('w:updateFields'))
    if update is None:update=OxmlElement('w:updateFields');doc.settings.element.append(update)
    update.set(qn('w:val'),'true')


def _bookmark(paragraph,index):
    start=OxmlElement('w:bookmarkStart');start.set(qn('w:id'),str(index));start.set(qn('w:name'),f'chapter_{index:02d}')
    end=OxmlElement('w:bookmarkEnd');end.set(qn('w:id'),str(index))
    paragraph._p.insert(1 if paragraph._p.pPr is not None else 0,start);paragraph._p.append(end)

def write_docx(pages,path):
    doc=Document(Path(__file__).parent/'assets/course_template.docx')
    for name,size in [('Normal',12),('一级标题',15),('二级标题',14),('三级标题',12),('图表题',10.5)]:
        st=doc.styles[name];st.font.size=Pt(size);st.font.bold=name.endswith('标题')
        pf=st.paragraph_format;pf.first_line_indent=Pt(24 if name=='Normal' else 0)
        pf.space_before=Pt(6 if name=='Normal' else 12);pf.space_after=Pt(6)
        pf.line_spacing=1.25;pf.keep_with_next=name!='Normal';pf.page_break_before=False
        for x in st.element.xpath('.//w:ind'):
            for att in ['firstLineChars','leftChars','rightChars']:x.attrib.pop(qn('w:'+att),None)
    formulas=[];equation_dir=path.parent/'图表/公式';equation_dir.mkdir(parents=True,exist_ok=True)
    for chapter,(title,blocks) in enumerate(pages):
        if chapter==1:doc.add_section(WD_SECTION_START.NEW_PAGE)
        if chapter:_bookmark(doc.add_paragraph(title,'一级标题'),chapter)
        eqno=0
        for bi,b in enumerate(blocks):
            typ=b[0]
            if chapter==0:
                p=doc.add_paragraph(b[1]);p.alignment=1;p.paragraph_format.first_line_indent=Pt(0)
                p.paragraph_format.space_before=Pt(36 if bi==0 else 16 if bi<3 else 8);p.paragraph_format.space_after=Pt(24 if bi==2 else 10 if bi<3 else 4)
                for run in p.runs:run.font.size=Pt(22 if bi==2 else 18 if bi<3 else 12);run.bold=bi<3
            elif typ=='h2':doc.add_paragraph(b[1],'二级标题')
            elif typ=='p':doc.add_paragraph(b[1])
            elif typ=='equation':
                eqno+=1;idx=len(formulas)+1;p=doc.add_paragraph();p.alignment=1;p.paragraph_format.first_line_indent=Pt(0)
                file=equation_dir/f'公式_{idx:03}.png';w,h=add_equation(p,b[1],file,idx)
                p.add_run(f'  （{chapter}-{eqno}）').font.size=Pt(10.5)
                formulas.append(dict(id=idx,number=f'{chapter}-{eqno}',source=b[1],preview=file.name,width_pt=w,height_pt=h))
            elif typ=='image':
                p=doc.add_paragraph();p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.keep_with_next=True
                p.add_run().add_picture(b[1],width=Cm(14.5));doc.add_paragraph(b[2],'图表题')
            elif typ=='table':
                doc.add_paragraph(b[1],'图表题');n=len(b[2]);widths=table_widths(n);table=doc.add_table(rows=1,cols=n);table.autofit=False
                for col,w in zip(table.columns,widths):col.width=Cm(w)
                for cells,row in [(table.rows[0].cells,b[2])]+[(table.add_row().cells,row) for row in b[3]]:
                    for cell,text in zip(cells,row):cell.text=text
                for ri,row in enumerate(table.rows):
                    pr=row._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
                    if ri==0:pr.append(OxmlElement('w:tblHeader'))
                    for ci,cell in enumerate(row.cells):
                        cell.width=Cm(widths[ci]);cell.vertical_alignment=1;borders=OxmlElement('w:tcBorders')
                        for edge in ['top','left','bottom','right']:
                            el=OxmlElement('w:'+edge)
                            for k,v in [('val','single'),('sz','4'),('color','D9D9D9')]:el.set(qn('w:'+k),v)
                            borders.append(el)
                        cell._tc.get_or_add_tcPr().append(borders)
                        if ri==0:
                            sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'EEEEEE');cell._tc.get_or_add_tcPr().append(sh)
                        for p in cell.paragraphs:
                            p.alignment=0 if ci==0 else 1;p.paragraph_format.first_line_indent=Pt(0)
                            p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(4);p.paragraph_format.line_spacing=1.05
                            for run in p.runs:run.font.size=Pt(10.5);run.bold=ri==0
                doc.add_paragraph().paragraph_format.space_after=Pt(0)
    _configure_page_numbers(doc)
    stories=[story._element for section in doc.sections for story in [section.header,section.first_page_header,section.even_page_header,section.footer,section.first_page_footer,section.even_page_footer]]
    for root in [doc.element,*stories]:
        for rr in root.xpath('.//w:r'):
            from docx.text.run import Run
            set_fonts(Run(rr,None))
    for fonts in doc.styles.element.xpath('.//w:rFonts'):
        for att in list(fonts.attrib):del fonts.attrib[att]
        for k,v in [('ascii','Times New Roman'),('hAnsi','Times New Roman'),('cs','Times New Roman'),('eastAsia','宋体')]:fonts.set(qn('w:'+k),v)
    doc.core_properties.title='桥梁工程课程设计纵向整体验算计算书';doc.core_properties.author='BridgeGenerator V0.12';doc.save(path)
    (equation_dir/'公式清单.json').write_text(json.dumps(formulas,ensure_ascii=False,indent=2),encoding='utf-8')
    return formulas

def write_pdf(pages,path,formulas):
    pdfmetrics.registerFont(TTFont('BookCN','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
    pdfmetrics.registerFont(TTFont('BookEN','C:/Windows/Fonts/times.ttf'))
    body=ParagraphStyle('Body',fontName='BookEN',fontSize=12,leading=18,firstLineIndent=24,spaceAfter=6,spaceBefore=6)
    heading=ParagraphStyle('Chapter',parent=body,fontSize=15,leading=21,firstLineIndent=0,spaceAfter=12)
    section=ParagraphStyle('Section',parent=body,fontSize=14,leading=20,firstLineIndent=0,spaceBefore=12,keepWithNext=True)
    caption=ParagraphStyle('Caption',parent=body,fontSize=10.5,leading=14,firstLineIndent=0,alignment=1,spaceBefore=5,spaceAfter=5)
    small=ParagraphStyle('Cell',fontName='BookEN',fontSize=10.5,leading=13,alignment=1)
    def esc(text):
        parts=[]
        for chunk in re.findall(r'[\u2e80-\uffff]+|[^\u2e80-\uffff]+',str(text)):
            font='BookCN' if '\u2e80'<=chunk[0]<='\uffff' else 'BookEN'
            chunk=chunk.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>')
            parts.append(f'<font name="{font}">{chunk}</font>')
        return ''.join(parts)
    class BookDocument(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            if isinstance(flowable,Paragraph) and getattr(flowable,'chapter_index',None):
                key=f'chapter_{flowable.chapter_index:02d}'
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(flowable.getPlainText(),key,level=0,closed=False)
    flow=[];index=0
    for chapter,(title,blocks) in enumerate(pages):
        if chapter==1:flow.append(PageBreak())
        if chapter:
            heading.keepWithNext=True
            title_paragraph=Paragraph(esc(title),heading);title_paragraph.chapter_index=chapter
            flow.append(title_paragraph)
        for bi,b in enumerate(blocks):
            if chapter==0:
                style=ParagraphStyle('Cover',parent=body,firstLineIndent=0,alignment=1,fontSize=22 if bi==2 else 18 if bi<3 else 12,leading=30 if bi<3 else 18,spaceBefore=36 if bi==0 else 16 if bi<3 else 8,spaceAfter=24 if bi==2 else 10 if bi<3 else 4)
                flow.append(Paragraph(esc(b[1]),style));continue
            if b[0]=='p':flow.append(Paragraph(esc(b[1]),body))
            elif b[0]=='h2':flow.append(Paragraph(esc(b[1]),section))
            elif b[0]=='equation':
                f=formulas[index];index+=1;im=Image(str(path.parent/'图表/公式'/f['preview']),width=f['width_pt'],height=f['height_pt'])
                tb=Table([[im,Paragraph(esc('（'+f['number']+'）'),caption)]],colWidths=[126*mm,20.5*mm])
                tb.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));flow.append(tb)
            elif b[0]=='image':flow.append(KeepTogether([Image(b[1],width=145*mm,height=88.26*mm),Paragraph(esc(b[2]),caption)]))
            elif b[0]=='table':
                n=len(b[2]);rows=[[Paragraph(esc(v),small) for v in row] for row in [b[2]]+b[3]]
                tb=Table(rows,colWidths=[w*10*mm for w in table_widths(n)],repeatRows=1)
                tb.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#D9D9D9')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEEEEE')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                cap=Paragraph(esc(b[1]),caption);cap.keepWithNext=True;flow.extend([cap,tb,Spacer(1,6)])
    def footer(cv,doc):
        if doc.page==1:cv.addPageLabel(0,prefix='封面')
        if doc.page==2:cv.addPageLabel(1,style='D',start=1)
        if doc.page>1:cv.setFont('BookEN',10.5);cv.drawCentredString(105*mm,17.5*mm,str(doc.page-1))
    BookDocument(str(path),pagesize=(210*mm,297*mm),leftMargin=31.75*mm,rightMargin=31.75*mm,topMargin=25.4*mm,bottomMargin=25.4*mm,title='桥梁工程课程设计纵向整体验算计算书').build(flow,onFirstPage=footer,onLaterPages=footer)

def export_report(r,out,figs):
    pages=book_pages(r,figs);formulas=write_docx(pages,out/'01_桥梁工程课程设计计算书.docx')
    write_pdf(pages,out/'02_桥梁工程课程设计计算书.pdf',formulas)
