#!/bin/bash

oc -n quay replace -f step3.yml
echo "$(cat step3-1.ldif)" | oc -n quay exec -ti deploy/ds389 -- ldapmodify -x -H ldap://localhost:10389 -D 'cn=Directory Manager' -w 'changeme'
