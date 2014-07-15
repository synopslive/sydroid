# -*- encoding: utf-8 -*-
import datetime


class Logger:
    def __init__(self):
        self.filelog = open("/home/synopslive/logs/sydroid.log", "a")
        self.filelog.write("==== LOG START ====\n")

        self.previousmsg = ""

    def format(self, msg):
        if type(msg) is unicode:
            msg = msg.encode('utf-8')

        if msg == self.previousmsg:
            return None
        else:
            self.previousmsg = msg

        msg = "[%s] %s" % (datetime.datetime.now().strftime("%x - %X"), msg)

        return msg

    def log(self, msg):
        msg = self.format(msg)

        if msg is None:
            return

        self.filelog.write(msg + '\n')

        self.filelog.flush()

    pass


logger = Logger()


def sylog(msg):
    global logger
    print msg
    #logger.log(msg)