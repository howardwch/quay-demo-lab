# Network troubleshooting scenario

## exercise failing Postgresql Database

In failure scenarios related to the database,  connections are typically interrupted and will be not in state between the client processes and the Database server. Quay and the underlying  sql library `peewee` will not recycle and re-establish such connections but rely on a mechanism like kubernetes health, liveness and readyness probes to restart the Quay deployment.

```
HINT: when deploying Quay not in Operator deployment mode, these health, liveness and readyness probes have the be in place for the podman deployment to guarantee similar behavior and self recovery
```
  
Without implementing the mentioned checks to recycle the deployment you'll see following behavior:

* broken connections will be iterated over returning errors in the various workers
* Quay will re-establish at least one connection returning functionality at some point
* depending on how many thread/workers and connections you have, you'll face a lot of broken uploads, 500pages on the UI until Quay recovers.

Same behavior will be seen with Clair utilizing the same database.
Which time frame can we expect to recover without recycling the deployment ?

For Quay, roughly ~5 minutes  depending on what happens to your database. Quay does recover, depending on how many workers you have configured it takes n^ requests to do so but you might still have processes not grabbing a new DB connection at all.

As by concept of `peewee` Database connection handled of from the pool are not checked on state and or functionality at all. This is argued by performance which would drop handing of a pooled connection.

### adding podman health check for Quay

ensure to have following parameters added to your podman configuration:

```
podman run ... \
  --health-cmd='["/usr/bin/curl", "-f", "-s", "http://localhost:8080/health/instance"]'\
  --health-interval=30s \
  --health-on-failure=restart \
  --health-retries=2 \
  --health-start-period=20s \
  --health-timeout=2s
```
Ensure to understand that the values:
* health-interval 
* health-retries

will control how long a not proper functioning Quay instance will be kept alive. In the particular example shown above, Quay would still be serving error pages for about 1 minute (30s check 2 times)

The param `health-start-period` will control how long these checks are omitted when starting the container. Make sure you give Quay enough time to validate it's external resources (Database, Clair, Authentication, ...).

Another word on `restart policy`. If a DB failover occurs existing connections become stale,  Quay needs time and active request to recover from such a scenario. A quicker way to get Quay working again is to simply "restart" with the mentioned health check. 
The fact that rolling upgrade strategies should provide a smoother transition, the total time to finish the recycle of the Container would not improve as the transition between the instances would only occur when the new instance enters the healthy state and the broken Container needs to terminate. Additionally this situation could introduce locking issues on the Database. 

### tuning connection parameters to optimize Quay behavior

First, we need to understand which components are involved in a particular deployment:
* are there Firewalls ?
* are there Load Balancers ?
* which path through the Network does which component take ?

We now assume a scenario where each component goes through a Load Balancer/Proxy.

* Quay -> tcp(1) connection -> Load Balancer -> tcp(2) connection -> Postgresql
* Quay -> tcp(3) connection -> Load Balancer -> tcp(4) connection -> Redis
* Quay -> tcp(5) connection -> Load Balancer -> tcp(6) connection -> Storage

FYI, the number next to `tcp` indicates who creates/initiates a connection. Load Balancer/Proxies tend to open separate connections to the backend Pools of a service to apply various optimizations or parameters to the TCP connection.

For tuning as example a Postgresql connection that means:
* settings on Quay for the tcp connection
* settings on Load Balancer for the tcp connection
* settings on Postgresql for tcp connection

The connection parameters you are looking for are:
* keepalives
* keepalives_idle
* keepalives_count
* keepalives_interval

We can adjust these in our `DB_CONNECTION_ARGS` and or `DB_URI` configuration in config.yaml.
Example setting for sending every 10th second a Keepalive package with the maximum loosing 3 of them and not receiving for maximum 30seconds a Keepalive package from the remote.

```
DB_CONNECTION_ARGS:
  [.. output omitted ..]
  keepalives: 1
  keepalives_idle: 30
  keepalives_interval: 10
  keepalives_count: 3
```

```
NOTE: these should match the configuration on the Load Balancer
```

#### postgresql connection tuning

When looking at postgresql the settings for keepalives are located in `postgresql.conf` and or any `include` configuration.

```
tcp_keepalives_idle = 30			# TCP_KEEPIDLE, in seconds;
tcp_keepalives_interval = 10		# TCP_KEEPINTVL, in seconds;
tcp_keepalives_count = 3			# TCP_KEEPCNT;
```

```
NOTE: these should match the configuration on the Load Balancer.
      For socket based connection keepalives are not considered at all.
```

###  Quay health check difference in DB_CONNECTION_POOLING

When not using `DB_CONNECTION_POOLING` the mentioned health checks will not verify/validate existing connections but create new connections. This means that without connection pooling, only issues which are experienced during the health check calls are considered for recycling the Container accordingly. (Firewall/Load Balancer connection resets will not be detected as new initiated connections are not target for keepalive/timeout issues)

The behavior we will see in such a scenario where established connections are _silently_ dropped by a Firewall/Load Balancer is that requests from various workers will fail with an error and Traback dump in the logs.

```
securityworker stdout | 2023-03-16 13:29:11,176 [97] [ERROR] [workers.worker] Operation raised exception securityworker stdout | Traceback (most recent call last): securityworker stdout | File "/usr/local/lib/python3.9/site-packages/peewee.py", line 3055, in execute_sql securityworker stdout | cursor = self.cursor(commit) securityworker stdout | File "/usr/local/lib/python3.9/site-packages/peewee.py", line 3042, in cursor securityworker stdout | return self._state.conn.cursor() securityworker stdout | psycopg2.InterfaceError: connection already closed securityworker stdout | During handling of the above exception, another exception occurred: securityworker stdout | Traceback (most recent call last): securityworker stdout | File "/quay-registry/workers/worker.py", line 87, in _operation_func securityworker stdout | return operation_func()
```

Verifying that workers do not recycle the connections can be done as follows 

```
$ oc -n quay logs deploy/quay | awk '/peewee.InterfaceError/ { print $1 }' | sort | uniq -c | sort -nr 82 securityworker 55 notificationworker 20 namespacegcworker 20 exportactionlogsworker 19 repositorygcworker 14 gcworker 14 buildlogsarchiver 7 teamsyncworker 6 globalpromstats
```

Even when setting `max_connections` in config.yaml `DB_CONNECTION_POOLING` is not turned on as the max_connections setting affects `peewee` handling connections out in general and not limited to pooling mode.

## exercise failing Clair Database

ToDo: Clair health checks

### tuning connection parameters to optimize Clair behavior

First, we need to understand which components are involved in a particular deployment:
* are there Firewalls ?
* are there Load Balancers ?
* which path through the Network does which component take ?

We now assume a scenario where each component goes through a Load Balancer/Proxy.

* Clair -> tcp(1) connection -> Load Balancer -> tcp(2) connection -> Postgresql
* Clair -> tcp(3) connection -> Load Balancer -> tcp(4) connection -> Redis
* Clair -> tcp(5) connection -> Load Balancer -> tcp(6) connection -> Storage

FYI, the number next to `tcp` indicates who creates/initiates a connection. Load Balancer/Proxies tend to open separate connections to the backend Pools of a service to apply various optimizations or parameters to the TCP connection.

For tuning as example a Postgresql connection that means:
* settings on Clair for the tcp connection
* settings on Load Balancer for the tcp connection
* settings on Postgresql for tcp connection

The connection parameters you are looking for are:
* keepalives
* keepalives_idle
* keepalives_count
* keepalives_interval

For Clair we need to utilize the `DB_URI` syntax in config.yaml.
Example setting for sending every 10th second a Keepalive package with the maximum loosing 3 of them and not receiving for maximum 30seconds a Keepalive package from the remote.

```
[.. output omitted ..]
indexer:
  connstring: host=postgres.clair.svc port=5432 dbname=clair user=clair password=clair sslmode=disable keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=3 tcp_user_timeout=10
  scanlock_retry: 10
  layer_scan_concurrency: 5
  migrations: true
matcher:
  connstring: host=postgres.clair.svc port=5432 dbname=clair user=clair password=clair sslmode=disable keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=3 tcp_user_timeout=10
  max_conn_pool: 50
  run: ""
  migrations: true
  indexer_addr: clair-indexer
notifier:
  connstring: host=postgres.clair.svc port=5432 dbname=clair user=clair password=clair sslmode=disable keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=3 tcp_user_timeout=10
  delivery: 1m
  poll_interval: 5m
  migrations: true
auth:
[.. output omitted ..]
```

```
NOTE: these should match the configuration on the Load Balancer
```

#### postgresql connection tuning

When looking at postgresql the settings for keepalives are located in `postgresql.conf` and or any `include` configuration.

```
tcp_keepalives_idle = 30                        # TCP_KEEPIDLE, in seconds;
tcp_keepalives_interval = 10            # TCP_KEEPINTVL, in seconds;
tcp_keepalives_count = 3                        # TCP_KEEPCNT;
```

```
NOTE: these should match the configuration on the Load Balancer.
      For socket based connection keepalives are not considered at all.
```



