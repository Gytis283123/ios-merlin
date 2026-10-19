#!/usr/bin/env python3
"""Download GitHub Actions kernel artifacts for merlin testing.

Kernel builds need macOS, i.e. GitHub runners (see .github/workflows/xnu.yml
-- it runs when this repo is pushed and its head touches xnu/patches/**).
Until then this downloads the proven ios-sweet kernel (the same generic
arm64 MACHINE_CONFIG=SWEET bring-up merlin boots today).

  fetch-kernel-artifact.py list REPO
  fetch-kernel-artifact.py latest REPO [DESTDIR]      (newest live artifact)
  fetch-kernel-artifact.py get REPO ARTIFACT_ID DESTDIR

Token: $GITHUB_TOKEN if set, else `git credential fill` (non-interactive;
GitHub artifacts need auth even on public repos). On Windows with Git
Credential Manager holding the PAT, the Linux side has no helper: run the
download there instead, e.g. in PowerShell:

  $tok = ("protocol=https`nhost=github.com`n`n" | git credential fill |
          Where-Object { $_ -match '^password=' }).Substring(9)
  curl.exe -L -o kernel.zip -H "Authorization: Bearer $tok" `
    "https://api.github.com/repos/dipa-studio/ios-sweet/actions/artifacts/ID/zip"
"""
import json, os, subprocess, sys, urllib.request

API = 'https://api.github.com'


def token():
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN'].strip()
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')  # fail, don't prompt
    r = subprocess.run(['git', 'credential', 'fill'],
                       input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True, env=env)
    for line in r.stdout.splitlines():
        if line.startswith('password='):
            tok = line[9:].strip()
            if tok:
                print('using git credential ( PAT hidden )', file=sys.stderr)
                return tok
    return None


def fetch(url, tok):
    req = urllib.request.Request(url)
    if tok:
        req.add_header('Authorization', f'Bearer {tok}')
    return urllib.request.urlopen(req)


def list_artifacts(repo, tok):
    d = json.load(fetch(f'{API}/repos/{repo}/actions/artifacts', tok))
    live = [a for a in d['artifacts'] if not a['expired']]
    print(json.dumps(live, indent=2))


def download(repo, art_id, destdir, tok):
    data = fetch(f'{API}/repos/{repo}/actions/artifacts/{art_id}/zip', tok).read()
    os.makedirs(destdir, exist_ok=True)
    dest = os.path.join(destdir, f'artifact-{art_id}.zip')
    open(dest, 'wb').write(data)
    print(f'{dest}: {len(data)} bytes')
    import zipfile
    with zipfile.ZipFile(dest) as z:
        z.extractall(destdir)
        print('extracted to', destdir)
    os.unlink(dest)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, repo = sys.argv[1], sys.argv[2]
    tok = token()
    try:
        if cmd == 'list':
            list_artifacts(repo, tok)
        elif cmd == 'latest':
            d = json.load(fetch(f'{API}/repos/{repo}/actions/artifacts', tok))
            live = [a for a in d['artifacts'] if not a['expired']]
            newest = sorted(live, key=lambda a: a['created_at'])[-1]
            print(f'newest live: {newest["id"]} {newest["name"]} {newest["created_at"]}',
                  file=sys.stderr)
            download(repo, str(newest['id']),
                     sys.argv[3] if len(sys.argv) > 3 else '.', tok)
        elif cmd == 'get':
            download(repo, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else '.', tok)
        else:
            raise SystemExit(__doc__)
    except Exception as e:
        msg = str(e)
        if '401' in msg or '403' in msg or msg == '':
            print(f'error: {e!r} -- no usable GitHub token '
                  '(set GITHUB_TOKEN or run from the Windows side, see docstring)',
                  file=sys.stderr)
        else:
            print(f'error: {e!r}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
