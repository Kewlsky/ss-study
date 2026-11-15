"""Push messages added in the last 15 minutes (and a ringtone changed in that time) to the Firebase topic "all".

Phones ignore a message they already showed (by its id), so sending one twice is harmless: this runs on every push to
the repo, including content updates. Uses only the standard library and openssl (on GitHub's Ubuntu runners).
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

WINDOW = 15 * 60


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def access_token(sa):
    now = int(time.time())
    head = b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())
    claims = b64(json.dumps({'iss': sa['client_email'], 'scope': 'https://www.googleapis.com/auth/firebase.messaging',
                             'aud': sa.get('token_uri', 'https://oauth2.googleapis.com/token'), 'iat': now, 'exp': now + 3600}).encode())
    with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as k:
        k.write(sa['private_key'])
    try:
        sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', k.name], input=(head + '.' + claims).encode(),
                             capture_output=True, check=True).stdout
    finally:
        os.remove(k.name)
    body = urllib.parse.urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                   'assertion': head + '.' + claims + '.' + b64(sig)}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(sa.get('token_uri', 'https://oauth2.googleapis.com/token'), data=body)))['access_token']


def recent(stamp):
    try:
        return 0 <= time.time() - int(stamp) <= WINDOW
    except (TypeError, ValueError):
        return False


def main():
    msgs = json.load(open('messages.json', encoding='utf-8')) if os.path.exists('messages.json') else []
    ring = json.load(open('ring.json', encoding='utf-8')) if os.path.exists('ring.json') else {}
    out = [{'kind': 'msg', **{k: str(m[k]) for k in ('id', 'title', 'text', 'until', 'date') if m.get(k)}}
           for m in msgs if isinstance(m, dict) and recent(str(m.get('id', ''))[1:])]
    if recent(ring.get('v')):
        out.append({'kind': 'ring', 'v': str(ring.get('v'))})
    secret = os.environ.get('FCM_SERVICE_ACCOUNT', '')
    if not secret:
        sys.exit('the FCM_SERVICE_ACCOUNT secret is missing (repo Settings > Secrets and variables > Actions)')
    sa = json.loads(secret)
    token = access_token(sa)
    url = 'https://fcm.googleapis.com/v1/projects/%s/messages:send' % sa['project_id']
    if not out:   # nothing to send: still check the key works, with a dry run Firebase doesn't deliver
        dry = {'validate_only': True, 'message': {'topic': 'all', 'data': {'kind': 'check'}}}
        req = urllib.request.Request(url, data=json.dumps(dry).encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        print('nothing new to push; Firebase key OK (dry run)', urllib.request.urlopen(req).status)
        return
    for data in out:
        msg = {'message': {'topic': 'all', 'data': data,
                           'android': {'priority': 'HIGH' if data['kind'] == 'msg' else 'NORMAL', 'ttl': '86400s'}}}
        req = urllib.request.Request(url, data=json.dumps(msg).encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        print('pushed', data['kind'], data.get('id') or data.get('v'), urllib.request.urlopen(req).status)


if __name__ == '__main__':
    main()
