#!/usr/bin/env python3
"""Query GitHub Actions runs/artifacts for the ios-sweet fork.

Uses $GITHUB_TOKEN if set, else `git credential fill` (Git Credential
Manager on this Windows host).  Read-only: GET requests only.

  gh-ci.py runs [REPO] [COUNT]          recent workflow runs
  gh-ci.py artifacts [REPO] [COUNT]     live artifacts
  gh-ci.py dispatch REPO REF           POST workflow_dispatch for xnu.yml
  gh-ci.py job REPO RUN_ID             job list + status for a run
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = 'https://api.github.com'


def token():
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN'].strip()
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    r = subprocess.run(['git', 'credential', 'fill'],
                       input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True, env=env)
    for line in r.stdout.splitlines():
        if line.startswith('password='):
            return line[9:].strip()
    return None


def req(url, tok, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Accept', 'application/vnd.github+json')
    if tok:
        r.add_header('Authorization', f'Bearer {tok}')
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, repo = sys.argv[1], sys.argv[2]
    tok = token()
    if cmd == 'runs':
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
        st, d = req(f'{API}/repos/{repo}/actions/runs?per_page={n}', tok)
        if st != 200:
            raise SystemExit(f'HTTP {st}: {d}')
        for run in d['workflow_runs']:
            print(f"{run['id']}  {run['name']}  {run['head_branch']}  "
                  f"{run['status']}/{run['conclusion']}  {run['created_at']}  "
                  f"sha={run['head_sha'][:8]}  {run['html_url']}")
    elif cmd == 'artifacts':
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        st, d = req(f'{API}/repos/{repo}/actions/artifacts?per_page={n}', tok)
        if st != 200:
            raise SystemExit(f'HTTP {st}: {d}')
        for a in d['artifacts']:
            print(f"{a['id']}  {a['name']}  {a['created_at']}  "
                  f"expired={a['expired']}  size={a['size_in_bytes']}")
    elif cmd == 'dispatch':
        ref = sys.argv[3]
        st, d = req(f'{API}/repos/{repo}/actions/workflows/xnu.yml/dispatches',
                    tok, 'POST', {'ref': ref})
        print('HTTP', st, d if d else '')
    elif cmd == 'job':
        run_id = sys.argv[3]
        st, d = req(f'{API}/repos/{repo}/actions/runs/{run_id}/jobs', tok)
        if st != 200:
            raise SystemExit(f'HTTP {st}: {d}')
        for j in d['jobs']:
            print(f"{j['name']}  {j['status']}/{j['conclusion']}  "
                  f"started={j['started_at']}  {j['html_url']}")
            for s in j['steps']:
                print(f"   - {s['name']}: {s['status']}/{s['conclusion']}")
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
