#!/usr/bin/python3 -Wignore

import requests
import json
from random import SystemRandom
import faker
from datetime import datetime, timedelta
import os
from concurrent.futures import ThreadPoolExecutor, wait
import logging
import sys
import urllib3.util
import base64
import shutil
import jwt
import json
import re
import socket
import subprocess
from collections import Counter

faker  = faker.Faker()

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

TOKEN=os.environ.get('QUAY_TOKEN', False)
URI = os.environ.get('QUAY_API', 'https://quay.example.com/api/v1/')
CA = os.environ.get('QUAY_CA', '/etc/ssl/certs/quay.example.com.pem')
CCA = os.environ.get('CLAIR_CA', '/etc/ssl/certs/clair.example.com.pem')
clair = os.environ.get('CLAIR_API', 'https://clair.example.com')
psk = os.environ.get('PSK', None)
THRESHOLD = int(os.environ.get('THRESHOLD', 25))
MAXTHREADS = int(os.environ.get('MAXTHREADS', 10))

if bool(os.environ.get('DEBUG', False)):    logger.setLevel(logging.DEBUG)
if not os.path.isfile(CA):  CA = False
if not os.path.isfile(CCA): CCA = False
headers = {'Authorization': f"Bearer {TOKEN}"}

def get_repositories(api=None, headers=None, CA=None):
    try:
        repos = []
        logger.info(f"requesting repositories")
        page = ''
        while page != None:
            if page != '':  page = f"&next_page={page}"
            rsp = requests.get(f"{api}repository?public=true&includeTags=true{page}",
                                 headers=headers, verify=CA)
            try:    logger.debug (f"{rsp} {rsp.status_code}")
            except Exception as e:
                logger.error(f"{e}")
                return []
            repos.extend(list(filter(lambda x: x.get('state') != 'MIRROR', rsp.json().get('repositories', []))))
            page = rsp.json().get('next_page')
    except Exception as e:
        logger.error(f"Generic repolist fetch error {e}")
        return []
    logger.debug(f"found {len(repos)} to mirror")
    return repos

def clair_headers(token):
    return {'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer %s' % token}

def sign(psk):
    jwt_psk = base64.b64decode(psk)
    payload = {
        "iss": "quay",
        "exp": datetime.utcnow() + timedelta(minutes=5),
    }
    return jwt.encode(payload, jwt_psk, algorithm='HS256')

def get_repotags(repo=None, latest=False, api=None, headers=None, CA=None):
    tags = []
    try:
        rsp = requests.get(f"{api}repository/{repo}?includeTags=True",headers=headers, verify=CA)
        if rsp.status_code == 200:
            if latest:
                tags = list(map(lambda y: dict(y[1].items()), filter(lambda x: x[1].get('name') == 'latest', rsp.json().get('tags').items())))
            else:
                tags = list(map(lambda y: dict(y[1].items()), rsp.json().get('tags').items()))
        else:
            return tags
    except Exception as e:
        logger.error(f"Generic gettags fetch error {e}")
        return tags
    return tags
    
def vulscore_manifest(clair, psk, manifest):
    try:
        rsp = requests.get(f"{clair}/matcher/api/v1/vulnerability_report/{manifest}", headers=clair_headers(sign(psk)), verify=CCA)
        vulrep = rsp.json()
    except Exception as e:
        logger.error(f"Fetching vulnerability report error {e}")
        return -1
    if rsp.status_code == 200:
        if all([vulrep.get('packages') == {}, vulrep.get('distributions') == {},
                vulrep.get('repository') == {}, vulrep.get('environments') == {},
                vulrep.get('vulnerabilities') == {}, vulrep.get('package_vulnerabilities') == {},
                vulrep.get('enrichments') == {}]):
             return -1
        else: logger.debug(f"difference in empty report")
        vulscore = dict(Counter(list(map(lambda x: vulrep['vulnerabilities'][x].get('normalized_severity'), vulrep.get('vulnerabilities')))))
        if vulscore.get('High', False):     vulscore['High']   *= 3
        if vulscore.get('Medium', False):   vulscore['Medium'] *= 2
    else:
        logger.debug(f"{rsp.status_code} {rsp.text}")
        return -1
    return sum(vulscore.values())

def scan_repository(repo):
    global good_to_mirror, URI, headers, CA
    uri = f"{repo.get('namespace')}/{repo.get('name')}"
    score = list(map(lambda x: (x.get('name'), x.get('manifest_digest'), 
                              vulscore_manifest(clair, psk, x.get('manifest_digest'))), get_repotags(repo=uri, api=URI, headers=headers, CA=CA)))
    if len(score) > 0:
        logger.debug(f"{uri}")
        for tag in score:
            if all([tag[-1] >= THRESHOLD,
                    tag[-1] != -1]):
                if good_to_mirror.get(f"{repo.get('namespace')}/{repo.get('name')}", False):
                    good_to_mirror[f"{repo.get('namespace')}/{repo.get('name')}"]['tags'].append(
                                                                                           dict(tag=tag[0], sha256=tag[1], score=tag[-1]))
                else:
                    good_to_mirror[f"{repo.get('namespace')}/{repo.get('name')}"] = dict(orga=repo.get('namespace'),
                                                                                         repo=repo.get('name'),
                                                                                         tags=[dict(tag=tag[0], sha256=tag[1], score=tag[-1])])



good_to_mirror = {}
repos = get_repositories(api=URI, headers=headers, CA=CA)
threads = []
for repo in repos:
    threads.append(ThreadPoolExecutor(MAXTHREADS).submit(vulscore_manifest, scan_repository(repo)))

wait(threads)

for m in good_to_mirror:
    print(f"{m}")
    for tag in sorted(good_to_mirror[m]['tags'], key=lambda x: x.get('score'), reverse=True):
        print(f"\t{tag.get('score')}\t{tag.get('tag')}({tag.get('sha256')}")

