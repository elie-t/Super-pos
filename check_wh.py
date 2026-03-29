from sync.service import _url, _headers
import requests
r = requests.get(_url('warehouses_central') + '?order=number.asc',
                 headers={**_headers(), 'Prefer': ''}, timeout=10)
for w in r.json():
    print(w.get('name'), '|', w.get('default_customer_id'))
