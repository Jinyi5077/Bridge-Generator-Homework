import ast
import copy
import inspect
import unittest
from pathlib import Path
import numpy as np
from crosscheck.force import ForceBeam
from crosscheck.section import SectionModel


class IndependentMechanicsTests(unittest.TestCase):
    def beam(self, supports):
        return ForceBeam(supports,lambda x:np.full_like(x,3e16),500.,extra_breaks=np.array(supports)/2)

    def test_simply_uniform_and_point(self):
        L=20000.;q=30.;b=self.beam([0,L]);x=np.array([0,L/2,L])
        g=b.distributed(x,lambda t:np.full_like(t,q))
        self.assertAlmostEqual(g['M'][1],q*L**2/8,delta=1e-5)
        self.assertAlmostEqual(g['W'][1],5*q*L**4/(384*3e16),delta=2e-4)
        np.testing.assert_allclose(g['R'],q*L/2,rtol=1e-10)
        p=b.influence(x,[L/2])
        self.assertAlmostEqual(p['M'][1,0],L/4,places=6)
        self.assertAlmostEqual(p['W'][1,0],L**3/(48*3e16),delta=1e-10)

    def test_two_equal_and_three_equal(self):
        L=20000.;q=30.
        b=self.beam([0,L,2*L]);g=b.distributed([0,L,2*L],lambda t:np.full_like(t,q))
        self.assertAlmostEqual(g['M'][1],-q*L**2/8,delta=q*L**2/8*1e-4)
        np.testing.assert_allclose(g['R'],[.375,1.25,.375]*np.array(q*L),rtol=1e-4)
        b=self.beam([0,L,2*L,3*L]);g=b.distributed([0,L,2*L,3*L],lambda t:np.full_like(t,q))
        np.testing.assert_allclose(g['M'][1:3],-q*L**2/10,rtol=1e-4)
        np.testing.assert_allclose(g['R'],np.array([.4,1.1,1.1,.4])*q*L,rtol=1e-4)
        np.testing.assert_allclose(g['W'],0,atol=1e-10)

    def test_constant_prestress_and_frequency(self):
        L=20000.;b=self.beam([0,L]);g=b.initial_moment(np.array([0,L/2,L]),lambda t:np.full_like(t,-1e9))
        np.testing.assert_allclose(g['secondary'],0,atol=1e-6)
        self.assertAlmostEqual(g['W'][1],-1e9*L*L/(8*3e16),delta=1e-5)
        mass=30/9806.65
        f=b.frequency(lambda t:np.full_like(t,mass),step=1000)
        exact=np.pi/(2*L**2)*np.sqrt(3e16/mass)
        self.assertAlmostEqual(f,exact,delta=exact*.0001)

    def test_one_sided_support_shear(self):
        L=20000.;b=self.beam([0,L,2*L]);g=b.distributed([L,L],lambda t:np.full_like(t,30),[-1,1])
        self.assertAlmostEqual(g['V'][1]-g['V'][0],g['R'][1],delta=1e-5)
        # Metric conversions can differ by a few floating-point ulps.
        near=b.distributed([L+1e-8,L+1e-8],lambda t:np.full_like(t,30),[-1,1])
        self.assertAlmostEqual(near['V'][1]-near['V'][0],near['R'][1],delta=1e-5)

    def test_kernel_import_independence(self):
        root=Path(inspect.getfile(ForceBeam)).parent
        for filename in ('force.py','section.py','kernel.py','rules.py'):
            tree=ast.parse((root/filename).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertFalse(any(a.name.startswith('bridgegen') for a in node.names))
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith('bridgegen'))

    def test_section_scan_matches_rectangle_minus_void(self):
        # Direct independent strip integral of a hollow rectangle.
        model=object.__new__(SectionModel)
        outer=np.array([[-5,0],[5,0],[5,8],[-5,8]],float)
        void=np.array([[-3,2],[3,2],[3,6],[-3,6]],float)
        A=model.integrate((outer,void),0,8)
        first=model.integrate((outer,void),0,8,1)
        I=model.integrate((outer,void),0,8,2)-A*(first/A)**2
        self.assertAlmostEqual(A,56,places=10)
        self.assertAlmostEqual(first/A,4,places=10)
        self.assertAlmostEqual(I,10*8**3/12-6*4**3/12,places=10)
