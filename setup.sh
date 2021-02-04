#!/bin/sh
# setup.sh -- Part of ddns-server
# Copyright (C) 2021 foorensic

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
#
set -e

[ -z "$NAMESERVER" ] && echo "ERROR: \$NAMESERVER env var is not set" && exit 1;
[ -z "$SOA_MAIL" ] && echo "ERROR: \$SOA_MAIL env var is not set" && exit 1;
[ -z "$AUTH_USER" ] && echo "ERROR: \$AUTH_USER env var is not set" && exit 1;
[ -z "$AUTH_PASS" ] && echo "ERROR: \$AUTH_PASS env var is not set" && exit 1;
[ -z "$RECORD_TTL" ] && echo "ERROR: \$RECORD_TTL env var is not set" && exit 1;
[ -z "$ZONE" ] && echo "ERROR: \$ZONE env var is not set" && exit 1;


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
	allow-update { localhost; };
};
EOF
fi

# Create zone file if it does not exist
if [ ! -f /var/bind/$ZONE.zone ]
then
	echo "Creating zone file /var/bind/${ZONE}.zone"
	cat > /var/bind/$ZONE.zone <<EOF
\$ORIGIN .
\$TTL 86400	; 1 day
$ZONE.	IN SOA	${NAMESERVER}. ${SOA_MAIL}. (
				74         ; serial
				3600       ; refresh (1 hour)
				900        ; retry (15 minutes)
				604800     ; expire (1 week)
				86400      ; minimum (1 day)
				)
			NS	${NAMESERVER}.
\$ORIGIN ${ZONE}.
\$TTL ${RECORD_TTL}
EOF
fi

echo "Adjusting permissions of /var/bind"
chown root:named /var/bind
chown named:named /var/bind/*
chmod 770 /var/bind/
chmod 644 /var/bind/*

named -fg -4 -u named -c /etc/bind/named.conf &

exec gunicorn -b :5000 wsgi:APP
