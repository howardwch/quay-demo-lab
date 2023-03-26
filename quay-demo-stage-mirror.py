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
MTOKEN=os.environ.get('MIRROR_TOKEN', False)
URI = os.environ.get('QUAY_API', 'https://quay.example.com/api/v1/')
MURI = os.environ.get('MIRROR_API', 'https://quay.example.com/api/v1/')
CA = os.environ.get('QUAY_CA', '/etc/ssl/certs/quay.example.com.pem')
MCA = os.environ.get('MIRROR_CA', '/etc/ssl/certs/quay.example.com.pem')
CCA = os.environ.get('CLAIR_CA', '/etc/ssl/certs/clair.example.com.pem')
clair = os.environ.get('CLAIR_API', 'https://clair.example.com')
psk = os.environ.get('PSK', None)
THRESHOLD = int(os.environ.get('THRESHOLD', 25))
MAXTHREADS = int(os.environ.get('MAXTHREADS', 10))

if bool(os.environ.get('DEBUG', False)):    logger.setLevel(logging.DEBUG)
if not os.path.isfile(CA):  CA = False
if not os.path.isfile(CCA): CCA = False
if not os.path.isfile(MCA): MCA = False
if psk == None:
    print(f"cannot scan Clair without a PSK")
    sys.exit(1)

headers = {'Authorization': f"Bearer {TOKEN}"}
mheaders = {'Authorization': f"Bearer {MTOKEN}"}

def get_repositories(api=None, headers=None, CA=None):
    try:
        repos = []
        logger.debug(f"requesting repositories for {api}")
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

def get_organizations(repos=None):
    return set(map(lambda x: x.get('namespace'), repos))

def get_orga_robot(orga=None, api=None, headers=None, CA=None):
    global robots
    try:
        rsp = requests.get(f"{api}organization/{orga}/robots?token=true", 
                            headers=headers, verify=CA)
        if rsp.status_code == 200:
            try:
                if len(rsp.json().get('robots')) > 1:
                    # if we need to select a specific one in the future
                    r = rsp.json().get('robots')[0]
                else:
                    r = rsp.json().get('robots')[0]
                robots[orga] = dict(name=r.get('name'), token=r.get('token'))
            except IndexError:  return False
    except Exception as e:
        logger.error(f"Generic getrobot fetch error {e}")
        return False
    return True

def get_orga_mrobot(orga=None, api=None, headers=None, CA=None):
    global mrobots
    try:
        rsp = requests.get(f"{api}organization/{orga}/robots?token=true",
                            headers=headers, verify=CA)
        if rsp.status_code == 200:
            try:
                if len(rsp.json().get('robots')) > 1:
                    # if we need to select a specific one in the future
                    r = rsp.json().get('robots')[0]
                else:
                    r = rsp.json().get('robots')[0]
                mrobots[orga] = dict(name=r.get('name'), token=r.get('token'))
            except IndexError:  return False
    except Exception as e:
        logger.error(f"Generic getrobot fetch error {e}")
        return False
    return True


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
        return (-1, {})
    if rsp.status_code == 200:
        if all([vulrep.get('packages') == {}, vulrep.get('distributions') == {},
                vulrep.get('repository') == {}, vulrep.get('environments') == {},
                vulrep.get('vulnerabilities') == {}, vulrep.get('package_vulnerabilities') == {},
                vulrep.get('enrichments') == {}]):
             return (-1, {})
        vulscore = dict(Counter(list(map(lambda x: vulrep['vulnerabilities'][x].get('normalized_severity'), vulrep.get('vulnerabilities')))))
        vulscore['packages'] = sum(map(lambda x: len(vulrep.get('package_vulnerabilities')[x]), vulrep.get('package_vulnerabilities')))
        if vulscore.get('Critical', False): vulscore['Critical'] *= 5
        if vulscore.get('High', False):     vulscore['High']     *= 3
        if vulscore.get('Medium', False):   vulscore['Medium']   *= 2
    else:
        logger.debug(f"{rsp.status_code} {rsp.text}")
        return (-1, {})
    return (sum(vulscore.values()), vulscore)

def scan_repository(repo):
    global good_to_mirror, URI, headers, CA
    uri = f"{repo.get('namespace')}/{repo.get('name')}"
    score = list(map(lambda x: (x.get('name'), x.get('manifest_digest'), 
                              vulscore_manifest(clair, psk, x.get('manifest_digest'))), get_repotags(repo=uri, api=URI, headers=headers, CA=CA)))
    if len(score) > 0:
        logger.info(f"mirroring {uri}")
        for tag in score:
            if all([tag[-1][0] <= THRESHOLD,
                    tag[-1] != -1]):
                if good_to_mirror.get(f"{repo.get('namespace')}/{repo.get('name')}", False):
                    good_to_mirror[f"{repo.get('namespace')}/{repo.get('name')}"]['tags'].append(
                                                                                           dict(tag=tag[0], sha256=tag[1], score=tag[-1]))
                else:
                    good_to_mirror[f"{repo.get('namespace')}/{repo.get('name')}"] = dict(orga=repo.get('namespace'),
                                                                                         repo=repo.get('name'),
                                                                                         tags=[dict(tag=tag[0], sha256=tag[1], score=tag[-1])])
    else:
        logger.info(f"skipping {uri} {score[-1]}")

def mirror_repo(source=None, repo=None, tags=[], robot=None, creds=None, api=None, headers=None, CA=None):
    logger.info(f"setting repository {repo.get('namespace')}/{repo.get('name')} state to mirror")
    rsp = requests.put(f"{api}repository/{repo.get('namespace')}/{repo.get('name')}/changestate", json=dict(state='MIRROR'),
                            headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")
    logger.info(f"setting up mirror config repository {repo.get('namespace')}/{repo.get('name')}")
    rsp = requests.post(f"{api}repository/{repo.get('namespace')}/{repo.get('name')}/mirror", json=dict(
                        is_enabled=False, external_reference=f"{source}/{repo.get('namespace')}/{repo.get('name')}",
                        sync_interval=1, sync_start_date=datetime(2999,12,31,23,59,59).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        robot_username=robot.get('name'),
                        external_registry_username=creds.get('name'), external_registry_password=creds.get('token'),
                        root_rule=dict(rule_kind='tag_glob_csv', rule_value=tags)),
                        headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")
    logger.info(f"starting sync for repository {repo.get('namespace')}/{repo.get('name')} in background")
    rsp = requests.post(f"{URI}repository/{repo.get('namespace')}/{repo.get('name')}/mirror/sync-now", headers=headers, verify=CA)
    try:    logger.debug (f"{rsp}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")

def copy_repo(robots, mrobots):
    global good_to_mirror
    for m in good_to_mirror:
        mm = good_to_mirror[m]
        uri = urllib3.util.parse_url(URI)
        muri = urllib3.util.parse_url(MURI)
        for ref in mm.get('tags'):
            logger.debug(f"getting {mm.get('orga')} robot")
            try: robot = robots.get(mm.get('orga'), False)
            except: robot = ''
            try: srobot = mrobots.get(mm.get('orga'), False)
            except: srobot = ''
            logger.debug(f"stage robot {robot.get('name')} {robot.get('token')[:5]} prod robot {srobot.get('name')} {srobot.get('token')[:5]}")
            try: 
                options = ''
                if CA == False: options = '--src-tls-verify=0 '
                if MCA == False: options += '--dest-tls-verify=0'
                if options != '':   loptions = '--tls-verify=0'
                logger.info(f"syncing {uri.host}/{mm.get('orga')}/{mm.get('repo')}@{ref.get('sha256')} ({ref.get('tag')}) {ref.get('score')}")
                log = subprocess.run(['skopeo', 'login', loptions, '-u', robot.get('name'), '-p', robot.get('token'), uri.host], 
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.debug(log.stdout)
                log = subprocess.run(['skopeo', 'login', '-u', srobot.get('name'), '-p', srobot.get('token'), muri.host], 
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.debug(log.stdout)
                log = subprocess.run(['skopeo', 'copy', options,
                                        f"docker://{uri.host}/{mm.get('orga')}/{mm.get('repo')}@{ref.get('sha256')}",
                                        f"docker://{muri.host}/{mm.get('orga')}/{mm.get('repo')}:{ref.get('tag')}"], 
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.debug(log.stdout)
            except Exception as e: logger.error(f"{e}")

good_to_mirror = {}
repos = get_repositories(api=URI, headers=headers, CA=CA)
logger.info(f"checking {len(repos)} for repositories to mirror")
orgas = get_organizations(repos=repos)
orgas = ['library']
robots = {}
threads = []
for orga in orgas:
    threads.append(ThreadPoolExecutor(MAXTHREADS).submit(get_orga_robot, orga, URI, headers, CA))

wait(threads)
threads = []
for orga in robots.keys():
    for repo in filter(lambda x: x.get('namespace') == orga, repos):
        threads.append(ThreadPoolExecutor(MAXTHREADS).submit(vulscore_manifest, scan_repository(repo)))

wait(threads)

mrepos = get_repositories(api=MURI, headers=mheaders, CA=MCA)
morgas = get_organizations(repos=mrepos)
morgas = ['library']
mrobots = {}
threads = []
for repo in mrepos:
    #if good_to_mirror.get(f"{repo.get('namespace')}/{repo.get('name')}", False):
    if repo.get('namespace') in orgas:
        logger.info(f"starting mirror for {repo.get('namespace')}/{repo.get('name')}")
        threads.append(ThreadPoolExecutor(MAXTHREADS).submit(get_orga_mrobot, repo.get('namespace'), MURI, mheaders, MCA))
wait(threads)

copy_repo(robots, mrobots)
sys.exit(0)

mrepos = get_repositories(api=MURI, headers=mheaders, CA=MCA)
morgas = get_organizations(repos=mrepos, api=MURI, headers=mheaders, CA=MCA)
mrobots = {}
threads = []
for repo in mrepos:
    if good_to_mirror.get(f"{repo.get('namespace')}/{repo.get('name')}", False):
        logger.info(f"spinning of {repo.get('namespace')}/{repo.get('name')}")
        threads.append(ThreadPoolExecutor(MAXTHREADS).submit(get_orga_robot, repo.get('namespace'), MURI, headers, MCA))

wait(threads)
for orga in mrobots.keys():
    for repo in filter(lambda x: x.get('namespace') == orga, mrepos):
        logger.info(f"checking {repo}")
        try: 
            srobot = robots.get(orga, False)
            if srobot == False: raise IndexError
        except IndexError:  
            logger.info(f"ignoring {repo} because no robot")
            continue
        logger.info(f"mirroring {repo}")
        threads.append(ThreadPoolExecutor(MAXTHREADS).submit(mirror_repo, 
            urllib3.util.parse_url(URI)._replace(path='').url, repo, 
                good_to_mirror[f"{repo.get('namespace')}/{repo.get('name')}"]['tags'], robots[orga], srobot, MURI, mheaders, MCA))

wait(threads)


