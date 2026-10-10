"""Regenerate boundaries; horizontal strips and quadrature, not Green moments."""
import numpy as np
from numpy.polynomial.legendre import leggauss
GZ,GW=leggauss(3)


class SectionModel:
    def __init__(self, cfg):
        self.c = cfg
        expected='single' if cfg['lanes']==2 else 'separated'
        if cfg['layout']!=expected:raise ValueError('复核发现车道数与分幅输入不一致')
        if cfg['side_span_mode']=='auto_ratio':
            span=cfg['main_span']*cfg['side_span_ratio']
            if max(abs(cfg['left_side_span']-span),abs(cfg['right_side_span']-span))>1e-8:
                raise ValueError('复核发现自动边跨匹配不一致')
        elif cfg['side_span_mode']!='manual':raise ValueError('复核边跨模式无效')
        self.decks = 1 if cfg['lanes'] == 2 or cfg['layout'] == 'single' else 2
        self.lanes = cfg['lanes']//self.decks
        self.B = (self.lanes*cfg['lane_width']+2*cfg['barrier_width']+
                  cfg['inner_margin']+cfg['outer_margin'])*1000
        self.b = self.B-2000*cfg['cantilever_width']
        main = cfg['main_span']*1000
        left = cfg['left_side_span']*1000
        right = cfg['right_side_span']*1000
        self.supports = np.array([0., left, left+main, left+main+right])
        self.cache = {}
        self.strips = {}

    def boundaries(self, x):
        c = self.c; _, a, b, L = self.supports
        f = ((x/a) if x < a else ((L-x)/(L-b) if x > b else abs(x-(a+b)/2)/((b-a)/2)))**c['height_curve_exponent']
        scale = c['main_span']/c['height_reference_span']
        hm = max(1.8, c['height_mid']*scale)*1000
        h = hm+(c['height_pier']*scale*1000-hm)*f
        tt, tip = c['top_thickness']*1000, c['tip_thickness']*1000
        tw = (c['web_mid']+(c['web_pier']-c['web_mid'])*f)*1000
        tb = (c['bottom_mid']+(c['bottom_pier']-c['bottom_mid'])*f)*1000
        uh, uv = c['top_haunch_horizontal']*1000, c['top_haunch_vertical']*1000
        bh, bv = c['bottom_chamfer_horizontal']*1000, c['bottom_chamfer_vertical']*1000
        B, box = self.B/2, self.b/2
        t = lambda z: c['cross_slope']*z
        outer = [(-B,t(-B)),(B,t(B)),(B,t(B)+tip),(box,t(box)+tt+uv),
                 (box,h),(-box,h),(-box,t(-box)+tt+uv),(-B,t(-B)+tip)]
        l,r = -box+tw,box-tw
        void = [(l,t(l)+tt+uv),(l+uh,t(l+uh)+tt),(r-uh,t(r-uh)+tt),
                (r,t(r)+tt+uv),(r,h-tb-bv),(r-bh,h-tb),(l+bh,h-tb),(l,h-tb-bv)]
        return np.array(outer), np.array(void), dict(h=h,tw=tw,tb=tb)

    @staticmethod
    def intervals(poly, y):
        crosses = []
        for (x0,y0),(x1,y1) in zip(poly, np.roll(poly,-1,axis=0)):
            if min(y0,y1) <= y < max(y0,y1):
                crosses.append(x0+(y-y0)*(x1-x0)/(y1-y0))
        crosses.sort()
        return list(zip(crosses[::2],crosses[1::2]))

    def width(self, polys, y):
        return float(self.widths(polys,np.array([y]))[0])

    @staticmethod
    def widths(polys, ys):
        widths=[];ys=np.asarray(ys)[:,None]
        for p in polys:
            end=np.roll(p,-1,axis=0);dy=end[:,1]-p[:,1]
            safe=np.where(dy==0,1.,dy)
            crosses=p[:,0]+(ys-p[:,1])*(end[:,0]-p[:,0])/safe
            mask=(ys>=np.minimum(p[:,1],end[:,1]))&(ys<np.maximum(p[:,1],end[:,1]))
            widths.append(abs(np.sum(crosses*np.sign(dy)*mask,axis=1)))
        return widths[0]-widths[1]

    def strip_profile(self,polys):
        cuts=np.unique(np.concatenate([p[:,1] for p in polys]));low,high=cuts[:-1],cuts[1:]
        y1=low+(high-low)/3;y2=low+(high-low)*2/3
        w1=self.widths(polys,y1);w2=self.widths(polys,y2)
        slope=(w2-w1)/(y2-y1)
        return low,high,slope,w1-slope*y1

    @staticmethod
    def integral_profile(profile,lo,hi,power=0):
        low,high,slope,intercept=profile
        a=np.clip(low,lo,hi);b=np.clip(high,lo,hi)
        return float(np.sum(slope*(b**(power+2)-a**(power+2))/(power+2)+intercept*(b**(power+1)-a**(power+1))/(power+1)))

    def integrate(self, polys, lo, hi, power=0):
        return self.integral_profile(self.strip_profile(polys),lo,hi,power)

    def at(self, x):
        key = round(float(x),6)
        if key not in self.cache:
            o,v,extra = self.boundaries(x); polys=(o,v)
            top,bottom = min(o[:,1]),max(o[:,1])
            profile=self.strip_profile(polys)
            A = self.integral_profile(profile,top,bottom)
            if A <= 0: raise ValueError('复核截面面积非正')
            yc = self.integral_profile(profile,top,bottom,1)/A
            I = self.integral_profile(profile,top,bottom,2)-A*yc*yc
            if I <= 0: raise ValueError('复核截面惯性矩非正')
            Q = yc*self.integral_profile(profile,top,yc)-self.integral_profile(profile,top,yc,1)
            self.cache[key] = dict(A=A,I=I,y=yc,Wt=I/(yc-top),Wb=I/(bottom-yc),
                                   top=top,bottom=bottom,Q=Q,b=self.width(polys,yc),**extra)
            self.strips[key]=profile
        return self.cache[key]

    def array(self, x):
        rows = [self.at(t) for t in x]
        return {k:np.array([r[k] for r in rows]) for k in rows[0]}

    def compressed(self, x, depth, upper):
        sec=self.at(x);top,bottom=sec['top'],sec['bottom']
        lo,hi = (top,min(bottom,top+depth)) if upper else (max(top,bottom-depth),bottom)
        low,high,slope,intercept=self.strips[round(float(x),6)]
        a=np.clip(low,lo,hi);b=np.clip(high,lo,hi)
        A=np.sum(slope*(b*b-a*a)/2+intercept*(b-a))
        first=np.sum(slope*(b**3-a**3)/3+intercept*(b*b-a*a)/2)
        return A, first/A if A > 1e-12 else (lo+hi)/2
