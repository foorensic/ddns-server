# ddns-server

This docker container allows you to roll you own dynamic DNS service.


## How does it work?

The idea is to delegate a complete subdomain specifically for dynamic hosts (e.g. dynamic.yourdomain.com) to a host running this service, i.e. make this host the authoritative source for all dynamic host entries.

This container runs a bind instance and also provides a simple REST API endpoint to update and delete A and TXT records in the zone bind is managing, so you can then create and update records for all the hosts you like to be resolved (e.g. host1.dynamic.yourdomain.com, host2.dynamic.yourdomain.com).  TXT record maintenance can for example be helpful in case you need to set text records for Let's Encrypt domain verification dynamically (i.e. you want a wildcard certificate for *.dynamic.yourdomain.com)

**Note** that when using this container you are advised to serve the API via **HTTPS only** as authentication is just basic-auth! Otherwise you'd send your credentials to update and delete records in your zone in plain text!

## How do I use it?

You can check out this repository and build the docker container with a simple `docker build . -t ddns-server`. The container can then be run with something like `docker run -e "ZONE=..." -e ... -p5000:5000 ddns-server`

Alternatively, and maybe more conveniently, you can use docker compose with a compose file similar to the following. Make sure to check and adjust to your needs. You might also want to map the volumes like in the example below, so zone info is saved across container restarts. **Note again: *** exposing port 5000 of this container directly does not provide transport encryption of API requests! 

```yaml
version: '3'

services:
  ddns-server:
    container_name: ddns-server
    build:
      context: ./ddns-server/
      dockerfile: Dockerfile
    environment:
      - ZONE=dynamic.yourdomain.com
      - NAMESERVER=host.yourdomain.com
      - SOA_MAIL=hostmaster.yourdomain.com
      - RECORD_TTL=60
      - AUTH_USER=ddns-user
      - AUTH_PASS=...
    volumes:
      - ./ddns-server-data:/var/bind
      - /etc/localtime:/etc/localtime:ro
    ports:
      - 53:53/udp
      - 127.0.0.1:5000:5000
    restart: always
```

Configuration of the container is done via environment variables:
- `ZONE`: The zone to be handled, e.g. dynamic.yourdomain.com
- `NAMESERVER`: The primary master name server for the `ZONE`. Usually the host this service runs on, e.g. ns.yourdomain.com
- `SOA_MAIL`: The SOA record mail address of the one on charge of the zone. Note that the @ in the email must be replaced with a `.` (dot). For example: hostmaster.yourdomain.com
- `RECORD_TTL`: The records time to live value
- `AUTH_USER`: The user for the requests to the API
- `AUTH_PASS`: The password for requests to the API


The API has pretty simple endpoints:
- `/api/v1/<record_type>/<method>?host=<hosts>&value=<value>`:  

  The slots for the request above:
  - `record_type`: The type of record your are about to change: `A` or `TXT` (case insensitive)
  - `method`: The type of operation, either `update` or `delete`. Deletes or updates a record (case insensitive)
  - `hosts`: A comma separated list of hosts you are updating the record for
  - `value` *optional for A records*: The value to write for the host. This allows you to specify an IP, or if left out, defaults to the request source IP
  
  For example, if you would like to point two DDNS hostnames to your dialup IP at home, you simply need a periodic job to issue a request from your network to:  
  `https://user:pass@host.yourdomain.com:5000/api/v1/A/update?host=host1,host2`  

  On success, the API responds with a JSON:  
  `{"success": true, "message": "Updated record: ['host1.dynamic.yourdomain.com', 'host2.dynamic.yourdomain.com] A xxx.xxx.xxx.xxx"}`
  
- `/api/v1/ip`: Simply returns the IP the request is coming from (in case you need to figure out your own IP in update scripts for example)
