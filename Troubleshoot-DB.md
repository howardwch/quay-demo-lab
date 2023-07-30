# Quay Database queries for identifying issues

**NOTE** These queries are not supported by Red Hat and are intend to only `SELECT` and **not** modify any content in the DB.


### Quay identify images not being able to be scanned by Clair

typically, when having issues with layers not downloaded and mirror from a remote registry you can get a list of repositories and images like follows

```
quay=# SELECT DISTINCT repository.name, public.user.username FROM manifestsecuritystatus 
       LEFT JOIN repository ON manifestsecuritystatus.repository_id = repository.id 
       LEFT JOIN public.user ON public.user.id = repository.namespace_user_id 
       WHERE manifestsecuritystatus.index_status = -2;
             name             |  username  
------------------------------+------------
 grafana                      | grafana
 vault-k8s                    | hashicorp
 rhceph-haproxy-rhel9         | rhceph
 almalinux                    | almalinux
 rhceph-promtail-rhel9        | rhceph
 ose-prometheus               | openshift4
 node                         | kindest
 nginx                        | nginx
 ose-prometheus-node-exporter | openshift4
 vault                        | hashicorp
 postgresql-10                | rhel8
 snmp-notifier-rhel9          | rhceph
 quay-rhel8                   | quay
 redhat-operator-index        | redhat
 ose-prometheus-alertmanager  | openshift4
 rhceph-6-dashboard-rhel9     | rhceph
 support-tools                | rhel8
 python-39                    | ubi9
 certified-operator-index     | redhat
 python-39                    | ubi8
 pgadmin4                     | dpage
 rhceph-6-rhel9               | rhceph
(22 rows)
``` 

to cleanup those you can use the UI and remove those repositories accordingly.
As example we pick the image `almalinux/almalinux` to fix by first downloading it locally from the source

```
$ skopeo copy docker://docker.io/almalinux/almalinux dir://tmp/image
Getting image source signatures
Copying blob ba2c2d4a4d0c done  
Copying config afb2ada19d done  
Writing manifest to image destination
Storing signatures
```

now with any S3 client (we'll use mcli here) we can check each layer if present and if not upload it accordingly

```
for layer in $(ls /tmp/image/* | egrep -v '(json|version)' ) ; do 
    echo "checking layer ${layer}"
    blob=$(basename ${layer})
    blobdir=${blob:0:2}
    mcli stat quay/quay-registry/datastorage/registry/sha256/${blobdir}/${blob} || \
    mcli cp ${layer} quay/quay-registry/datastorage/registry/sha256/${blobdir}/${blob}
done
```

you should now be able to scan the image through Clair again ...


### getting a missing layer from a sha digest 

check your Quay logs to retrieve either the manifest or each individual blob missing from your Storage. 
The retrieved values can be queried (read-only) from the Database to retrieve the related organization|user and repository name.

#### getting the manifest sha 
```
quay=# SELECT DISTINCT public.user.username AS organization, repository.name AS repository FROM manifest
       LEFT JOIN repository ON manifest.repository_id = repository.id 
       LEFT JOIN public.user ON public.user.id = repository.namespace_user_id 
       WHERE manifest.digest = 'sha256:b79724759c7%';
```
#### getting any layer from the manifest
```
quay=# SELECT DISTINCT public.user.username AS organization, repository.name AS repository FROM manifest
       LEFT JOIN repository ON manifest.repository_id = repository.id 
       LEFT JOIN public.user ON public.user.id = repository.namespace_user_id 
       WHERE manifest.manifest_bytes LIKE '%sha256:ba958a445f%';
```

#### python scripted 

```
oc -n quay exec -ti deploy/quay -- python 
import psycopg3 
db = psycopg2.connect('host=postgres dbname=quay user=quay password=changeme')
cur = db.cursor()
cur.execute("SELECT DISTINCT public.user.username AS organization, repository.name AS repository FROM manifest LEFT JOIN repository ON manifest.repository_id = repository.id LEFT JOIN public.user ON public.user.id = repository.namespace_user_id WHERE manifest.manifest_bytes LIKE '%sha256:ba958a445f%';")
for image in cur.fetchall():
        print("${registry}/" + f"{image[0]}/{image[1]}")

cur.close()
[CTRL+D]
${registry}/rhceph/rhceph-6-dashboard-rhel9
${registry}/rhceph/rhceph-6-rhel9
${registry}/rhceph/rhceph-haproxy-rhel9
${registry}/rhceph/rhceph-promtail-rhel9
${registry}/rhceph/snmp-notifier-rhel9
```

#### filling the void

with the list of broken images retrieved you can `backfill` the missing layers if you have the source available (that part is not stored in Quay at all)
in the example we have missing layers in the Red Hat Ceph Storage images retrieved from the Registry `registry.redhat.io` 

```
export registry=registry.redhat.io
export IMAGE=${registry}/rhceph/rhceph-6-dashboard-rhel9

skopeo copy docker://${1} dir://tmp/image
for layer in $(ls /tmp/image/* | egrep -v '(json|version|signature)' ) ; do
    echo "checking layer ${layer}"
    blob=$(basename ${layer})
    blobdir=${blob:0:2}
    for storage in quay quaya ; do
        mcli stat ${storage}/quay-registry/datastorage/registry/sha256/${blobdir}/${blob} || \
            mcli cp ${layer} ${storage}/quay-registry/datastorage/registry/sha256/${blobdir}/${blob}
    done
done
```

