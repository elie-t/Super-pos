from sync.service import _url, _headers
import requests, json
r = requests.get(_url('warehouses_central') + '?order=number.asc',
                 headers={**_headers(), 'Prefer': ''}, timeout=10)
print('status:', r.status_code)
print('URL:', _url('warehouses_central'))
data = r.json()
if data:
    print('columns:', list(data[0].keys()))
    for w in data:
        print(w.get('name'), '|', w.get('default_customer_id'))
