FROM registry.access.redhat.com/ubi9/ubi:latest

COPY requirements.txt /tmp/requirements.txt
COPY quay-demo-publisher.py /usr/local/bin/quay-demo-publisher.py
COPY entrypoint.sh /entrypoint.sh
RUN dnf install -y pip ; pip install -r /tmp/requirements.txt ; rm -fR /root/.cache /var/cache/dnf

ENTRYPOINT ["/entrypoint.sh"]


