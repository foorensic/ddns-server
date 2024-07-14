#!/bin/sh
# Dynamic DNS Server - docker entrypoint.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# https://github.com/foorensic/ddns-server
# Copyright (C) 2024 foorensic

set -e

[ -z "$ZONE" ] && echo "ERROR: \$ZONE env var is not set" && exit 1;
[ -z "$NAMESERVER" ] && echo "ERROR: \$NAMESERVER env var is not set" && exit 1;
[ -z "$SOA_MAIL" ] && echo "ERROR: \$SOA_MAIL env var is not set" && exit 1;
[ -z "$AUTH_USER" ] && echo "ERROR: \$AUTH_USER env var is not set" && exit 1;
[ -z "$AUTH_PASS" ] && echo "ERROR: \$AUTH_PASS env var is not set" && exit 1;
RECORD_TTL=${RECORD_TTL:-3600}


# Add zone to named.conf if it does not exist
if ! grep 'zone "'$ZONE'"' /etc/bind/named.conf > /dev/null
then
    echo "Adding zone '${ZONE}' to named.conf";
    cat >> /etc/bind/named.conf <<EOF
zone "$ZONE" {
  type master;
  file "$ZONE.zone";
  allow-query { any; };
  allow-transfer { none; };
  allow-update { 127.0.0.1; };
};
EOF
fi

# Create zone file if it does not exist
if [ ! -f /var/bind/$ZONE.zone ]
then
    echo "Creating zone file /var/bind/${ZONE}.zone"
    cat > /var/bind/$ZONE.zone <<EOF
\$TTL ${RECORD_TTL}    ; default TTL for zone
\$ORIGIN ${ZONE}.
@         IN      SOA   ${NAMESERVER}. ${SOA_MAIL}. (
                                2024071300 ; serial number
                                1h         ; refresh
                                15m        ; update retry
                                1w         ; expiry
                                2h         ; minimum
                                )
           IN      NS      ${NAMESERVER}.
EOF
fi

echo "Adjusting permissions of /var/bind"
chown root:named /var/bind
chown named:named /var/bind/*
chmod 770 /var/bind/
chmod 644 /var/bind/*

named -fg -4 -u named -c /etc/bind/named.conf &

exec poetry run uvicorn --host 0.0.0.0 --port 5000 --no-server-header --proxy-headers --forwarded-allow-ips "*" api:app
