import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from bridgegen.design import analyse
from crosscheck.contract import input_spec,digest,main_hash
from crosscheck.service import run_crosscheck,rule_audit
from crosscheck.compare import compare,compare_array


class CrosscheckIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main=analyse({})
        cls.temp=tempfile.TemporaryDirectory()
        cls.report=run_crosscheck(cls.main,cls.temp.name)
        cls.output=json.loads((Path(cls.temp.name)/'交叉复核'/cls.report['provenance']['run_id']/'独立输出.json').read_text(encoding='utf-8'))
        cls.b=cls.output['result']

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_independent_process_and_scope(self):
        r=self.report
        self.assertEqual(r['execution_status'],'PASS',r['message'])
        self.assertEqual(r['numerical_status'],'PASS',str([v for v in r['comparisons'] if v['status']!='PASS']))
        self.assertEqual(r['coverage_status'],'PARTIAL')
        self.assertEqual(r['rule_status'],'PARTIAL')
        self.assertTrue(all(v['status']=='PASS' for v in r['convergence']))
        self.assertLess(r['invariants']['force_balance_kn'],1e-6)
        self.assertLess(r['invariants']['compatibility_mm'],.0001)
        self.assertEqual(r['provenance']['main_numeric_hash'],main_hash(self.main))
        self.assertGreater(len(r['provenance']['kernel_hashes']),3)
        self.assertEqual(self.report['status'],'CONSISTENT_WITHIN_SCOPE')

    def test_no_main_effects_transmitted(self):
        spec=input_spec(self.main);scheme=spec['scheme']
        self.assertEqual(set(spec),{'schema','run_id','input','scheme','queries'})
        self.assertNotIn('force_effective',scheme);self.assertNotIn('analysis',spec)
        self.assertNotIn('inertia',scheme);self.assertNotIn('sigma_effective',scheme)
        before=self.main['prestress']['profile']['active_tendon_count'][0]
        spec['scheme']['active_counts'][0]=9999
        self.assertEqual(self.main['prestress']['profile']['active_tendon_count'][0],before)

    def test_fault_injection_wrong_units_lanes_and_losses(self):
        original=digest(self.b)
        for field,multiplier in [('M_dead1',1000),('M_live_max',1.2),('prestress_force_effective',.9),('shear_capacity',.8)]:
            damaged=copy.deepcopy(self.main)
            damaged['analysis'][field]=[v*multiplier for v in damaged['analysis'][field]]
            rows=compare(damaged,self.b)
            row=next(v for v in rows if v['field']==field)
            self.assertEqual(row['status'],'FAIL',field)
        self.assertEqual(digest(self.b),original)

    def test_missing_nan_and_misaligned_arrays_never_pass(self):
        for value in (None,[float('nan')],[1,2,3]):
            self.assertEqual(compare_array('bad',[1.],value,'kN',.01,.03,.1)['status'],'ERROR')
        damaged=copy.deepcopy(self.main);del damaged['analysis']['M_dead1']
        self.assertEqual(next(v for v in compare(damaged,self.b) if v['field']=='M_dead1')['status'],'ERROR')
        damaged=copy.deepcopy(self.b);del damaged['analysis']['M_dead1']
        self.assertEqual(next(v for v in compare(self.main,damaged) if v['field']=='M_dead1')['status'],'ERROR')

    def test_separate_rule_failures(self):
        m=copy.deepcopy(self.main)
        m['structural_verification']['checks']['deflection']['rule_version']='legacy'
        self.assertEqual(next(v for v in rule_audit(m,self.b) if v['id']=='DEFLECTION')['status'],'FAIL')
        m=copy.deepcopy(self.main);m['input']['strand_fpk_mpa']=1670
        self.assertEqual(next(v for v in rule_audit(m,self.b) if v['id']=='STRAND_GRADE')['status'],'FAIL')

    def test_near_zero_and_one_sided_shear(self):
        self.assertEqual(compare_array('zero',[0.],[.02],'kN',.01,.03,.1)['status'],'PASS')
        a=self.b['analysis'];x=np.array(a['x']);V=np.array(a['V_dead'])
        for i,pier in enumerate(self.b['geometry']['supports'][1:-1],1):
            ids=np.flatnonzero(np.isclose(x,pier))
            self.assertAlmostEqual(V[ids[1]]-V[ids[0]],self.b['reactions']['R_dead'][i],delta=.001)

    def test_recheck_timeout_is_error(self):
        r=run_crosscheck(self.main,self.temp.name,timeout=.001)
        self.assertEqual(r['execution_status'],'ERROR');self.assertEqual(r['status'],'ERROR')
        self.assertEqual(r['counts']['PASS'],0)
        self.assertNotEqual(r['provenance']['run_id'],self.report['provenance']['run_id'])
