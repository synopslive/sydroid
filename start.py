#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from Synchronizer import Synchronizer
from Control import Control
from View import View
from twisted.python import log
from twisted.internet import task, reactor
from Networking import *
import sys

log.startLogging(sys.stdout)

ctl = Control()
syn = Synchronizer(ctl)

wsfactory = SydroidWebsocketFactory("ws://127.0.0.1:8007/", debug=True,
                                    on_receive=lambda x: ctl.parse_line(x))

listenWS(wsfactory)

locfactory = SydroidLiquidsoapFactory(on_receive=lambda x: ctl.parse_line(x))

reactor.listenUNIX('/tmp/sydroid.sock', locfactory)


def send(mesg):
    global wsfactory
    if mesg["type"] == "status":
        wsfactory.smart_broadcast(mesg)
    else:
        wsfactory.broadcast(json.dumps(mesg))

view = View(send)
ctl.sender = send


def main_loop():
    syn.synchronize_all()
    view.update_dradis()

if __name__ == '__main__':
    print "Starting Sydroid."

    l = task.LoopingCall(main_loop)
    l.start(0.4)

    reactor.run()