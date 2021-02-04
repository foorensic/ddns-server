#!/usr/bin/env python
"""ddns-api -- Part of ddns-server
Copyright (C) 2021 foorensic

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

https://github.com/foorensic/ddns-server

"""
import os
import ipaddress
import tempfile
import subprocess
from typing import Dict
from flask import Flask, Response, request, make_response
from flask.logging import create_logger
from flask_restful import Resource, Api, reqparse
from flask_httpauth import HTTPBasicAuth

APP = Flask(__name__)
API = Api(APP, prefix='/api/v1')
AUTH = HTTPBasicAuth()
LOG = create_logger(APP)

# Config
AUTH_USER = os.environ['AUTH_USER']  # This intentionally
AUTH_PASS = os.environ['AUTH_PASS']  # raises a KeyError
RECORD_TTL = os.environ.get('RECORD_TTL', '3600')
ZONE = os.environ.get('ZONE', '').lstrip('.')
NSUPDATE = '/usr/bin/nsupdate'


def valid_ip(address: str) -> bool:
    """Validates an IP address"""
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        pass
    return False


@AUTH.verify_password
def verify(username: str, password: str) -> bool:
    """Verifies username and password"""
    if not (username and password):
        return False
    if not AUTH_USER or not AUTH_PASS:
        return False
    valid = username == AUTH_USER and password == AUTH_PASS
    if valid:
        return valid
    LOG.warning('User/Pass wrong: %s/%s', username, password)
    return False


# pylint: disable=too-few-public-methods
class ResourceHandler(Resource):
    """Resource handler
    """
    parser = reqparse.RequestParser()
    parser.add_argument('host', type=str, default='', trim=True)
    parser.add_argument('value', type=str, default='', trim=True)

    # pylint: disable=too-many-branches,too-many-return-statements
    @AUTH.login_required
    def get(self, record_type: str, method: str) -> Dict:
        """GET request handler

        """
        record_type = record_type.upper().strip()
        method = method.lower().strip()

        if record_type not in ['A', 'TXT']:
            LOG.warning('Unknown record type "%s" for request: %s',
                        record_type, request.url)
            return {'success': False, 'message': 'Unknown record'}
        if method not in ['update', 'delete']:
            LOG.warning('Unknown method "%s" for request: %s', method,
                        request.url)
            return {'success': False, 'message': 'Unknown method'}

        args = self.parser.parse_args()

        # Prepare the host(s)
        hosts = [
            host.strip() + '.' + ZONE for host in args.host.split(',')
            if host.strip()
        ]
        if not hosts:
            LOG.warning('Request is missing host value: %s', request.url)
            return {'success': False, 'message': 'Missing host value'}

        # Prepare value
        value = ''
        if record_type == 'A':
            if args.value:
                if not valid_ip(args.value):
                    LOG.warning('Request has invalid IP address "%s": %s',
                                args.value, request.url)
                    return {'success': False, 'message': 'Address invalid'}
                value = args.value
            else:
                # See if there is a X-Real-IP header field, fallback to request IP
                value = request.headers.get('X-Real-IP', request.remote_addr)
        elif record_type == 'TXT':
            if not args.value and not method == 'delete':
                LOG.warning('Request for TXT cannot have empty value: %s',
                            request.url)
                return {'success': False, 'message': 'Empty TXT value'}
            value = '"' + args.value.strip(' "') + '"'

        # Create the update file
        file_content = 'server localhost\n'
        file_content += 'zone %s\n' % ZONE
        for host in hosts:
            record_text = 'update delete {record!s} {record_type!s}\n'
            if method == 'update':
                record_text += 'update add {record!s} {ttl!s} {record_type!s} {value!s}\n'
            file_content += record_text.format(record=host,
                                               record_type=record_type,
                                               ttl=RECORD_TTL,
                                               value=value)
        file_content += 'send\n'

        update_filename = os.path.join(tempfile.gettempdir(), 'nsupdate.txt')
        with open(update_filename, 'wt') as uf_handle:
            uf_handle.write(file_content)
        LOG.info('Created update file: %s', update_filename)
        command = [NSUPDATE, update_filename]
        try:
            subprocess.run(command,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           check=True)
        except subprocess.CalledProcessError as err:
            LOG.error('%s: %s', err, err.stderr)
            return {'success': False, 'message': 'Error updating zone'}

        # Return message
        message = 'Updated record: %s %s %s' % (hosts, record_type, value)
        if method == 'delete':
            message = 'Deleted record: %s %s' % (hosts, record_type)
        return {'success': True, 'message': message}


# pylint: disable=too-few-public-methods
class ResourceHandlerIp(Resource):
    """Resource handler for "What's my IP" requests

    """

    # pylint: disable=no-self-use
    def get(self) -> Response:
        """GET request handler"""
        remote_ip = request.headers.get('X-Real-IP', request.remote_addr)
        response = make_response(remote_ip, 200)
        response.mimetype = 'text/plain'
        return response


API.add_resource(ResourceHandler, '/<string:record_type>/<string:method>')
API.add_resource(ResourceHandlerIp, '/ip')

if __name__ == '__main__':
    APP.run(debug=True)
