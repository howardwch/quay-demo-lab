#!/bin/bash

echo | openssl s_client -connect quay.example.com:443 | openssl x509 -out /etc/ssl/certs/quay.example.com.pem
/usr/local/bin/quay-demo-publisher.py
