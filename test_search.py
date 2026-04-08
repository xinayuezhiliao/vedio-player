import urllib.request
import ssl
import json
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
        data = r.read()
        encoding = 'utf-8'
        for part in ct.split(';'):
            if 'charset' in part:
                encoding = part.split('charset=')[-1].strip()
                break
        return data.decode(encoding, errors='ignore')

# 测试搜索 "狂飙"
keyword = "狂飙"
url = f"https://so.iqiyi.com/so?q=" + urllib.request.quote(keyword)
print("Fetching:", url)
text = fetch(url)
print("Response length:", len(text))
matches = re.findall(r'href="(https://www\.iqiyi\.com/v_[^"]+)"', text)
print("URLs found:", len(set(matches)))
for m in list(set(matches))[:3]:
    print(m)
