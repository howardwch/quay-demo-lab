#!/usr/bin/python3 -Wignore

import requests
import json
from random import SystemRandom
from datetime import datetime
import os
from concurrent.futures import ThreadPoolExecutor, wait
import logging
import sys
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

TOKEN=os.environ.get('QUAY_TOKEN', False)
MIRROR_TOKEN=os.environ.get('MIRROR_TOKEN', False)
URI = os.environ.get('QUAY_API', 'https://quay.example.com/api/v1/')
MIRROR_URI = os.environ.get('MIRROR_API', 'https://quay.ro.example.com/api/v1/')
CA = os.environ.get('QUAY_CA', '/etc/ssl/certs/quay.example.com.pem')
MIRROR_CA = False
MIRROR_INTERVAL = 60

if bool(os.environ.get('DEBUG', False)):    logger.setLevel(logging.DEBUG)
if not os.path.isfile(CA):  CA = False
if not os.path.isfile(MIRROR_CA): MIRROR_CA = False

headers = {'Authorization': f"Bearer {TOKEN}"}
mirror_headers = {'Authorization': f"Bearer {MIRROR_TOKEN}"}

def get_repositories():
    try:
        repos = []
        logger.info(f"requesting repositories")
        page = ''
        while page != None:
            if page != '':  page = f"&next_page={page}"
            rsp = requests.get(f"{URI}repository?public=true{page}",
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

def create_organization(name):
    try:
        rsp = requests.post(f"{MIRROR_URI}organization/", json=dict(name=name, email=f"mirror@{name}"),
                             headers=mirror_headers, verify=MIRROR_CA)
        if rsp.status_code not in (201, 204):
            try:
                if not rsp.json().get('error_message') == 'A user or organization with this name already exists':
                    logger.debug (f"{rsp} {rsp.status_code} {rsp.json()}")
            except Exception as e:  
                logger.error(f"creating Organization failed {e}")
                return False
        try:
            rsp = requests.put(f"{MIRROR_URI}organization/{name}/robots/robot-{name}",
                                    headers=mirror_headers, verify=MIRROR_CA)
            if rsp.status_code not in (200, 204):
                try:    
                    if not rsp.json().get('message').startswith('Existing robot with name'):
                        logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
                except Exception as e:
                    logger.error(f"{e} {rsp} {rsp.reason}")
        except Exception as e:
            logger.error(f"creating Organization robot failed {e}")
            return False
    except Exception as e:
        logger.error(f"creating Organization generic error {e}")
        return False
    return True 

def create_repository(orga, name, description, visibility):
    try:
        if visibility == True:  visibility = 'public'
        else:                   visibility = 'private'
        rsp = requests.post(f"{MIRROR_URI}repository", json=dict(repository=name, visibility=visibility,
                                    namespace=orga, repo_kind='image', description=description),
                                    headers=mirror_headers, verify=MIRROR_CA)
        if rsp.status_code not in (201, 204):
            try:    
                if not rsp.json().get('error_message') == 'Repository already exists':
                    logger.debug (f"{rsp} {rsp.status_code} {rsp.json()}")
            except Exception as e:
                logger.error(f"creating Repository {orga}/{name} failed {e}")
                return False
    except Exception as e:
        logger.error(f"creating Repository generic error {e}")
        return False
    return True


def create_mirror(orga, name):
    try:
        rsp = requests.put(f"{MIRROR_URI}repository/{name}/changestate", json=dict(state='MIRROR'),
                            headers=mirror_headers, verify=MIRROR_CA)
        if rsp.status_code not in (200, 204):
            try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
            except Exception as e:
                logger.error(f"{e} {rsp} {rsp.reason}")
        logger.info(f"setting up mirror config repository {name}")
        rsp = requests.post(f"{MIRROR_URI}repository/{name}/mirror", json=dict(
                            is_enabled=True, external_reference=f"{urlparse(URI).netloc}/{name}",
                            sync_interval=MIRROR_INTERVAL, sync_start_date=datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                            external_registry_username='daniel58', external_registry_password='changeme',
                            robot_username=f"{orga}+robot-{orga}",
                            root_rule=dict(rule_kind='tag_glob_csv', rule_value=['*'])),
                                        headers=mirror_headers, verify=MIRROR_CA)
        if rsp.status_code not in (201, 204, 409):
            try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
            except Exception as e:
                logger.error(f"{e} {rsp} {rsp.reason}")
        logger.info(f"starting sync for repository {name} in background")
        rsp = requests.post(f"{MIRROR_URI}repository/{name}/mirror/sync-now", headers=mirror_headers, verify=MIRROR_CA)
        if rsp.status_code not in (201, 204):
            try:    logger.debug (f"{rsp.json()}")
            except Exception as e:
                logger.error(f"{e} {rsp} {rsp.reason}")
    except Exception as e:
        print(f"creating Mirror generic error {e}")
        return False
    return True

def mirror(repo):
    if create_organization(repo.get('namespace')):
        if create_repository(repo.get('namespace'), repo.get('name'), repo.get('description'), repo.get('is_public')):
            if create_mirror(repo.get('namespace'), f"{repo.get('namespace')}/{repo.get('name')}"):
                logger.info(f"mirror for {repo['namespace']}/{repo['name']} successful")
                return True
    return False

threads = []
for repo in get_repositories():
    threads.append(ThreadPoolExecutor().submit(mirror, repo))

wait(threads)
