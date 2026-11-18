#!/usr/bin/env python3
"""Loopback-only WebDAV fixture for the Explorer listing-state VM test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import time

ROOT = Path(sys.argv[1])


def resource(path, folder):
    kind = '<D:collection/>' if folder else ''
    return (f'<D:response><D:href>{path}</D:href><D:propstat><D:prop>'
            f'<D:resourcetype>{kind}</D:resourcetype>'
            '<D:getcontentlength>7</D:getcontentlength>'
            '<D:getlastmodified>Sat, 14 Nov 2026 07:39:00 GMT</D:getlastmodified>'
            '</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>')


class Handler(BaseHTTPRequestHandler):
    def do_PROPFIND(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        path = self.path.rstrip('/') + '/'
        name = path.strip('/')
        if name not in ('Slow', 'Superseded', 'Failed', 'Final'):
            self.send_error(404)
            return
        listing = self.headers.get('Depth') == '1'
        if listing:
            (ROOT / f'{name}.requested').touch()
            deadline = time.monotonic() + 75
            while not (ROOT / f'{name}.release').exists():
                if time.monotonic() > deadline:
                    self.send_error(504)
                    return
                time.sleep(.05)
            if name == 'Failed':
                # KIO expects DAV XML here; an HTML error document can look like a listing.
                self.send_response(404)
                self.send_header('Content-Length', '0')
                self.end_headers()
                (ROOT / f'{name}.responded').touch()
                return
        entries = resource(path, True)
        if listing and name in ('Slow', 'Superseded'):
            entries += resource(path + 'Sample.txt', False)
        body = f'<?xml version="1.0"?><D:multistatus xmlns:D="DAV:">{entries}</D:multistatus>'.encode()
        self.send_response(207)
        self.send_header('Content-Type', 'application/xml; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Superseding a listing can close its worker connection before the response.
            if name != 'Superseded':
                raise
        if listing:
            (ROOT / f'{name}.responded').touch()


with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
    (ROOT / 'port').write_text(str(server.server_port))
    server.serve_forever()
