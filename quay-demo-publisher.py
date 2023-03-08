#!/usr/bin/python3

import requests
import json
from random import SystemRandom
import faker
from datetime import datetime
import os
import ldap3
from concurrent.futures import ThreadPoolExecutor, wait
import logging
import sys

faker  = faker.Faker()

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

TOKEN=os.environ.get('QUAY_TOKEN', False)
URI = os.environ.get('QUAY_API', 'https://quay.example.com/api/v1/')
CA = os.environ.get('QUAY_CA', '/etc/ssl/certs/quay.example.com.pem')
ROBOTCOUNT = int(os.environ.get('ROBOTCOUNT', 5))
REPOCOUNT  = int(os.environ.get('REPOCOUNT', 5))
MIRRORCOUNT= int(os.environ.get('MIRRORCOUNT', 25))

if bool(os.environ.get('DEBUG', False)):    logger.setLevel(logging.DEBUG)
if not os.path.isfile(CA):  CA = False
headers = {'Authorization': f"Bearer {TOKEN}"}

try:
    logger.info(f"starting LDAP connection")
    server = ldap3.Server('ldap://ds389.quay.svc:10389', get_info=ldap3.ALL)
    conn = ldap3.Connection(server, 'cn=Directory Manager', 'changeme', auto_bind=True)
    conn.search('ou=People,dc=example,dc=com', '(objectClass=inetuser)', attributes=['cn', 'uid', 'memberOf'])
except Exception as e:
    logger.error(f"cannot fetch LDAP information {e}")
    sys.exit(1)

orgas = set([])

logger.info(f"fetching entries from LDAP")
for e in conn.entries:
    try:
        orgas.add(ldap3.utils.dn.parse_dn(e.memberOf.values[0])[0][1])
    except Exception as err:
        logger.error(f"skipping entry {e}: {err}")

MIRRORIMG = 'quay.io/centos/centos'
try:
    # https://quay.io/v2/centos/centos/tags/list
    logger.info(f"pulling tags for {MIRRORIMG}")
    tags = requests.get(f"https://quay.io/v2/centos/centos/tags/list").json()['tags']
except Exception as e: 
    logger.error(f"cannot pul tags for {MIRRORIMG} {e} skipping mirror")
    MIRRORIMG = False

def create_organization(orga, robot=False):
    global faker, CA, headers, URI
    logger.info(f"requesting organization {orga}")
    rsp = requests.post(f"{URI}organization/", json=dict(name=f"{orga}", email=f"{orga}-admin@example.com"),
                         headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {rsp.status_code}")
    except Exception as e:
        logger.error(f"{e} Organization {orga}")
        return
    if orga == 'mirrors':   
        rsp = requests.put(f"{URI}organization/{orga}/robots/robot-syncer",
                                    headers=headers, verify=CA)
        return
    try:
        logger.info(f"requesting developer group for {orga}")
        rsp = requests.put(f"{URI}organization/{orga}/team/developers", json=dict(role='member', description='developers'),
                        headers=headers, verify=CA)
        try:
            logger.info(f"setting up TeamSync for developers {orga}")
            rsp = requests.post(f"{URI}organization/{orga}/team/developers/syncing", json={'group_dn': f'cn={orga},ou=Groups'},
                        headers=headers, verify=CA)
        except Exception as e:
            logger.error(f"{e} Organization {orga} enabling LDAP sync for developers")
    except Exception as e:
        logger.error(f"{e} Organization {orga} creating Team developers")
    try:
        for _ in range(1, faker.random_int(1,ROBOTCOUNT)):
            logger.info(f"requesting robot for organziation {orga}")
            if robot == False:  name = faker.user_name()
            else:               name = robot
            rsp = requests.put(f"{URI}organization/{orga}/robots/robot-{name}",
                                    headers=headers, verify=CA)
            try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
            except Exception as e:
                logger.error(f"{e} {rsp} {rsp.reason}")
            if robot != False:  break
        for _ in range(1, faker.random_int(1,REPOCOUNT)):
            logger.info(f"requesting repository {_} for {orga}")
            rsp = requests.post(f"{URI}repository", json=dict(repository=f"{faker.user_name()}", visibility='public',
                                    namespace=f"{orga}", repo_kind='image', description=f"repository {orga}-{_}"),
                                    headers=headers, verify=CA)
            try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
            except Exception as e:
                logger.error(f"{e} {rsp} {rsp.reason}")
    except Exception as e:
        logger.error(f"{e} organization {orga}")

def create_mirror(name):
    global faker, CA, headers, URI, MIRRORIMG
    logger.info(f"requesting mirror for repository {name}")
    rsp = requests.post(f"{URI}repository", json=dict(repository=f"{name}", visibility='public',
                                    namespace='mirrors',
                                    repo_kind='image', description=f"mirror repository {name}"),
                                    headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")
    logger.info(f"setting repository {name} state to mirror")
    rsp = requests.put(f"{URI}repository/mirrors/{name}/changestate", json=dict(state='MIRROR'),
                            headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")
    logger.info(f"setting up mirror config repository {name}")
    rsp = requests.post(f"{URI}repository/mirrors/{name}/mirror", json=dict(
                        is_enabled=True, external_reference=MIRRORIMG,
                        sync_interval=(86400 * 7 * 52), sync_start_date=datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                        robot_username='mirrors+robot-syncer', 
                        root_rule=dict(rule_kind='tag_glob_csv', rule_value=[faker.random_element(tags)])),
                                    headers=headers, verify=CA)
    try:    logger.debug (f"{rsp} {json.dumps(rsp.json(), indent=2)}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")
    logger.info(f"starting sync for repository {name} in background")
    rsp = requests.post(f"{URI}repository/mirrors/{name}/mirror/sync-now", headers=headers, verify=CA)
    try:    logger.debug (f"{rsp}")
    except Exception as e:
        logger.error(f"{e} {rsp} {rsp.reason}")

threads = []
for orga in orgas:
    threads.append(ThreadPoolExecutor().submit(create_organization, orga))

wait(threads)
if MIRRORIMG != False:
    create_organization('mirrors', 'syncer')
    threads = []
    for _ in range(10, faker.random_int(10,MIRRORCOUNT)):
        threads.append(ThreadPoolExecutor().submit(create_mirror, faker.user_name()))
    wait(threads)

# if we want to cleanup everything
#for orga in orgas:
#    rsp = requests.delete(f"{URI}repository/{orga}",
#                            headers=headers, verify=CA)
#    try:    print (f"{rsp} {rsp.status_code}")
#    except Exception as e:
#        print(f"{e} {rsp} {rsp.reason}")

