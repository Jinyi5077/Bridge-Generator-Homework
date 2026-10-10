"""Engineering CAD sheets with real mm dimensions and 1:1 paper layouts."""
from pathlib import Path
import json, math
import numpy as np
import ezdxf
from ezdxf.enums import TextEntityAlignment
from copy import copy

CN_FONT='simfang.ttf'
NUM_FONT='isocpeur.ttf'
LAYERS={
    'B-CUT':(50,'CONTINUOUS'), 'B-OUTLINE':(25,'CONTINUOUS'),
    'B-DETAIL':(13,'CONTINUOUS'), 'B-CENTER':(13,'B-CENTER'),
    'B-HIDDEN':(13,'B-HIDDEN'), 'B-PIER':(25,'CONTINUOUS'),
    'B-HATCH':(13,'CONTINUOUS'), 'B-PRESTRESS':(25,'CONTINUOUS'),
    'B-REBAR':(25,'CONTINUOUS'),
    'B-DIM':(13,'CONTINUOUS'), 'B-TEXT':(13,'CONTINUOUS'),
    'P-FRAME':(50,'CONTINUOUS'), 'P-GRID':(13,'CONTINUOUS'),
    'P-TEXT':(13,'CONTINUOUS'), 'P-VPORT':(13,'CONTINUOUS'),
}
REFERENCES=[
    dict(title='湖南省高速公路建设项目文件材料编制与归档指南（2025）',
         pages='印刷页85-86、191；PDF第93-94、199页',
         url='https://jtt.hunan.gov.cn/xxgk/zwgg/202505/33685439/files/94061363918a46b69b6afa2753541a66.pdf',
         use='GB50162引用、仿宋宽度0.7、字高、尺寸、装订边和图框'),
    dict(title='温岭市大溪镇泵与电机孵化园区基础设施配套项目-规划四路施工图（2024.01）',
         pages='PDF第91、131页',
         url='https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web2760/site/attach/-1/2403041117378428943.pdf',
         use='参考尺寸链、断面题名、右下角图标和说明的组织方式；未照搬结构或签章'),
]


def render_cad_pdf(dxf_path,pdf_path):
    """Render the actual CAD paper layout, including model viewport and glyphs."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import FigureCanvasPdf  # explicit frozen-app dependency
    from ezdxf.addons.drawing import Frontend,RenderContext
    from ezdxf.addons.drawing.config import Configuration,ColorPolicy,BackgroundPolicy
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend,to_matplotlib_path
    from matplotlib.patches import PathPatch
    class EngineeringBackend(MatplotlibBackend):
        def draw_filled_paths(self,paths,properties):
            # TrueType contours already have the correct winding. Bounding-box
            # based reorientation fills counters in Chinese glyphs such as 图/四.
            self.ax.add_patch(PathPatch(to_matplotlib_path(paths,detect_holes=False),
                facecolor=properties.color,linewidth=0,fill=True,zorder=self._get_z()))
    d=ezdxf.readfile(dxf_path); layout=next(l for l in d.layouts if l.name!='Model')
    # ezdxf clips into paper coordinates before its linetype stage but then
    # applies inverse viewport scaling. Compensate in the rendering copy only.
    # The saved CAD retains scaled model patterns and PSLTSCALE=0.
    vp_scale=min(v.get_scale() for v in layout.query('VIEWPORT') if v.dxf.id>1)
    for name,pattern in [('B-CENTER',[16,10,-2,0,-4]),('B-HIDDEN',[6,3,-3])]:
        if name in d.linetypes:d.linetypes.get(name).setup_pattern([v*vp_scale for v in pattern])
    W,H=float(layout.dxf.paper_width),float(layout.dxf.paper_height)
    fig=plt.figure(figsize=(W/25.4,H/25.4),dpi=150);ax=fig.add_axes([0,0,1,1])
    cfg=Configuration(color_policy=ColorPolicy.BLACK,background_policy=BackgroundPolicy.WHITE,
                      lineweight_scaling=72/25.4,min_lineweight=.01,min_dash_length=.1*vp_scale)
    Frontend(RenderContext(d),EngineeringBackend(ax,adjust_figure=False),config=cfg).draw_layout(layout,finalize=True)
    ax.set_xlim(0,W);ax.set_ylim(0,H);ax.set_aspect('equal');ax.set_axis_off()
    fig.savefig(pdf_path,format='pdf',facecolor='white',dpi=200);plt.close(fig)


class Sheet:
    def __init__(self,title,scale,number,size=(420,297)):
        self.title,self.scale,self.number=title,float(scale),number
        self.W,self.H=size;self.expected=[];self.origin=(0.,0.);self.views={}
        self.d=ezdxf.new('R2018');self.d.units=4
        for key,value in {'$MEASUREMENT':1,'$INSUNITS':4,'$LUNITS':2,'$LUPREC':0,
                          '$LWDISPLAY':True,'$LTSCALE':1.,'$PSLTSCALE':0}.items():self.d.header[key]=value
        for name,pattern in [('B-CENTER',[16,10,-2,0,-4]),('B-HIDDEN',[6,3,-3])]:
            self.d.linetypes.new(name,dxfattribs={'description':name+' paper mm','pattern':[v*self.scale for v in pattern]})
        for name,(weight,ltype) in LAYERS.items():
            self.d.layers.new(name,dxfattribs={'color':7,'lineweight':weight,'linetype':ltype,'plot':0 if name=='P-VPORT' else 1})
        for name,font,width,family in [('CN_FS',CN_FONT,.7,'FangSong'),('ISO_NUM',NUM_FONT,1.,'ISOCPEUR')]:
            st=self.d.styles.new(name,dxfattribs={'font':font,'width':width,'height':0})
            st.set_extended_font_data(family=family,italic=False,bold=False)
        self.m=self.d.modelspace();self.d.layouts.rename('Layout1','出图');self.p=self.d.layouts.get('出图')
        self.p.page_setup(size=size,margins=(0,0,0,0),units='mm',scale=(1,1),device='DWG To PDF.pc3')
        self.p.set_plot_flags(128,True);self.p.set_plot_flags(64,False);self.p.set_plot_flags(32,False)
        self.p.dxf.current_style_sheet=''
        self.dimstyle='CN_MM_'+str(int(scale))
        self.d.dimstyles.new(self.dimstyle,dxfattribs={
            'dimscale':self.scale,'dimtxt':2.5,'dimasz':2.,'dimexo':2.,'dimexe':2.,'dimgap':.625,
            'dimdli':7.5,'dimdec':0,'dimtad':1,'dimtih':0,'dimtoh':0,'dimtmove':1,'dimjust':0,
            'dimzin':8,'dimlfac':1.,'dimclrd':0,'dimclre':0,'dimclrt':0,'dimlwd':13,'dimlwe':13,'dimtxsty':'ISO_NUM'})

    def pt(self,p,paper=False):
        return tuple(float(v) if paper else float(v)*self.scale+self.origin[i] for i,v in enumerate(p))
    def line(self,a,b,layer='B-OUTLINE',paper=False):
        return (self.p if paper else self.m).add_line(self.pt(a,paper),self.pt(b,paper),dxfattribs={'layer':layer})
    def poly(self,points,closed=False,layer='B-OUTLINE',paper=False):
        return (self.p if paper else self.m).add_lwpolyline([self.pt(v,paper) for v in points],close=closed,dxfattribs={'layer':layer})
    def rect(self,x,y,w,h,layer='B-OUTLINE',paper=False):
        return self.poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],True,layer,paper)
    def circle(self,center,radius,layer='B-DETAIL',paper=False):
        return (self.p if paper else self.m).add_circle(
            self.pt(center,paper),radius*(1 if paper else self.scale),dxfattribs={'layer':layer})
    def text(self,x,y,value,height=3.5,align='left',paper=False,numeric=False,rotation=0):
        t=(self.p if paper else self.m).add_text(str(value),dxfattribs={
            'height':height*(1 if paper else self.scale),'style':'ISO_NUM' if numeric else 'CN_FS',
            'width':1. if numeric else .7,'rotation':rotation,'layer':'P-TEXT' if paper else 'B-TEXT'})
        t.set_placement(self.pt((x,y),paper),align={'left':TextEntityAlignment.LEFT,'center':TextEntityAlignment.MIDDLE_CENTER,'right':TextEntityAlignment.RIGHT}[align])
        return t
    def dim(self,a,b,offset,vertical=False,text_rise=None):
        # Mirroring must not reverse the dimension direction and move text
        # below the chain. Preserve the measured endpoints in increasing order.
        a,b=sorted((a,b),key=lambda p:p[1] if vertical else p[0])
        base=(offset,a[1]) if vertical else (a[0],offset)
        dim=self.m.add_linear_dim(base=self.pt(base),p1=self.pt(a),p2=self.pt(b),angle=90 if vertical else 0,
                                 dimstyle=self.dimstyle,dxfattribs={'layer':'B-DIM'})
        if text_rise is not None and not vertical:
            # Retain a measured DIMENSION and only stagger crowded chain labels.
            dim.set_location(self.pt(((a[0]+b[0])/2,offset+text_rise)),leader=True)
        dim.render();self.expected.append(float(abs(a[1]-b[1] if vertical else a[0]-b[0])*self.scale))
    def hatch(self,outer,holes):
        h=self.m.add_hatch(color=256,dxfattribs={'layer':'B-HATCH'})
        h.set_pattern_fill('ANSI31',scale=1.6*self.scale,color=256,style=0)
        h.paths.add_polyline_path([self.pt(p) for p in outer],is_closed=True,flags=1)
        for ring in holes:h.paths.add_polyline_path([self.pt(p) for p in ring],is_closed=True,flags=0)
    def leader(self,tip,end,label):
        self.line(tip,end,'B-DETAIL');dx,dy=tip[0]-end[0],tip[1]-end[1];length=math.hypot(dx,dy)
        if length:
            ux,uy=dx/length,dy/length
            pts=[tip,(tip[0]-2*ux+.35*uy,tip[1]-2*uy-.35*ux),(tip[0]-2*ux-.35*uy,tip[1]-2*uy+.35*ux)]
            self.m.add_solid([self.pt(p) for p in [*pts,pts[-1]]],dxfattribs={'layer':'B-DETAIL'})
        self.text(end[0]+1,end[1]+1,label)
    def view_title(self,x,y,title,scale=None):
        self.text(x,y,title,5,'center',paper=True);width=len(title)*3.5+8
        self.line((x-width/2,y-4),(x+width/2,y-4),'P-FRAME',True)
        self.line((x-width/2,y-5),(x+width/2,y-5),'P-GRID',True)
        if scale is not None:self.text(x+width/2+8,y,'1:'+str(int(scale)),3.5,paper=True,numeric=True)
    def subview(self, scale, center, size):
        view=copy(self);view.scale=float(scale)
        # Keep detail geometry outside the main viewport but close enough for
        # useful model-space Zoom Extents when editing the DWG.
        view.origin=(self.W*self.scale+10000.+len(self.views)*20000.,self.H*self.scale/2)
        view.dimstyle='CN_MM_'+str(int(scale))
        if view.dimstyle not in self.d.dimstyles:
            attrs=self.d.dimstyles.get(self.dimstyle).dxf.all_existing_dxf_attribs()
            attrs={k:v for k,v in attrs.items() if k not in ('name','handle','owner')}
            attrs['dimscale']=view.scale
            self.d.dimstyles.new(view.dimstyle,dxfattribs=attrs)
        self.p.add_viewport(center=center,size=size,view_center_point=view.origin,
            view_height=size[1]*view.scale,dxfattribs={'layer':'P-VPORT','flags':16384})
        self.views[str(len(self.views))]=view
        return view

    def frame(self,r):
        W,H=self.W,self.H
        # Reference PDF: A3 landscape, binding margin and a compact lower-right
        # institution/project/drawing/signature block. The extra ID row is requested.
        self.rect(17.5,7,W-24.5,H-14,'P-FRAME',True)
        c=r['input'];right=W-7;x=right-142;y=7
        self.rect(x,y,142,40,'P-FRAME',True)
        def line(a,b):self.line(a,b,'P-GRID',True)
        line((x,y+30),(right,y+30))
        for xx in (x+58,x+72):line((xx,y+30),(xx,y+40))
        for xx in (x+15,x+62,x+116,x+128):line((xx,y),(xx,y+30))
        for yy in (y+7.5,y+15,y+22.5):
            line((x,yy),(x+62,yy));line((x+116,yy),(right,yy))
        def cell(cx,cy,value,width,height=3.0):
            value=str(value) if value else '________'
            # Keep all user data; long values are split or reduced to fit a cell.
            units=sum(.7 if ord(ch)>255 else .4 for ch in value)
            font_height=height if units*height<=width else (2.5 if units*2.5<=width else 0)
            if not font_height:
                parts=[];part='';used=0
                for ch in value:
                    unit=.7 if ord(ch)>255 else .4
                    if (used+unit)*2.5>width:parts.append(part);part='';used=0
                    part+=ch;used+=unit
                parts.append(part)
                if len(parts)>2:raise ValueError('标题栏文字过长，请缩短：'+value)
                for i,part in enumerate(parts):self.text(cx,cy+1.8-i*3.6,part,2.5,'center',True)
            else:self.text(cx,cy,value,font_height,'center',True)
        def wrapped(cx,cy,value,width,max_chars,height=3.):
            parts=[value[i:i+max_chars] for i in range(0,len(value),max_chars)] or ['________']
            for i,part in enumerate(parts):cell(cx,cy+(len(parts)-1)*height*.7-i*height*1.4,part,width,height)
        wrapped(x+29,y+35,c.get('institution',''),54,22,3.5)
        cell(x+65,y+35,'题目',12,3.5)
        wrapped(x+107,y+35,c['project_name'],66,30,3.)
        for i,(label,key) in enumerate((('班级','class_name'),('姓名','designer_name'),('学号','student_id'),('指导老师','supervisor'))):
            yy=y+26.25-i*7.5
            cell(x+7.5,yy,label,13,2.8);cell(x+38.5,yy,c.get(key,''),43,3.)
        wrapped(x+89,y+15,self.title,50,12,4.)
        for i,(label,value) in enumerate((('图别','课程'),('图号','BC-'+self.number),('比例','1:'+str(int(self.scale))),('日期',c.get('drawing_date','')))):
            yy=y+26.25-i*7.5
            cell(x+122,yy,label,10,2.8);cell(x+135,yy,value,12,2.5)
        self.line((25,3),(125,3),'P-GRID',True)
        for i in range(11):self.line((25+10*i,3),(25+10*i,5),'P-GRID',True)
        self.text(130,3,'校核尺100 mm（按原幅面打印）',2.5,paper=True)
        self.p.add_viewport(center=(W/2,H/2),size=(W,H),
            view_center_point=(W*self.scale/2,H*self.scale/2),view_height=H*self.scale,
            dxfattribs={'layer':'P-VPORT','flags':16384})
        self.d.set_modelspace_vport(height=H*self.scale,center=(W*self.scale/2,H*self.scale/2))

    def save(self,path):
        self.d.saveas(path);d=ezdxf.readfile(path);audit=d.audit()
        if audit.has_errors:raise RuntimeError('图纸实体审查失败: '+str(path))
        dims=list(d.modelspace().query('DIMENSION'));measured=[float(e.get_measurement()) for e in dims]
        if len(measured)!=len(self.expected) or not np.allclose(measured,self.expected,rtol=1e-9,atol=1e-5):
            raise RuntimeError('尺寸数值与真实几何不一致')
        return dict(file=path.name,entities=len(d.modelspace()),paper_entities=len(self.p),dimensions=len(dims),
                    measurements_mm=measured,expected_measurements_mm=self.expected,audit_errors=0,
                    paper_mm=[self.W,self.H],plot_scale='1:1',viewport_scale=1/self.scale,
                    lineweights_mm=sorted(set(w/100 for w,_ in LAYERS.values())),
                    viewport_scales=[v.get_scale() for v in self.p.query('VIEWPORT') if v.dxf.id>1],
                    fonts={'CN_FS':dict(file=CN_FONT,width_factor=.7),'ISO_NUM':dict(file=NUM_FONT,width_factor=1)},
                    text_heights_paper_mm=sorted({round(e.dxf.height,3) for e in self.p.query('TEXT')} |
                        {round(e.dxf.height/self.scale,3) for e in self.m.query('TEXT') if e.dxf.height/self.scale<=7}),
                    frame_template='用户参考PDF_A3横向_右下角签名栏',plot_uses_lineweights=True)

