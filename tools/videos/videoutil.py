import json
import os
import requests
import sys
import time


def get_current_token():
    if not os.path.isfile('.google_keys.json'):
        print("You need to set up a Google cloud app and store the keys in a file called .google-keys.json in the current directory")
        print("Do NOT commit this file to a git repo, of course!")
        sys.exit(1)

    with open('.google_keys.json') as f:
        g = json.load(f)

    tokenchanged = False
    if os.path.isfile('.google_tokens.json'):
        with open('.google_tokens.json') as f:
            tokens = json.load(f)
            tokenexpires = int(tokens.get('access_token_expires_at', '0'))
            if tokenexpires < time.time():
                print("Token expired, refreshing...")
                r = requests.post(g['installed']['token_uri'], params={
                    'client_id': g['installed']['client_id'],
                    'client_secret': g['installed']['client_secret'],
                    'grant_type': 'refresh_token',
                    'refresh_token': tokens['refresh_token'],
                })
                r.raise_for_status()
                tokens['access_token'] = r.json()['access_token']
                tokens['expires_in'] = r.json()['expires_in']
                tokenchanged = True
    else:
        # No tokens yet, so initiate login
        url = '{}?{}'.format(
            g['installed']['auth_uri'],
            urllib.parse.urlencode({
                'scope': 'https://www.googleapis.com/auth/youtube',
                'response_type': 'code',
                'client_id': g['installed']['client_id'],
                'nonce': 'abc123def',
                'state': 'def456abc',
                'redirect_uri': 'http://localhost:1/oauth_receive',
            }))
        print("Login is needed! Please go to the following URL and grant access!")
        print(url)
        print("Once redirected back, please paste the URL you received here:")
        while True:
            url = input('URL: ')
            if not url:
                continue
            try:
                code = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['code'][0]
                break
            except Exception as e:
                print("Failed to parse: {}".format(e))
        r = requests.post(g['installed']['token_uri'], params={
            'client_id': g['installed']['client_id'],
            'client_secret': g['installed']['client_secret'],
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': 'http://localhost:1/oauth_receive',
        })
        r.raise_for_status()
        tokens = r.json()
        tokenchanged = True
    if tokenchanged:
        tokens['access_token_expires_at'] = time.time() + int(tokens['expires_in'])
        with open('.google_tokens.json', 'w') as f:
            json.dump(tokens, f)

    return tokens['access_token']
