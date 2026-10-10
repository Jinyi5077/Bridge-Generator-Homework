"""Double click the packaged EXE, or run: python app.py --config examples/default.json."""
import argparse,json,mimetypes,os,secrets,sys,threading,webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote,urlsplit

# Small/medium beam matrices run faster without oversubscribing desktop CPUs.
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(name,'2')

ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
ASSETS=Path(getattr(sys,'_MEIPASS',ROOT))


def require_drawing_identity(config):
    """Require author details only when producing deliverable drawings."""
    for key,label in [('designer_name','绘图人姓名'),('student_id','学号')]:
        if not str(config.get(key,'')).strip():
            raise ValueError(f'请先填写{label}')


def serve(port=0,open_browser=True):
    from bridgegen.config import DEFAULT,validate,section_suggestions,span_suggestions
    state={'running':False,'logs':[],'result':None,'error':None,'folder':None}
    token=secrets.token_urlsafe(32);lock=threading.Lock()
    def progress(message):
        with lock:state['logs'].append(message)
    def worker(config,drawings_only=False):
        try:
            from bridgegen.pipeline import build
            folder=ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            result=build(config,folder,progress,drawings_only=drawings_only)
            with lock:state.update(result=result,folder=str(folder))
        except Exception as exc:
            with lock:state['error']=str(exc)
        finally:
            with lock:state['running']=False
    def recheck_worker(result,folder):
        try:
            from crosscheck.service import run_crosscheck
            result['crosscheck']=run_crosscheck(result,folder,progress)
            result['status']=result['status'].split('；独立交叉验证：')[0]+'；独立交叉验证：'+result['crosscheck']['status']
            Path(folder,'设计结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            # Earlier report runs remain immutable and retain their own IDs.
            from bridgegen.pipeline import write_manifest
            write_manifest(result,Path(folder))
            with lock:state['result']=result
        except Exception as exc:
            with lock:state['error']=str(exc)
        finally:
            with lock:state['running']=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,data,status=200,content_type='application/json; charset=utf-8'):
            body=json.dumps(data,ensure_ascii=False).encode('utf-8') if not isinstance(data,bytes) else data
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            path=unquote(urlsplit(self.path).path)
            if path=='/':return self.respond((ASSETS/'ui.html').read_bytes(),content_type='text/html; charset=utf-8')
            if path=='/api/defaults':return self.respond({'config':DEFAULT,'token':token,'version':'0.12.0'})
            if path=='/api/status':
                with lock:
                    snap={k:v for k,v in state.items() if k!='folder'}
                    if state['folder']:
                        folder=Path(state['folder']);snap['files']=[p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()]
                return self.respond(snap)
            if path.startswith('/files/') and state['folder']:
                root=Path(state['folder']).resolve();p=(root/path[len('/files/'):]).resolve()
                if p.is_relative_to(root) and p.is_file():
                    return self.respond(p.read_bytes(),content_type=mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            self.respond({'error':'未找到内容'},404)
        def do_POST(self):
            if self.headers.get('X-Bridge-Token')!=token:return self.respond({'error':'无效请求'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>50000:raise ValueError('请求过大')
                data=json.loads(self.rfile.read(length) or '{}')
                if self.path=='/api/normalize':
                    return self.respond({'config':validate(data)})
                if self.path=='/api/suggest':
                    span=span_suggestions(data.get('main_span'),data.get('side_span_ratio',0.60))
                    section=section_suggestions(data.get('main_span'),data.get('lanes',4))
                    notes=[span.pop('suggestion_basis'),section.pop('suggestion_basis')]
                    span.pop('arrangement',None)
                    return self.respond({'values':{**span,**section},'note':'；'.join(notes)})
                if self.path=='/api/run':
                    drawings_only=bool(data.pop('drawings_only',False))
                    config=validate(data)
                    require_drawing_identity(config)
                    with lock:
                        if state['running']:return self.respond({'error':'已有任务正在运行'},409)
                        state.update(running=True,logs=['正在准备参数与计算模型'],result=None,error=None,folder=None)
                    threading.Thread(target=worker,args=(config,drawings_only),daemon=True).start()
                    return self.respond({'ok':True})
                if self.path=='/api/recheck':
                    with lock:
                        if state['running']:return self.respond({'error':'已有任务正在运行'},409)
                        if not state['result'] or not state['folder']:return self.respond({'error':'请先完成一次计算'},400)
                        snapshot=json.loads(json.dumps(state['result']));folder=state['folder']
                        state.update(running=True,error=None,logs=['对本次固定方案重新执行独立复核'])
                    threading.Thread(target=recheck_worker,args=(snapshot,folder),daemon=True).start()
                    return self.respond({'ok':True})
                if self.path=='/api/open' and state['folder']:
                    if os.name=='nt':os.startfile(state['folder'])
                    return self.respond({'ok':True})
                self.respond({'error':'无效操作'},404)
            except (ValueError,TypeError,KeyError) as exc:self.respond({'error':str(exc)},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    (ROOT/'当前界面地址.txt').write_text(url,encoding='utf-8')
    print('BridgeGenerator '+url,flush=True)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


def main():
    # Worker dispatch precedes all UI/main-engine imports, so the second
    # calculation process cannot inherit A's model or computed arrays.
    if len(sys.argv)==4 and sys.argv[1]=='--crosscheck-worker':
        from crosscheck.worker import run
        run(sys.argv[2],sys.argv[3]);return 0
    p=argparse.ArgumentParser(description='V0.12 连续箱梁课程设计与独立交叉验证生成器（50–150 m；2/4/6车道）')
    p.add_argument('--config',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--recheck',type=Path,help='独立复核已生成的设计结果JSON，不重新选束或出图')
    p.add_argument('--no-dwg',action='store_true');p.add_argument('--port',type=int,default=0)
    p.add_argument('--no-browser',action='store_true')
    p.add_argument('--drawings-only',action='store_true',help='仅生成CAD图纸、PDF及检查记录')
    args=p.parse_args()
    if args.recheck:
        if args.config:p.error('--config与--recheck不能同时使用')
        from crosscheck.service import run_crosscheck
        r=json.loads(args.recheck.read_text(encoding='utf-8-sig'))
        target=args.output or ROOT/'results'/('复核_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        cc=run_crosscheck(r,target,print)
        print(cc['message']);print(str(target.resolve()))
        return 0 if cc['status']=='CONSISTENT_WITHIN_SCOPE' else 3
    if args.config:
        from bridgegen.pipeline import build
        cfg=json.loads(args.config.read_text(encoding='utf-8-sig'))
        target=args.output or ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        r=build(cfg,target,print,args.no_dwg,args.drawings_only)
        print(r['status']);print(r['exports']['dwg']['message']);print(str(target.resolve()))
        return 0 if args.no_dwg or r['exports']['dwg']['status']=='ok' else 2
    serve(args.port,not args.no_browser)


if __name__=='__main__':
    try:sys.exit(main() or 0)
    except Exception as exc:
        (ROOT/'启动错误.txt').write_text(str(exc),encoding='utf-8')
        raise
