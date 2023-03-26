#!/usr/bin/python3

import psycopg2
import sys
import bcrypt
from uuid import uuid4
import string
from random import SystemRandom as Random

random = Random()

try:
    conn = psycopg2.connect("dbname='quay' user='quay' host='postgres' password='changeme'")
except Exception as e:
    print(f"unable to connect to Database {e}")
    sys.exit(1)

cur = conn.cursor()
cur.execute("INSERT INTO public.oauthapplication " + 
            "(client_id, redirect_uri, application_uri, organization_id, name, description, gravatar_email, secure_client_secret, fully_migrated) " +
            f"VALUES (1, '', '', 1, 'SuperAdmin', '', '', '{''.join([random.choice(string.ascii_uppercase + string.digits) for _ in range(40)])}', 't');")

token = ''.join([random.choice(string.ascii_uppercase + string.digits) for _ in range(40)])
etoken = bcrypt.hashpw(token[20:].encode("utf-8"), bcrypt.gensalt())
ntoken = token[:20]

cur.execute("INSERT INTO public.oauthaccesstoken " + 
            "(uuid, application_id, authorized_user_id, scope, token_type, expires_at, data, token_code, token_name) " +
            f"VALUES ('{str(uuid4())}', 1, 1, 'super:user org:admin user:admin user:read repo:create repo:admin repo:write repo:read', " +
            f"'Bearer', '2387-12-15 00:00:00.0', '', '{etoken}', '{ntoken}');")

print(token)

