"""Marionette client for the disposable lab profile only; no host browser connection."""
import json
import socket
import sys


with socket.create_connection(('127.0.0.1', 2828), timeout=30) as connection:
    def receive():
        length = b''
        while (char := connection.recv(1)) != b':':
            if not char:
                raise RuntimeError('Firefox closed the Marionette connection')
            length += char
        body = b''
        while len(body) < int(length):
            chunk = connection.recv(int(length) - len(body))
            if not chunk:
                raise RuntimeError('Firefox truncated a Marionette response')
            body += chunk
        return json.loads(body)

    def command(number, name, parameters):
        body = json.dumps([0, number, name, parameters]).encode()
        connection.sendall(str(len(body)).encode() + b':' + body)
        response = receive()
        if response[2]:
            raise RuntimeError(response[2])
        return response[3]

    receive()
    session = command(1, 'WebDriver:NewSession', {})
    # A test accidentally targeting another profile must fail before executing privileged JavaScript.
    assert session['capabilities']['moz:profile'] == '/tmp/win7-firefox-profile', session
    request = json.load(sys.stdin)
    try:
        command(2, 'Marionette:SetContext', {'value': request.get('context', 'chrome')})
        result = command(3, request.get('command', 'WebDriver:ExecuteScript'), request['parameters'])
        print(json.dumps(result['value']))
    finally:
        command(4, 'WebDriver:DeleteSession', {})
