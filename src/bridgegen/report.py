from pathlib import Path
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.units import mm
from .drawings import font_name


def plots(r,out):
    out.mkdir(exist_ok=True)
    font=Path('C:/Windows/Fonts/simsun.ttc')
    if font.exists():font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=['Times New Roman','SimSun']
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    a=r['analysis'];x=np.asarray(a['x']);files={}
    fig,axs=plt.subplots(2,1,figsize=(9.2,5.6),layout='constrained')
    for ax,kind,unit in zip(axs,['M','V'],['MN·m','MN']):
        lo=np.asarray(a[kind+'_uls_min'])/1000;hi=np.asarray(a[kind+'_uls_max'])/1000
        ax.fill_between(x,lo,hi,color='#dce9ef');ax.plot(x,hi,label='基本组合最大值',color='#226b89')
        ax.plot(x,lo,label='基本组合最小值',color='#bb713c')
        ax.plot(x,np.asarray(a[kind+'_dead'])/1000,label='恒载标准值',color='#374957',ls='--')
        ax.set_ylabel(('弯矩' if kind=='M' else '剪力')+' ('+unit+')')
        ax.set_xlabel('距左桥台支承轴线 x (m)');ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
        for support in r['geometry']['supports']:ax.axvline(support,color='#aab7bf',ls=':',lw=.8)
    axs[0].invert_yaxis()
    target=out/'内力包络.png';fig.savefig(target,dpi=170,facecolor='white');plt.close(fig);files['内力包络']=target
    fig,ax=plt.subplots(1,1,figsize=(9.2,3.6),layout='constrained')
    lo=np.asarray(a['deflection_standard_total_min'])*1000;hi=np.asarray(a['deflection_standard_total_max'])*1000
    ax.fill_between(x,lo,hi,color='#e6edf0')
    ax.plot(x,hi,label='标准组合最大值',color='#226b89')
    ax.plot(x,lo,label='标准组合最小值',color='#bb713c')
    ax.plot(x,np.asarray(a['deflection_prestress'])*1000,label='预应力反拱',color='#57945b',ls='--')
    ax.set_ylabel('竖向位移 (mm)');ax.set_xlabel('距左桥台支承轴线 x (m)')
    ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    for support in r['geometry']['supports']:ax.axvline(support,color='#aab7bf',ls=':',lw=.8)
    target=out/'位移包络.png';fig.savefig(target,dpi=170,facecolor='white');plt.close(fig);files['位移包络']=target
    p=r['prestress'];profile=p['profile']
    px=np.asarray(profile['x'])
    fig,axs=plt.subplots(2,1,figsize=(9.2,5.6),layout='constrained')
    axs[0].plot(px,np.asarray(profile['depth_from_top']),color='#226b89',label='钢束合力线距顶面')
    axs[0].plot(px,np.asarray(r['geometry']['height_mid'])+np.zeros_like(px),alpha=0)
    axs[0].invert_yaxis();axs[0].set_ylabel('距顶面深度 (m)');axs[0].legend(fontsize=8)
    axs[1].plot(px,np.asarray(profile['sigma_jack']),label='张拉控制应力',color='#374957',ls='--')
    axs[1].plot(px,np.asarray(profile['sigma_after_friction']),label='摩阻后',color='#bb713c')
    axs[1].plot(px,np.asarray(profile['sigma_effective']),label='长期有效',color='#226b89')
    axs[1].set_ylabel('钢束应力 (MPa)');axs[1].set_xlabel('距左桥台支承轴线 x (m)');axs[1].legend(fontsize=8)
    for ax in axs:
        ax.grid(axis='y',alpha=.2)
        for support in r['geometry']['supports']:ax.axvline(support,color='#aab7bf',ls=':',lw=.8)
    target=out/'钢束与损失.png';fig.savefig(target,dpi=170,facecolor='white');plt.close(fig);files['钢束与损失']=target
    construction=r['construction_stages'];stages=construction['stages'];labels=[v['stage_id'] for v in stages]
    fig,axs=plt.subplots(2,1,figsize=(9.2,5.6),layout='constrained')
    colors=['#226b89','#bb713c']
    for j,pier in enumerate(construction['piers']):
        rows=pier['stages'];labs=[v['stage_id'] for v in rows]
        moments=np.asarray([v['net_root_moment_knm']/1000 for v in rows])
        top=np.asarray([v['top_stress_mpa'] for v in rows]);bottom=np.asarray([v['bottom_stress_mpa'] for v in rows])
        axs[0].plot(labs,moments,marker='o',color=colors[j],label=pier['pier_id'])
        axs[1].plot(labs,top,marker='o',label=f'{pier["pier_id"]}上缘',color=colors[j])
        axs[1].plot(labs,bottom,marker='o',label=f'{pier["pier_id"]}下缘',color=colors[j],ls='--')
    axs[0].set_ylabel('墩顶净弯矩 (MN·m)');axs[0].legend(fontsize=8)
    axs[1].set_ylabel('截面应力 (MPa)');axs[1].set_xlabel('施工阶段');axs[1].legend(fontsize=8)
    for ax in axs:ax.grid(axis='y',alpha=.2);ax.tick_params(axis='x',rotation=35)
    target=out/'施工阶段.png';fig.savefig(target,dpi=170,facecolor='white');plt.close(fig);files['施工阶段']=target
    fig,ax=plt.subplots(1,1,figsize=(9.2,3.8),layout='constrained')
    ax.plot(x,np.asarray(a['flexural_utilization_positive']),label='正弯矩抗弯',color='#226b89')
    ax.plot(x,np.asarray(a['flexural_utilization_negative']),label='负弯矩抗弯',color='#bb713c')
    ax.plot(x,np.asarray(a['shear_utilization']),label='抗剪',color='#57945b')
    ax.axhline(1.0,color='#a13623',ls='--',label='限值 1.0')
    ax.set_ylabel('验算利用率');ax.set_xlabel('距左桥台支承轴线 x (m)')
    ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8,ncol=4)
    for support in r['geometry']['supports']:ax.axvline(support,color='#aab7bf',ls=':',lw=.8)
    target=out/'验算利用率.png';fig.savefig(target,dpi=170,facecolor='white');plt.close(fig);files['验算利用率']=target
    return files


from .course_book import book_pages,write_docx,write_pdf,export_report
