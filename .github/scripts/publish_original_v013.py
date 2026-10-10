"""Publish exact approved archives using only the workflow-scoped token."""
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

repository = os.environ['GITHUB_REPOSITORY']
assert repository == 'Jinyi5077/Bridge-Generator-Homework'
token = os.environ['GH_TOKEN']
headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Bridge-Generator-Homework-V013-release'}
api = 'https://api.github.com/repos/' + repository

def request(url, body=None):
    h = dict(headers)
    if body is not None:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)

parts = Path('release-parts')
manifest = json.loads((parts / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['repository'] == repository and manifest['tag'] == 'v0.13.0'
target = manifest['target_commit']
assert len(target) == 40 and all(c in '0123456789abcdef' for c in target)
assert request(api + '/git/commits/' + target)['sha'] == target
expected = {
    'BridgeGenerator_V0.13_Windows.zip': (107577035, '68e790df54955d30c3268ab77aae22199306893f2896e4376debaff9c298a6da'),
    'BridgeGenerator_V0.13_Source.zip': (1236024, 'a7b2570ddba8961383407dfcab453cbbf925453ae4e2a2ce3915a9d9d5c3dc88'),
}
assert {f['filename'] for f in manifest['files']} == set(expected)
with tempfile.TemporaryDirectory(prefix='bridge_v013_release_') as temp:
    archives = []
    for item in manifest['files']:
        size, sha = expected[item['filename']]
        assert item['bytes'] == size and item['sha256'] == sha
        archive = Path(temp) / item['filename']
        digest = hashlib.sha256()
        total = 0
        with archive.open('wb') as dest:
            for part in item['parts']:
                src = parts / part['name']
                assert src.parent == parts
                block = src.read_bytes()
                assert len(block) == part['bytes'] and hashlib.sha256(block).hexdigest() == part['sha256']
                dest.write(block)
                digest.update(block)
                total += len(block)
        assert total == size and digest.hexdigest() == sha
        archives.append((archive, size, sha))
        print('Verified original archive:', item['filename'], size, sha)
    try:
        release = request(api + '/releases/tags/v0.13.0')
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        body = (
            '支持 50～220 m 主跨、2 / 3 / 4 / 6 车道；三车道单幅、四和六车道分离两幅。\n\n'
            '新增三车道布载、跨度匹配及 JTG D60—2015 表 4.3.1-6 的长跨汽车纵向折减；界面、计算书、PPT、CAD 与独立内核同步。\n\n'
            '最终 EXE 的 132＋220＋132 m 三车道算例：默认 0.5 m 网格，约 94.6 s，364 项数值比较一致、六项验算判断一致，生成 3 张经 ODA 回转校验的 DWG、29 页 PDF、23 页可编辑 PPT。\n\n'
            '**该初选算例抗弯、抗剪、抗裂和使用阶段压应力未通过；挠度与简化施工阶段压应力通过。状态 COURSE_SCOPE_FAILED / NEEDS_REVIEW。数值一致不表示方案满足限值。**\n\n'
            '69 项唯一测试最终验证通过；完整记录为 68 通过、1 项旧公式文字断言失败，更新断言后单项复跑通过，CAD 调整后 4 项复跑通过，原始日志保留。\n\n'
            'DOCX 含 63 个 MathType OLE 公式并核对宋体 / Times New Roman 元数据；未使用 Word 渲染检查 DOCX 分页。\n\n'
            'Windows ZIP 已包含 Python 与计算库；生成 DWG 需接收方自行安装 ODA File Converter。无新增商业结构软件依赖。\n\n'
            '模型限于课程纵向平面梁、等效预应力和简化施工；全过程施工继承、空间、横向、局部与下部结构未完成。详细算法、运行证据及 35 个代表成果见 main。\n\n'
            '两个下载文件均为本机已验收 ZIP 的原始字节，上传分段后逐段及整体校验合并，未重编译或重打包。\n\n'
            + '\n'.join('- `' + name + '` SHA-256: `' + value[1] + '`' for name, value in expected.items())
        )
        release = request(api + '/releases', dict(tag_name='v0.13.0', target_commitish=target,
            name='V0.13 三车道与220 m连续箱梁课程设计生成器', body=body, draft=False, prerelease=False))
    assert not release['draft'] and not release['prerelease']
    ref = request(api + '/git/ref/tags/v0.13.0')['object']
    while ref['type'] == 'tag':
        ref = request(api + '/git/tags/' + ref['sha'])['object']
    assert ref['type'] == 'commit' and ref['sha'] == target
    for archive, size, sha in archives:
        existing = [a for a in release.get('assets', []) if a['name'] == archive.name]
        if existing:
            assert len(existing) == 1 and existing[0]['state'] == 'uploaded'
            assert existing[0]['size'] == size and existing[0].get('digest') == 'sha256:' + sha
            print('Exact asset already published:', existing[0]['browser_download_url'])
            continue
        url = urllib.parse.urlsplit(release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(archive.name))
        assert url.hostname == 'uploads.github.com'
        connection = http.client.HTTPSConnection(url.hostname, timeout=300, context=ssl.create_default_context())
        connection.putrequest('POST', url.path + '?' + url.query)
        for key, value in {**headers, 'Content-Type': 'application/zip', 'Content-Length': str(size)}.items():
            connection.putheader(key, value)
        connection.endheaders()
        with archive.open('rb') as source:
            while block := source.read(1048576):
                connection.send(block)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        if response.status != 201:
            raise RuntimeError('Asset upload failed: HTTP ' + str(response.status) + ' ' + payload.decode('utf-8', errors='replace')[:1500])
        asset = json.loads(payload)
        assert asset['state'] == 'uploaded' and asset['size'] == size and asset.get('digest') == 'sha256:' + sha
        print('Verified asset published:', asset['browser_download_url'])
    print('Release published:', release['html_url'])
