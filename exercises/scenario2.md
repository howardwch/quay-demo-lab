# Quay Demo Lab exercise 2

Our Quay is up and running working fine. Some users started to report problems fetching random Images. To simplify the scenario we are going to reproduce the issue just with one image and collect the required logs from the Quay system. 

# Requirements

-   The Quay Demo Lab has to be running and working as described in the  [Welcome](quay-demo-lab/README.md)  page.

## prepare step1

- create some custom images as described in the [Welcome](quay-demo-lab#push-and-pull-some-more-images-to-populate-clair-security-reports) page.
- extract the images to a local folder as described in the [Welcome](quay-demo-lab#push-and-pull-some-more-images-to-populate-clair-security-reports) page.

### evaluate the image manifest and image layers
we pick one of the images (in this example **ubi9**) to exercise on. 

 - change to the directory you extracted the image to (default /tmp/ubi9)

    ```
    cd /tmp/ubi9
    ls -l
    total 87932
    -rw-r--r--. 1 root root      226 Mar 18 11:35 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d
    -rw-r--r--. 1 root root 79170714 Mar 18 11:35 2a625e4afab51b49edb0e5f4ff37d8afbb20ec644ed1e68641358a6305557de3
    -rw-r--r--. 1 root root 10841695 Mar 18 11:35 38cac6677f2bc0e4aea0a343f2c25da8ae3a824c3463a071ca7c3f8acbe83bb8
    -rw-r--r--. 1 root root     7772 Mar 18 11:35 5d4b1460bf44aca1ab357655f4e27793cf931aa0138f746939e55e1d497596b7
    -rw-r--r--. 1 root root      176 Mar 18 11:35 805fd7cafdf23b97883e8e7e296ca9f42c5c3518950c0b8b71f4175bc18a9c53
    -rw-r--r--. 1 root root     2215 Mar 18 11:35 81bebee5223318601de68214234f802af77498b62e572bcc04e8352823fa033d
    -rw-r--r--. 1 root root     1240 Mar 18 11:35 manifest.json
    -rw-r--r--. 1 root root       33 Mar 18 11:35 version

	file *
	259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d: gzip compressed data, original size 2048
	2a625e4afab51b49edb0e5f4ff37d8afbb20ec644ed1e68641358a6305557de3: gzip compressed data, original size 219347456
	38cac6677f2bc0e4aea0a343f2c25da8ae3a824c3463a071ca7c3f8acbe83bb8: gzip compressed data, original size 44984832
	5d4b1460bf44aca1ab357655f4e27793cf931aa0138f746939e55e1d497596b7: ASCII text, with very long lines, with no line terminators
	805fd7cafdf23b97883e8e7e296ca9f42c5c3518950c0b8b71f4175bc18a9c53: gzip compressed data, original size 2560
	81bebee5223318601de68214234f802af77498b62e572bcc04e8352823fa033d: gzip compressed data, original size 10240
	manifest.json:                                                    ASCII text, with very long lines, with no line terminators
	version:                                                          ASCII text
    ```

    ```
    NOTE: the tool jq will format and manipulate json data nicely. 
          As alternative you can use "python -m json.tool" instead
    ```
 - review the manifest content which represents the image information and all layers

    ```
    $ python3 -m json.tool manifest.json 
	{
	    "schemaVersion": 2,
	    "mediaType": "application/vnd.oci.image.manifest.v1+json",
	    "config": {
	        "mediaType": "application/vnd.oci.image.config.v1+json",
	        "digest": "sha256:5d4b1460bf44aca1ab357655f4e27793cf931aa0138f746939e55e1d497596b7",
	        "size": 7772
	    },
	    "layers": [
	        {
	            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
	            "digest": "sha256:2a625e4afab51b49edb0e5f4ff37d8afbb20ec644ed1e68641358a6305557de3",
	            "size": 79170714
	        },
	        {
	            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
	            "digest": "sha256:805fd7cafdf23b97883e8e7e296ca9f42c5c3518950c0b8b71f4175bc18a9c53",
	            "size": 176
	        },
	        {
	            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
	            "digest": "sha256:81bebee5223318601de68214234f802af77498b62e572bcc04e8352823fa033d",
	            "size": 2215
	        },
	        {
	            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
	            "digest": "sha256:259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d",
	            "size": 226
	        },
	        {
	            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
	            "digest": "sha256:38cac6677f2bc0e4aea0a343f2c25da8ae3a824c3463a071ca7c3f8acbe83bb8",
	            "size": 10841695
	        }
	    ],
	    "annotations": {
	        "org.opencontainers.image.base.digest": "sha256:784ce67f829ef411aff4142fbb97365dc949ac2b2c887bc9f0cd50575d48dc28",
	        "org.opencontainers.image.base.name": "registry.access.redhat.com/ubi9/ubi:latest"
	    }
	}
    ```

	what we can notice is that we have an OCI image. There are various types which are listed below:
	 - [Docker Image Manifest V2, Schema 1](https://docs.docker.com/registry/spec/manifest-v2-1/)
	 - [Docker Image Manifest V2, Schema 2](https://docs.docker.com/registry/spec/manifest-v2-2/)
	 - [Open Container Initiative (OCI) Specifications](https://github.com/opencontainers/image-spec)

 - verify image size and file system size are equal
   the total size (sum all size attributes) should equal the file system usage.

	```
	cat manifest.json | \
	    python3 -c 'import json,sys; oci = json.loads(sys.stdin.read()); print("%iM" % round((sum(map(lambda x: x["size"], oci["layers"])) + oci["config"]["size"]) / 2**20))'  
	86M 

	du -hsx .
	86M    .
	```

- evaluate the image configuration layer we can see from the initial directory listing that the image layer **5d4b14...96b7** is considered as ASCII layer. So check on the json syntaxed definition of our Dockerfile in the image.

	```
	python3 -m json.tool 5d4b1460bf44aca1ab357655f4e27793cf931aa0138f746939e55e1d497596b7
	{
	    "created": "2023-03-09T08:04:36.956092741Z",
	    "architecture": "amd64",
	    "os": "linux",
	    "config": {
	        "Env": [
	            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
	            "container=oci"
	        ],
	        "Entrypoint": [
	            "/entrypoint.sh"
	        ],
	        "Labels": {
	            "architecture": "x86_64",
	            "build-date": "2023-02-22T09:23:14",
	            "com.redhat.component": "ubi9-container",
	    [.. output omitted ..]
	```

- evaluate the image configuration layer of our entrypoint.sh file we added to the Docker image. We have two candidates of layers from the size point of view bot are ~2/2.5k in size and represent the requirements.txt and the entrypoint.sh file
	
	```
	zcat 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d | head
	
	entrypoint.sh0100755000000000000000000000024114402304216013620 0ustar00rootroot00000000000000#!/bin/bash

	echo | openssl s_client -connect quay.example.com:443 | openssl x509 -out /etc/ssl/certs/quay.example.com.pem
	/usr/local/bin/quay-demo-publisher.py
	```

- now let's try to modify the entrypoint layer to inject a wrong certificate by using a different port

	```
	zcat 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d |\
	    sed -e " s#:443#:1443# " | \
	    gzip -c > 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d.malware
	```

	now replace the original lay with the tampered layer and update the manifest according to the size change (the original size is 226)


	```
	mv 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d.malware 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d
	
	stat 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d
	  File: 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d
	  Size: 220       	Blocks: 8          IO Block: 4096   regular file
      [.. output omitted ..]

	# assuming that the original size is unique
	sed -i -e " s#"size": 226#"size": 220#; ' manifest.json
	```

- now we try uploading this manipulated image

	```
	skopeo copy dir:///tmp/ubi${v} docker://quay.example.com/${USER}/quay-demo-publisher:ubi${v}
	Getting image source signatures
	Copying blob 2a625e4afab5 skipped: already exists  
	Copying blob 805fd7cafdf2 skipped: already exists  
	Copying blob 81bebee52233 skipped: already exists  
	Copying blob 259ad5f5e699 skipped: already exists  
	Copying blob 38cac6677f2b skipped: already exists  
	Copying config 5d4b1460bf done  
	Writing manifest to image destination
	Storing signatures
	```

	so Quay verified that our layers have already been uploaded. Now we have two ways to proceed

#### manipulating the image layer on the storage backend 
first, we need an s3 tool to fetch/push objects (the exercise will utilize MinIOs client but please feel free to use what you prefer)

```
# download the S3 client
curl https://dl.min.io/client/mc/release/linux-amd64/mc \
  --create-dirs \
  -o /usr/bin/mc
chmod +x /usr/bin/mc

# configure the S3 client
mc alias set s3 https://minio.example.com minioadmin minioadmin --api=s3v4 --path=auto
Added `s3` successfully.

# verify that the original blob is available 
mc ls s3/quay/datastorage/registry/sha256/25/259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d

# ensure we have a backup for it 
mc cp s3/quay/datastorage/registry/sha256/25/259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d s3/quay/datastorage/registry/sha256/25/259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d.bkp

# now upload or tempared blob instead of the original
mc cp 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d s3/quay/datastorage/registry/sha256/25/259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d 

# you can verify and already see the size difference in the blob on the storage
mc ls s3/quay/datastorage/registry/sha256/25/
[2023-03-18 12:38:43 CET]   220B STANDARD 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d
[2023-03-18 12:37:51 CET]   226B STANDARD 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d.bkp
```

now with that, we consider a normal user trying to fetch our image with the tampered layer. With caching on podman we utilize skopeo copy instead

```
skopeo copy docker://quay.example.com/${USER}/quay-demo-publisher:ubi${v} dir://tmp/ubi9-tampered
Getting image source signatures
Copying blob 2a625e4afab5 done  
Copying blob 805fd7cafdf2 done  
Copying blob 81bebee52233 done  
Copying blob 259ad5f5e699 [>-------------------------------------] 8.0b / 226.0b
Copying blob 38cac6677f2b done  
FATA[0004] writing blob: happened during read: Digest did not match, expected sha256:259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d, got sha256:3902e0f415fa6b6be5ec98e4c14bb4c4b99cb2498747e6d2067e188c7cd23212 
```
As we can see, skopeo/podman will detect sha256 mismatches and protect users from utilizing tampered images/blobs. 

#### manipulating the image layer due to uploading a tampered layer with the same tag

as preparation for this scenario, you need to delete the existing tag (example ubi9) from your repository as well as all other images referencing the same layer (in our example, the file /entrypoint.sh layer equals between all tags we uploaded so you need to delete all)
You can as well delete the complete repository instead of each individual tag.

```
NOTE: you'll need to wait for Quay's recycling on the blob layers to the storage as well

watch mc ls s3/quay/datastorage/registry/sha256/25/
```

after the blobs have vanished from the storage backend we can upload the image again.

```
skopeo copy dir://tmp/ubi9 docker://quay.example.com/${USER}/quay-demo-publisher:ubi${v} 
Getting image source signatures
Copying blob 2a625e4afab5 done  
Copying blob 805fd7cafdf2 done  
Copying blob 81bebee52233 done  
Copying blob 259ad5f5e699 [====================================>-] 220.0b / 226.0b
Copying blob 38cac6677f2b done  
FATA[0005] writing blob: Patch "https://quay.example.com/v2/daniel58/quay-demo-publisher/blobs/uploads/8ba5bc43-f8f5-45ad-b3a7-291f86334c6b": happened during read: Digest did not match, expected sha256:259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d, got sha256:3902e0f415fa6b6be5ec98e4c14bb4c4b99cb2498747e6d2067e188c7cd23212 
```

as we can see, Quay verifies each layer on it's sha256 sum as well.

##### how to still succeed

the only way to continue in tampering such images is by updating the manifest and applying the values to the tag people are using. So we change the `size` and the `digest` referenced in the manifest

```
python3 -m json.tool manifest.json
{
    "schemaVersion": 2,
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "config": {
[.. output omitted ..]
        {
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": "sha256:3902e0f415fa6b6be5ec98e4c14bb4c4b99cb2498747e6d2067e188c7cd23212",
            "size": 220
        },
[.. output omitted ..]
```

```
# don't forget to rename the blob in the filesystem as well
mv 259ad5f5e699015b2fa35e28f78006a95aebaa905798df509370146ea6917d4d 3902e0f415fa6b6be5ec98e4c14bb4c4b99cb2498747e6d2067e188c7cd23212

skopeo copy dir://tmp/ubi9 docker://quay.example.com/${USER}/quay-demo-publisher:ubi${v} 
Getting image source signatures
Copying blob 2a625e4afab5 skipped: already exists  
Copying blob 805fd7cafdf2 skipped: already exists  
Copying blob 81bebee52233 skipped: already exists  
Copying blob 3902e0f415fa done  
Copying blob 38cac6677f2b skipped: already exists  
Copying config 5d4b1460bf done  
Writing manifest to image destination
Storing signatures
```

Well, if not already clear this is the reason why using `tags` as image reference is not a good idea for highly protected and restricted deployments.

```
NOTE: one should always reference the sh256 sum in configurations to ensure image manipulation is not possible
```

##### example image reference 

- bad examples
    ```
	podman pull quay.example.com/${USER}/quay-demo-publisher:latest
	podman pull quay.example.com/${USER}/quay-demo-publisher:ubi9
	...
	```
- good examples
    ```
    # identify the sha for a valid image
    skopeo inspect podman \
        quay.example.com/${USER}/quay-demo-publisher:ubi9 | jq -r ' .Digest'

	podman pull quay.example.com/${USER}/quay-demo-publisher@sha256:
	...
	```

