#!/bin/bash

if [ "${QUAY_API:-False}" != "False" ] ; then
	uri=$(python3 -c "import urllib3.util, os; print(urllib3.util.parse_url(os.environ['QUAY_API']).netloc)")
 	echo | openssl s_client -connect ${uri}:443 | openssl x509 -out /etc/ssl/certs/${uri}.pem
        mkdir -p /etc/docker/certs.d/${uri}
        cp /etc/ssl/certs/${uri}.pem /etc/docker/certs.d/${uri}/service-ca.crt
fi
if [ "${MIRROR_API:-False}" != "False" ] ; then
	uri=$(python3 -c "import urllib3.util, os; print(urllib3.util.parse_url(os.environ['MIRROR_API']).netloc)")
	echo | openssl s_client -connect ${uri}:443 | openssl x509 -out /etc/ssl/certs/${uri}.pem
        mkdir -p /etc/docker/certs.d/${uri}
        cp /etc/ssl/certs/${uri}.pem /etc/docker/certs.d/${uri}/service-ca.crt
fi
if [ "${CLAIR_API:-False}" != "False" ] ; then
        uri=$(python3 -c "import urllib3.util, os; print(urllib3.util.parse_url(os.environ['CLAIR_API']).netloc)")
        echo | openssl s_client -connect ${uri}:443 | openssl x509 -out /etc/ssl/certs/${uri}.pem
fi

case $1 in 
	mirror )
		/usr/local/bin/quay-demo-stage-mirror.py
		;;
	vulscore )
		/usr/local/bin/quay-demo-vulscore-images.py
		;;
	debug )
		/bin/bash
		;;
	* )
		/usr/local/bin/quay-demo-publisher.py
		;;
esac
