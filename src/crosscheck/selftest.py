"""Analytical runtime gates for the shipped independent kernel."""
import numpy as np
from .force import ForceBeam
from .section import SectionModel


def run():
    L=20000.;EI=3e16;q=30.;rows=[]
    def check(name,actual,expected,relative=1e-4,absolute=1e-7):
        actual=np.asarray(actual);expected=np.asarray(expected)
        ok=bool(np.all(np.isfinite(actual)) and np.all(abs(actual-expected)<=absolute+relative*abs(expected)))
        rows.append(dict(name=name,status='PASS' if ok else 'FAIL',actual=actual.tolist(),expected=expected.tolist(),relative_tolerance=relative,absolute_tolerance=absolute))
    b=ForceBeam([0,L],lambda t:np.full_like(t,EI),1000.)
    g=b.distributed([0,L/2,L],lambda t:np.full_like(t,q))
    check('简支梁均布荷载弯矩、反力、挠度',[g['M'][1],g['R'][0],g['W'][1]],[q*L**2/8,q*L/2,5*q*L**4/(384*EI)])
    p=b.influence([L/2],[L/2]);check('简支梁跨中集中力',[p['M'][0,0],p['W'][0,0]],[L/4,L**3/(48*EI)])
    p=b.initial_moment(np.array([L/2]),lambda t:np.full_like(t,-1e9))
    check('恒定预应力与零次效应',[p['secondary'][0],p['W'][0]],[0,-1e9*L**2/(8*EI)])
    b3=ForceBeam([0,L,2*L,3*L],lambda t:np.full_like(t,EI),1000.)
    g=b3.distributed([L,2*L],lambda t:np.full_like(t,q))
    check('三等跨连续梁支点弯矩与反力',np.r_[g['M'],g['R']],np.r_[[-q*L**2/10]*2,np.array([.4,1.1,1.1,.4])*q*L])
    mass=q/9806.65;f=b.frequency(lambda t:np.full_like(t,mass),step=2000.)
    check('简支梁解析基频',f,np.pi/(2*L**2)*np.sqrt(EI/mass),relative=2e-4)
    model=object.__new__(SectionModel)
    o=np.array([[-5,0],[5,0],[5,8],[-5,8]],float);v=np.array([[-3,2],[3,2],[3,6],[-3,6]],float)
    A=model.integrate((o,v),0,8);S=model.integrate((o,v),0,8,1);I=model.integrate((o,v),0,8,2)-S*S/A
    check('空心矩形条带面积和惯性矩',[A,I],[56,10*8**3/12-6*4**3/12],relative=1e-10)
    if any(r['status']!='PASS' for r in rows):raise RuntimeError('独立内核解析基准自检失败：'+str(rows))
    return rows
