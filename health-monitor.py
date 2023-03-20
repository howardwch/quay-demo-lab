#!/usr/bin/python3 -Wignore

import requests
from time import sleep
from socket import gethostname
from datetime import datetime
import os

def fetch_states(URI):
    data = dict(status_code=200, data=dict(services=dict()))
    for endpoint in ('instance', 'endtoend'):
        try:    rsp = requests.get(f"{URI}/health/{endpoint}", 
                      verify=os.environ.get('CA', False)).json()
        except Exception as e: 
            return data
        data.get('data').get('services').update(rsp.get('data').get('services'))
        if rsp.get('status_code') != 200:   data['status_code'] = rsp.get('status_code')
    return data 

def data_to_metrics(data):
    metrics = 'quay_health_status{%s,status_code="%s"} %i' % (','.join(map(lambda x: 
              f"{x}=\"{data.get('data').get('services').get(x)}\"", data.get('data').get('services'))),
                                        data.get('status_code'), 1)
    return '# HELP quay_health_status health endpoint responses\n' + \
           '# TYPE quay_health_status gauge\n' + metrics + '\n'

if __name__ == '__main__':
    print(f"starting monitoring {os.environ.get('QUAY_HEALTH_URI', 'http://localhost:8080')}" +
          f" reporting at {os.environ.get('QUAY_PROM_URI', 'http://localhost:9091')}")
    while True:
        try:    data = data_to_metrics(fetch_states(os.environ.get('QUAY_HEALTH_URI', 'http://localhost:8080')))
        except Exception as e:
            data = data_to_metrics(dict(data=dict(services={'deadtime':int(time())}), status_code=503))
        try:    
            rsp = requests.post(
                f"{os.environ.get('QUAY_PROM_URI', 'http://localhost:9091')}/metrics/job/quay/host/{os.environ.get('QUAY_HOST', gethostname())}", 
                data=data, verify=os.environ.get('CA', False))
            if rsp.status_code != 200:
                print(f"{datetime.now()} {rsp.status_code} {rsp.text}")
        except Exception as e:  
            pass
        try:
            sleep(int(os.environ.get('INTERVAL', 5)))
        except (KeyboardInterrupt, Exception) as e:
            print(f"shutting down on exception {e}")
            break
