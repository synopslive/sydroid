# -*- encoding: utf-8 -*-

import socket
import threading
import time
from Logger import sylog


class LiquidsoapConnection:
    def __init__(self):
        self.lock = threading.Lock()
        self._connection = None
        self.unable_to_connect = False

    @property
    def connection(self):
        if not self._connection:
            try:
                self._connection = socket.socket()
                self._connection.connect(('127.0.0.1', 1234))
                self.unable_to_connect = False
            except socket.error as detail:
                if not self.unable_to_connect:
                    print u"E: Impossible de se connecter à Liquidsoap. En panne ?"
                    print "   (" + str(detail) + ")"
                self.unable_to_connect = True
                self._connection = None
        return self._connection

    @property
    def is_connected(self):
        return self.connection is not None

    def send_command(self, thecommand):
        with self.lock:
            if self.connection:
                self.connection.send(thecommand.encode('utf-8') + '\r\n')
                data = ""
                while not data.count("\r\nEND\r\n"):
                    data += self.connection.recv(4096 * 16).decode('latin1')
                result = data.replace("\r\nEND\r\n", '').lstrip().rstrip()
                if result == "":
                    return "0.0"
                else:
                    return result
            else:
                sylog("/!\\ Pas de connexion avec Liquidsoap !")
                return None  # Pas de connexion...

    @staticmethod
    def parse_metadatas(metadatas):
        try:
            return dict([(el[0], el[1][1:-1]) for el in [el.split('=') for el in metadatas.split('\n')]])
        except IndexError:
            retour = {}
            for el in metadatas.split('\n'):
                if '=' in el:
                    sp = el.split('=')
                    retour[sp[0]] = "=".join(el[1:])[1:-1]
            return retour

    @staticmethod
    def parse_date(liqdate):
        try:
            return time.mktime(time.strptime(liqdate, '%Y/%m/%d %H:%M:%S'))
        except ValueError:
            return None

    def set_var(self, varname, value):
        fval = ""

        if type(value) is bool:
            if value:
                fval = '"true"'
            else:
                fval = '"false"'

        if type(value) is int:
            value = float(value)

        if type(value) is float:
            fval = repr(value)

        if type(value) is str or type(value) is unicode:
            fval = '"%s"' % value

        sylog("DEBUG: Setting %s to %s" % (varname, fval))

        return self.send_command("var.set %s = %s" % (varname, fval))

    def get_var(self, varname):
        retour = self.send_command("var.get %s" % varname)
        if retour.strip().endswith("is not defined."):
            sylog("/!\\ Erreur retournée par Liquidsoap : \n %s" % retour)
            return None
        if type(retour) == str:
            return retour.strip('"')
        else:
            return retour


liq = LiquidsoapConnection()