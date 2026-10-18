"""
Lists (and with --get, downloads) one SMART-DS folder from the OEDI data lake into ../data/smartds/.
    python fetch_smartds.py <prefix> [--get]
Public bucket, no credentials; only the files under <prefix>.
"""
import os
import re
import sys
import urllib.request

BUCKET = 'https://oedi-data-lake.s3.amazonaws.com'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'data', 'smartds')


def keys(prefix):
    token, found = None, []
    while True:
        url = f'{BUCKET}/?list-type=2&prefix={prefix}' + (f'&continuation-token={urllib.request.quote(token)}' if token else '')
        xml = urllib.request.urlopen(url, timeout=60).read().decode()
        found += [(k, int(s)) for k, s in re.findall(r'<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>', xml)]
        m = re.search(r'<NextContinuationToken>([^<]+)</NextContinuationToken>', xml)
        if not m:
            return found
        token = m.group(1)


if __name__ == '__main__':
    prefix = sys.argv[1]
    files = keys(prefix)
    print(f'{len(files)} files, {sum(s for _, s in files) / 1e6:.2f} MB under {prefix}')
    for k, s in files[:12]:
        print(f'  {s:>10d}  {k[len(prefix):]}')
    if '--get' in sys.argv:
        for k, s in files:
            dest = os.path.join(OUT, *k.split('/'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            urllib.request.urlretrieve(f'{BUCKET}/{k}', dest)
        print('downloaded into', OUT)
