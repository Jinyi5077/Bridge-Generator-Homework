"""Continuous beam force method: two released interior vertical reactions.

All lengths mm, forces N, EI N mm²; downward loads/displacements positive.
No element stiffness, FE shape functions, or imports from the main engine.
"""
import numpy as np
from numpy.polynomial.legendre import leggauss


def quadrature(breaks, step, order=4):
    gx,gw=leggauss(order); points=[];weights=[]
    for start,end in zip(breaks[:-1],breaks[1:]):
        cuts=np.linspace(start,end,max(1,int(np.ceil((end-start)/step)))+1)
        for a,b in zip(cuts[:-1],cuts[1:]):
            points.extend((a+b)/2+(b-a)/2*gx);weights.extend((b-a)/2*gw)
    return np.array(points),np.array(weights)


class ForceBeam:
    def __init__(self, supports, ei, step=2000., extra_breaks=()):
        self.supports=np.asarray(supports,dtype=float);self.L=float(self.supports[-1])
        if self.supports[0] != 0 or np.any(np.diff(self.supports)<=0): raise ValueError('复核支点顺序无效')
        self.ei=ei
        breaks=sorted(set(self.supports.tolist()+list(extra_breaks)))
        self.qx,self.qw=quadrature(breaks,step)
        self.flexweight=self.qw/ei(self.qx)
        self.mi=self.simple_moment(self.qx,self.supports[1:-1])
        self.f=self.mi.T@(self.flexweight[:,None]*self.mi)
        self.fi=np.linalg.inv(self.f) if self.f.size else self.f.copy()
        self.condition=float(np.linalg.cond(self.f)) if self.f.size else 1.

    def simple_moment(self, targets, loads):
        x=np.atleast_1d(targets)[:,None];t=np.atleast_1d(loads)[None,:]
        return x*(self.L-t)/self.L-np.maximum(x-t,0.)

    def redundants(self, moment_at_quad):
        return -self.fi@(self.mi.T@(self.flexweight[:,None]*np.asarray(moment_at_quad).reshape(len(self.qx),-1)))

    def influence(self, targets, load_x, sides=None):
        targets=np.asarray(targets);load_x=np.asarray(load_x)
        m0q=self.simple_moment(self.qx,load_x)
        X=self.redundants(m0q)
        mq=m0q+self.mi@X
        mt=self.simple_moment(targets,load_x)+self.simple_moment(targets,self.supports[1:-1])@X
        re=(self.L-load_x)/self.L+((self.L-self.supports[1:-1])/self.L)@X
        side=np.ones(len(targets)) if sides is None else np.asarray(sides)
        # Evaluate one-sided shears at supports; a moving load exactly on a section
        # belongs to the left branch only when the section is viewed from its right.
        delta=targets[:,None]-load_x[None,:]
        before=(delta>1e-6)|((abs(delta)<=1e-6)&(side[:,None]>0))
        delta=targets[:,None]-self.supports[1:-1][None,:]
        passed=(delta>1e-6)|((abs(delta)<=1e-6)&(side[:,None]>0))
        vt=re[None,:]-before-passed@X
        wt=self.simple_moment(targets,self.qx)@(self.flexweight[:,None]*mq)
        reactions=np.vstack([re,-X,1-re+np.sum(X,axis=0)])
        return dict(M=mt,V=vt,W=wt,R=reactions)

    def distributed(self, targets, q, sides=None):
        # Integrate the continuous load before recovering shear. Integrating
        # a Heaviside influence with quadrature nodes that straddle a requested
        # section would introduce a spurious half-panel shear error.
        from scipy.interpolate import CubicSpline,PPoly
        grid=np.unique(np.r_[np.linspace(0,self.L,max(50,int(np.ceil(self.L/500)))+1),self.supports,
                             (self.supports[1:-1].mean() if len(self.supports)>2 else self.L/2)])
        spline=CubicSpline(grid,q(grid));p0=spline.antiderivative()
        cc=spline.c;d=grid[:-1]
        first=PPoly(np.vstack([cc[0],cc[1]+d*cc[0],cc[2]+d*cc[1],cc[3]+d*cc[2],d*cc[3]]),grid).antiderivative()
        total=p0(self.L)-p0(0);total_first=first(self.L)-first(0)
        r0=total-total_first/self.L
        def m0(t):return r0*t-t*(p0(t)-p0(0))+(first(t)-first(0))
        X=self.redundants(m0(self.qx)).ravel()
        mq=m0(self.qx)+self.mi@X
        targets=np.asarray(targets);side=np.ones(len(targets)) if sides is None else np.asarray(sides)
        re=r0+((self.L-self.supports[1:-1])/self.L)@X
        delta=targets[:,None]-self.supports[1:-1][None,:]
        passed=(delta>1e-6)|((abs(delta)<=1e-6)&(side[:,None]>0))
        R=np.r_[re,-X,total-re+np.sum(X)]
        return dict(M=m0(targets)+self.simple_moment(targets,self.supports[1:-1])@X,
                    V=re-(p0(targets)-p0(0))-passed@X,
                    W=self.simple_moment(targets,self.qx)@(self.flexweight*mq),R=R,
                    balance=float(np.sum(R)-total))

    def initial_moment(self, targets, mp):
        initial=mp(self.qx);X=self.redundants(initial).ravel()
        secondary=self.simple_moment(targets,self.supports[1:-1])@X
        totalq=initial+self.mi@X
        w=self.simple_moment(targets,self.qx)@(self.flexweight*totalq)
        residual=self.mi.T@(self.flexweight*totalq)
        return dict(primary=mp(targets),secondary=secondary,total=mp(targets)+secondary,
                    W=w,compatibility=float(np.max(abs(residual))) if residual.size else 0.)

    def frequency(self, mass, step=8000.):
        from scipy.linalg import eigh
        x,w=quadrature(self.supports,step,order=3)
        basic=self.simple_moment(self.qx,x)
        b=basic.T@(self.flexweight[:,None]*self.mi)
        G=basic.T@(self.flexweight[:,None]*basic)-b@self.fi@b.T
        root=np.sqrt(w*mass(x))
        H=root[:,None]*G*root[None,:]
        lam=float(eigh(H,subset_by_index=[len(x)-1,len(x)-1],eigvals_only=True)[0])
        if lam <= 0: raise ValueError('复核动力柔度特征值非正')
        return 1/(2*np.pi*np.sqrt(lam))
