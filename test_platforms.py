import urllib.request
import ssl
import re
import sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url, headers=None, timeout=8):
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        ct = r.headers.get('Content-Type', '')
        enc = 'utf-8'
        for p in ct.split(';'):
            if 'charset' in p:
                enc = p.split('charset=')[-1].strip()
                break
        return r.read().decode(enc, errors='ignore')

tests = [
    ('腾讯视频', 'https://v.qq.com/x/search/?q=%E7%8B%82%E9%A3%99&c=news'),
    ('芒果TV', 'https://so.mgtv.com/list?k=%E7%8B%82%E9%A3%99'),
]

for name, url in tests:
    print(f'\n=== {name} ===')
    try:
        text = fetch(url)
        print(f'Response length: {len(text)}')
        if 'iqiyi' in name.lower():
            m = re.findall(r'href="(https://www\.iqiyi\.com/v_[^"]+)"', text)
        elif 'tencent' in name.lower() or 'qq' in name.lower():
            m = re.findall(r'href="(/cover/[^?"]+)"[^>]*>([^<]{5,60})<', text)
            m = [(t.strip(), 'https://v.qq.com'+u) for u,t in m if t.strip()]
        elif 'mango' in name.lower():
            m = re.findall(r'href="(https://www\.mgtv\.com/b/[^?"]+)"[^>]*>([^<]{5,50})<', text)
            m = [(t.strip(), u) for u,t in m if t.strip()]
        else:
            m = []
        seen = list(dict.fromkeys(m))[:5]
        for title, link in seen:
            print(f'  {title} | {link}')
    except Exception as e:
        print(f'Error: {e}')
