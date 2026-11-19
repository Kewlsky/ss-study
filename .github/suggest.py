"""Send users' new suggestions to the creator's phone only.

The app saves each suggestion in the Firebase Realtime Database under /suggest (anyone can add one, nobody can read
them there). This runs every 5 minutes (GitHub may start it a few minutes late): it reads the ones not sent yet with the Firebase key (repository secret
FCM_SERVICE_ACCOUNT), pushes each to the creator's private topic (repository secret CREATOR_TOPIC; only the creator's
phone joins it) and marks it sent. The logs of a public repo are public, so they never show a suggestion's text.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push import access_token   # noqa: E402

SCOPES = ' '.join(['https://www.googleapis.com/auth/firebase.messaging', 'https://www.googleapis.com/auth/firebase.database',
                   'https://www.googleapis.com/auth/userinfo.email'])


def call(url, token, method='GET', body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    secret, topic = os.environ.get('FCM_SERVICE_ACCOUNT', ''), os.environ.get('CREATOR_TOPIC', '').strip()
    if not secret or not topic:
        print('not set up yet: the CREATOR_TOPIC secret (or FCM_SERVICE_ACCOUNT) is missing; nothing to do')
        return
    sa = json.loads(secret)
    token = access_token(sa, SCOPES)
    db = 'https://%s-default-rtdb.firebaseio.com' % sa['project_id']
    try:
        all_ = call(db + '/suggest.json', token) or {}
    except urllib.error.HTTPError as e:
        sys.exit('could not read the suggestions: the database answered %s' % e.code)
    new = sorted(((k, v) for k, v in all_.items() if isinstance(v, dict) and not v.get('sent')), key=lambda kv: kv[1].get('at', 0))
    fcm = 'https://fcm.googleapis.com/v1/projects/%s/messages:send' % sa['project_id']
    sent = 0
    for key, s in new:
        data = {'kind': 'suggest', 'id': key, 't': str(s.get('t', ''))[:600], 'at': str(s.get('at', '')),
                'v': str(s.get('v', '')), 'app': 'true' if s.get('app') else 'false'}
        call(fcm, token, 'POST', {'message': {'topic': topic, 'data': data, 'android': {'priority': 'HIGH', 'ttl': '604800s'}}})
        call(db + '/suggest/%s.json' % key, token, 'PATCH', {'sent': int(time.time() * 1000)})
        sent += 1
    print('suggestions: %d new, sent to the creator\'s phone' % sent)


if __name__ == '__main__':
    main()
