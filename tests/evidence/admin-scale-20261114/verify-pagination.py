import json
import os
import time
import urllib.error
import urllib.request
import http.cookiejar

base = os.environ.get('SCALE_API_URL', 'http://127.0.0.1:8007')
records = []

def session(username=None, password=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    if username:
        request = urllib.request.Request(base + '/api/auth/login', data=json.dumps(dict(username=username, password=password)).encode(), headers={'Content-Type':'application/json'})
        assert opener.open(request).status == 200
    return opener

def get(opener, endpoint, expected=200):
    start = time.perf_counter()
    try:
        response = opener.open(base + endpoint)
    except urllib.error.HTTPError as error:
        response = error
    payload = response.read()
    assert response.status == expected, (endpoint, response.status, payload[:300])
    records.append(dict(endpoint=endpoint, status=response.status, milliseconds=round((time.perf_counter()-start)*1000, 1), bytes=len(payload)))
    return json.loads(payload)

admin = session('admin', 'admin123')
teacher = session('user', 'user123')
anonymous = session()
paths = ['/api/cases/admin/queue?queue=review', '/api/cases/admin/queue?queue=published', '/api/admin/material-candidates?status=candidate', '/api/admin/skills/versions?status=all']
for path in paths:
    seen = set()
    for page in (1, 250, 500):
        body = get(admin, path + f'&page={page}&pageSize=20')
        assert body['total'] == 10000 and len(body['items']) == 20
        ids = [r['versions'][0]['id'] if 'versions' in r else r['id'] for r in body['items']]
        assert ids == sorted(ids, reverse=True) and not seen.intersection(ids)
        seen.update(ids)
        assert '"document"' not in json.dumps(body) and '"files"' not in json.dumps(body)
    assert len(get(admin, path + '&pageSize=50')['items']) == 50
    assert get(admin, path + '&page=501')['items'] == []
    assert get(admin, path + '&q=%5B%E4%B8%93%E9%A2%98%5D')['total'] == 100
    assert get(admin, path + '&q=NOTFOUND')['total'] == 0
    assert get(admin, path + '&q=.*')['total'] == 0
    get(admin, path + '&page=0', 422)
    get(admin, path + '&pageSize=10000', 422)
    get(teacher, path, 403)
    get(anonymous, path, 401)
assert get(admin, '/api/admin/skills/versions?status=published')['total'] == 500
assert get(admin, '/api/admin/skills/versions?status=unpublished')['total'] == 9500
assert get(admin, '/api/admin/material-candidates?status=approved')['total'] == 0
print(json.dumps(dict(result='passed', dependency='real MongoDB replica set; isolated synthetic database; actual HTTP authentication and routes', checks=records), ensure_ascii=False, indent=2))
