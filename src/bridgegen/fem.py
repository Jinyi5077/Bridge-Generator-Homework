"""Euler–Bernoulli beam. kN, m. v positive up; M positive sagging.

All point loads use consistent Hermite interpolation. End-force recovery
subtracts the local load vector so moving-load shear jumps are preserved.
"""
import numpy as np
from scipy.linalg import cho_factor, cho_solve, eigh


def shape(t,L):
    return np.array([1-3*t*t+2*t**3,L*(t-2*t*t+t**3),3*t*t-2*t**3,L*(-t*t+t**3)])


def curvature(t,L):
    return np.array([(-6+12*t)/L**2,(-4+6*t)/L,(6-12*t)/L**2,(-2+6*t)/L])


class Beam:
    def __init__(self,x,EI,supports,mass=None,ei_function=None):
        self.x=np.asarray(x,dtype=float);self.L=np.diff(self.x);self.ne=len(self.L)
        self.EI=np.broadcast_to(EI,(self.ne,)).astype(float)
        self.nd=2*len(self.x)
        self.dof=np.array([[2*i,2*i+1,2*i+2,2*i+3] for i in range(self.ne)])
        self.K=np.zeros((self.nd,self.nd));self.ke=[]
        self.mass=np.zeros_like(self.K)
        for i,(L,EI) in enumerate(zip(self.L,self.EI)):
            k=EI/L**3*np.array([[12,6*L,-12,6*L],[6*L,4*L*L,-6*L,2*L*L],
                                [-12,-6*L,12,-6*L],[6*L,2*L*L,-6*L,4*L*L]])
            if ei_function is not None:
                z,w=np.polynomial.legendre.leggauss(4);t=(z+1)/2
                values=ei_function(self.x[i]+t*L)
                curv=np.array([curvature(tj,L) for tj in t])
                k=np.einsum('j,ji,jk->ik',values*w*L/2,curv,curv)
            self.ke.append(k); ix=np.ix_(self.dof[i],self.dof[i]);self.K[ix]+=k
            if mass is not None:
                self.mass[ix]+=mass[i]*L/420*np.array([[156,22*L,54,-13*L],[22*L,4*L*L,13*L,-3*L*L],
                                                    [54,13*L,156,-22*L],[-13*L,-3*L*L,-22*L,4*L*L]])
        self.ke=np.array(self.ke)
        self.fixed=np.array([2*int(np.argmin(abs(self.x-s))) for s in supports])
        if any(abs(self.x[j//2]-s)>1e-8 for j,s in zip(self.fixed,supports)):
            raise ValueError('Support must coincide with mesh node')
        self.free=np.setdiff1d(np.arange(self.nd),self.fixed)
        self.factor=cho_factor(self.K[np.ix_(self.free,self.free)])
        self.stations=np.column_stack((self.x[:-1],self.x[1:])).ravel()

    def solve(self,F,local=None):
        F=np.asarray(F); multi=F.ndim==2
        if not multi:F=F[:,None]
        u=np.zeros_like(F);u[self.free]=cho_solve(self.factor,F[self.free])
        residual=F[self.free]-self.K[np.ix_(self.free,self.free)]@u[self.free]
        u[self.free]+=cho_solve(self.factor,residual)
        end=np.einsum('eij,ejk->eik',self.ke,u[self.dof])
        if local is not None:
            if local.ndim==2: local=local[:,:,None]
            end-=local
        M=np.stack((-end[:,1],end[:,3]),axis=1).reshape(2*self.ne,-1)
        V=np.stack((end[:,0],-end[:,2]),axis=1).reshape(2*self.ne,-1)
        R=(self.K@u-F)[self.fixed]
        if multi:return dict(u=u,M=M,V=V,R=R)
        return dict(u=u[:,0],M=M[:,0],V=V[:,0],R=R[:,0])

    def distributed(self,q):
        L=self.L
        if callable(q):
            z,w=np.polynomial.legendre.leggauss(4);t=(z+1)/2
            local=np.array([sum((wi*length/2)*qi*shape(ti,length)
                                for ti,wi,qi in zip(t,w,q(start+t*length)))
                            for start,length in zip(self.x[:-1],L)])
        else:
            q=np.broadcast_to(q,(self.ne,))
            local=q[:,None]*np.column_stack((L/2,L*L/12,L/2,-L*L/12))
        F=np.zeros(self.nd)
        for d,f in zip(self.dof,local):F[d]+=f
        return self.solve(F,local)

    def initial_moment(self,fn):
        """Return secondary effects of a primary prestress moment M_p(x)."""
        local=np.zeros((self.ne,4))
        z,w=np.polynomial.legendre.leggauss(4)
        for e,L in enumerate(self.L):
            for t,wt in zip((z+1)/2,w*L/2):
                local[e]+=curvature(t,L)*float(fn(self.x[e]+t*L))*wt
        F=np.zeros(self.nd)
        for d,f in zip(self.dof,local):F[d]+=f
        res=self.solve(F,local)
        res['secondary_M']=res['M'].copy()
        res['M']=res['M']+fn(self.stations)
        return res

    def influences(self):
        """Gauss positions integrate lane UDL; nodes locate point-load extrema."""
        z,w=np.polynomial.legendre.leggauss(4)
        positions=[];weights=[];elements=[];ts=[]
        for e,L in enumerate(self.L):
            for t,wt in zip((z+1)/2,w*L/2):
                positions.append(self.x[e]+t*L);weights.append(wt);elements.append(e);ts.append(t)
        ng=len(positions)
        for e,L in enumerate(self.L):
            for t in [1e-7,1-1e-7]:
                positions.append(self.x[e]+t*L);weights.append(0.);elements.append(e);ts.append(t)
        # Include all nodes for concentrated-load peaks without double-counting UDL.
        for i,x in enumerate(self.x):
            e=min(i,self.ne-1);positions.append(x);weights.append(0.);elements.append(e)
            ts.append((x-self.x[e])/self.L[e])
        F=np.zeros((self.nd,len(positions)));local=np.zeros((self.ne,4,len(positions)))
        for col,(e,t) in enumerate(zip(elements,ts)):
            local[e,:,col]=-shape(t,self.L[e]);F[self.dof[e],col]+=local[e,:,col]
        res=self.solve(F,local)
        res.update(load_x=np.array(positions),weights=np.array(weights),ngauss=ng)
        return res

    def frequency(self):
        K=self.K[np.ix_(self.free,self.free)];M=self.mass[np.ix_(self.free,self.free)]
        eig=eigh(K,M,subset_by_index=[0,0],eigvals_only=True)[0]
        return float(np.sqrt(max(eig,0))/(2*np.pi))


def envelope(influence,weights,qk,pk):
    pos=np.maximum(influence,0);neg=np.minimum(influence,0)
    return qk*(neg@weights)+pk*np.min(neg,axis=1), qk*(pos@weights)+pk*np.max(pos,axis=1)
