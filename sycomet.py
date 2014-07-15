#!/usr/bin/env python
# -*- coding: utf-8 -*-
#from txwebsockets import WebSocketFactory, WebSocketServer, BasicOperations
from websocket import WebSocketHandler, WebSocketSite
#
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor
from twisted.web.static import File
import os
import traceback
import sys
import socket

API_KEY = os.environ['SYDROID_API_KEY']


class SycometWebSocketBroadcaster(WebSocketHandler):
    def __init__(self, transport):
        WebSocketHandler.__init__(self, transport)
        self.api_key = ""
        print " > Connection received ! :)"
        self.transport._request.site.presence.append(self)

    def connectionLost(self, reason=None):
        print " > Connection lost :( "
        self.transport._request.site.presence.remove(self)

    def frameReceived(self, data):
        if self.api_key != API_KEY:
            if data.startswith("LOGIN="):
                print " > Provided api_key = " + data[6:]
                self.api_key = data[6:]
                return
            else:
                print " ! Wrong packet received, closing (api_key = " + self.api_key + ")"
                self.transport.loseConnection()

        if os.path.exists("/tmp/sycomet-receiver.sock"):
            try:
                scom = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                scom.connect('/tmp/sycomet-receiver.sock')
                scom.send(data + '@@@ENDOFFRAME@@@\n')
            except:
                print " ! Error : can't dispatch the msg to sycomet-receiver."
                traceback.print_exc(file=sys.stdout)
        else:
            print " ! Warning : Nobody is listening for clients messages."


class SycometWebSocketSite(WebSocketSite):
    def __init__(self, resource, logPath=None, timeout=60 * 60 * 12,
                 supportedProtocols=None):
        WebSocketSite.__init__(self, resource, logPath, timeout, supportedProtocols)
        self.presence = []
        print " ! SycometWebSocketFactory initiated"

    def sendMessageToAllClients(self, mesg):
        for handler in self.presence:
            if handler.api_key == API_KEY:
                handler.transport.write(mesg.encode('utf-8'))


class SycometLocalProtocol(Protocol):
    def dataReceived(self, data):
        data = data.strip('\n')
        self.factory.secfactory.sendMessageToAllClients(data)


class SycometLocalFactory(Factory):
    protocol = SycometLocalProtocol

    def __init__(self, secfactory):
        print " ! SycometLocalFactory initiated"
        self.secfactory = secfactory


root = File('./jail')
secfactory = SycometWebSocketSite(root)
secfactory.addHandler('/sydroid', SycometWebSocketBroadcaster)
factory = SycometLocalFactory(secfactory)

if os.path.exists("/tmp/sycomet-broadcast.sock"):
    os.remove("/tmp/sycomet-broadcast.sock")

print " ! Start listening from Local..."
reactor.listenUNIX("/tmp/sycomet-broadcast.sock", factory)
print " ! Start listening from Web..."
reactor.listenTCP(8007, secfactory)
print " ! Running..."
reactor.run()
print " . End."
