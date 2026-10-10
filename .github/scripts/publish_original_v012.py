"""Reassemble approved original bytes and publish exactly that archive to this repo."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request

repository=os.environ['GITHUB_REPOSITORY']
assert repository=='Jinyi5077/Bridge-Generator-Homework'
token=os.environ['GH_TOKEN']
headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
         'X-GitHub-Api-Version':'2022-11-28','User-Agent':'Bridge-Generator-Homework-original-release'}
api='https://api.github.com/repos/'+repository

def request(url,body=None):
    h=dict(headers)
    if body is not None:h['Content-Type']='application/json'
    req=urllib.request.Request(url,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=h)
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)

parts=Path('release-parts');manifest=json.loads((parts/'manifest.json').read_text(encoding='utf-8'))
expected='23de22bad721b4c406ef58fd2220afe314311748f0025e0e7346211aad13e74e'
assert manifest['sha256']==expected and manifest['bytes']==101181598
assert manifest['filename']=='BridgeGenerator_V0.12_程序包.zip'
with tempfile.TemporaryDirectory(prefix='bridge_original_release_') as temp:
    archive=Path(temp)/manifest['filename'];digest=hashlib.sha256();total=0
    with archive.open('wb') as target:
        for part in manifest['parts']:
            source=parts/part['name'];assert source.parent==parts
            block=source.read_bytes();assert len(block)==part['bytes']
            assert hashlib.sha256(block).hexdigest()==part['sha256']
            target.write(block);digest.update(block);total+=len(block)
    assert total==manifest['bytes'] and digest.hexdigest()==expected
    print('Original archive assembled and verified:',total,'bytes SHA-256',expected)
    try:
        release=request(api+'/releases/tags/v0.12.0')
    except urllib.error.HTTPError as exc:
        if exc.code!=404:raise
        release=request(api+'/releases',dict(tag_name='v0.12.0',target_commitish='main',
            name='V0.12 连续箱梁课程设计生成器',draft=False,prerelease=False,
            body='原始 Windows V0.12 程序包，包含离线计算与内置独立复核。\n\n'
                 '2026-10-10 本机运行 60＋100＋60 m 四车道分离式箱梁算例：六类课程验算通过，219 项数值对照一致，3 张 DWG 经 ODA 回转检查。\n\n'
                 '程序包无需另装 Python 或商业结构计算软件；DWG 导出需自行安装 ODA File Converter。源码、详细算法及 34 个代表性成果见 main 分支。\n\n'
                 '复核覆盖课程纵向模型，逐龄期、完整施工历史、空间、局部和下部结构未完成。\n\n'
                 'SHA-256: `'+expected+'`\n\n'
                 '资产通过原始文件分段上传后校验合并，未重编译、未重新打包。'))
    for asset in release.get('assets',[]):
        if asset['name']==manifest['filename']:
            assert asset['size']==total and asset.get('digest')=='sha256:'+expected
            print('Exact original asset already published:',asset['browser_download_url'])
            raise SystemExit(0)
    url=urllib.parse.urlsplit(release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(manifest['filename']))
    assert url.hostname=='uploads.github.com'
    connection=http.client.HTTPSConnection(url.hostname,timeout=300,context=ssl.create_default_context())
    connection.putrequest('POST',url.path+'?'+url.query)
    for key,value in {**headers,'Content-Type':'application/zip','Content-Length':str(total)}.items():connection.putheader(key,value)
    connection.endheaders()
    with archive.open('rb') as source:
        while block:=source.read(1048576):connection.send(block)
    response=connection.getresponse();payload=response.read();connection.close()
    if response.status!=201:raise RuntimeError('Asset upload failed: HTTP '+str(response.status)+' '+payload.decode('utf-8',errors='replace')[:1500])
    asset=json.loads(payload)
    assert asset['size']==total and asset.get('digest')=='sha256:'+expected
    print('Verified original asset published:',asset['browser_download_url'])
