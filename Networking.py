#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import json, os

from autobahn.websocket import WebSocketServerFactory, WebSocketServerProtocol
from autobahn.websocket import listenWS
from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import LineReceiver
from collections import Mapping

API_KEY = os.environ['SYDROID_API_KEY']

def diffed(original, challenger):
    result = challenger.copy()
    for k in challenger:
        if k in original:
            if isinstance(challenger[k], Mapping):
                result[k] = diffed(original[k], challenger[k])
                if not len(result[k]):
                    del result[k]
            else:
                if original[k] == challenger[k]:
                    del result[k]
    return result


class SydroidWebsocketBroadcaster(WebSocketServerProtocol):
    def __init__(self):
        self.api_key = ""
        self.cache = {}
        self.throttler = 0

    def is_authenticated(self):
        return self.api_key == API_KEY

    def onOpen(self):
        self.factory.clients.append(self)

    def connectionLost(self, reason=None):
        WebSocketServerProtocol.connectionLost(self, reason)
        if self in self.factory.clients:
            self.factory.clients.remove(self)

    def onMessage(self, data, binary):
        if binary:
            return
        if self.is_authenticated():
            if self.factory.on_receive is not None:
                self.factory.on_receive(data)
        else:
            if data.startswith("LOGIN="):
                self.api_key = data[6:]
                if not self.is_authenticated():
                    self.sendMessage({"type": "error", "reason": "Wrong API key."})
                    self.failConnection(WebSocketServerProtocol.CLOSE_STATUS_CODE_INVALID_PAYLOAD)
            else:
                print " ! Wrong packet received, closing (api_key = " + self.api_key + ")"
                self.failConnection(WebSocketServerProtocol.CLOSE_STATUS_CODE_UNSUPPORTED_DATA)

    def smart_send(self, message):
        if self.throttler % 10:
            diff = diffed(self.cache, message)
            diff["type"] = "diff_status"
            self.sendMessage(json.dumps(diff).strip('\n').encode('utf-8'))
        else:
            self.sendMessage(json.dumps(message).strip('\n').encode('utf-8'))

        self.cache = message

        self.throttler += 1
        pass


class SydroidWebsocketFactory(WebSocketServerFactory):
    protocol = SydroidWebsocketBroadcaster

    def __init__(self, url, debug=None, debug_code_path=None,
                 on_receive=None):
        WebSocketServerFactory.__init__(self, url, debug, debug_code_path)
        self.setProtocolOptions(allowHixie76=True)
        self.clients = []
        self.on_receive = on_receive

    def broadcast(self, message):
        for client in self.clients:
            if client.is_authenticated():
                client.sendMessage(message.strip('\n').encode('utf-8'))

    def smart_broadcast(self, message):
        for client in self.clients:
            if client.is_authenticated():
                client.smart_send(message)
        pass


class SydroidLiquidsoapProtocol(LineReceiver):
    delimiter = '\n'

    def __init__(self, transport):
        LineReceiver(self, transport)
        self.factory.presence.append(self)

    def connectionLost(self, reason=None):
        self.factory.presence.remove(self)

    def lineReceived(self, line):
        if self.factory.on_receive is not None:
            self.factory.on_receive(line)


class SydroidLiquidsoapFactory(Factory):
    protocol = SydroidLiquidsoapProtocol

    def __init__(self, on_receive=None):
        self.on_receive = on_receive
        self.presence = []

    def broadcast(self, mesg):
        for handler in self.presence:
            handler.transport.write(mesg.strip('\n').encode('utf-8'))
