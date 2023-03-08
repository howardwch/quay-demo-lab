#!/bin/bash

echo "$(cat step3-2.ldif)" | oc -n quay exec -ti deploy/ds389 -- ldapmodify -x -H ldap://localhost:10389 -D 'cn=Directory Manager' -w 'changeme'
