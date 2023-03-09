#!/bin/bash

cd exercises/scenario1
DN=$(oc -n quay exec -ti deploy/ds389 -- ldapsearch -x -H ldap://localhost:10389 -D 'cn=Directory Manager' -w 'changeme' uid=${USER} -LLL | \
  	 egrep -e '^dn:' | cut -f2 -d':')
echo "dn: ${DN}" > step3-2.ldif 
cat step3-2-template.ldif >> step3-2.ldif
echo "$(cat step3-2.ldif)" | oc -n quay exec -ti deploy/ds389 -- ldapmodify -x -H ldap://localhost:10389 -D 'cn=Directory Manager' -w 'changeme'
cd -
