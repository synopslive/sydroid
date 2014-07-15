# -*- encoding: utf-8 -*-
from calendar import timegm
from collections import Mapping

import json, socket
from math import floor
from Liquidsoap import liq
import urllib2
import time
import hashlib
from Logger import sylog
from models import Studio, session


def safe_float(value):
    """
    Convertit en float, ou mets à 0 si None.
    """
    if value is None:
        return 0
    return float(value)


class View:
    def __init__(self, sender=None):
        self.lastLoggedAudience = 0
        self.lastLoggedAudienceTime = 0
        self.hashstatus = ""
        self.sender = sender

        self.statsslperm = open("./statsslperm", "a+")
        pass

    def send_status(self, dictstatus):
        if self.sender is not None:
            self.sender(dictstatus)

        return json.dumps(dictstatus)

    def format_sec(self, seconds):
        seconds = int(seconds)
        if seconds < 0:
            return "-0:00"
        if seconds > 3600:
            hours = int(floor(seconds / 3600.0))
            minutes = int(floor((seconds % 3600) / 60.0))
            secs = seconds % 60
            return str(hours) + ":" + str(minutes).zfill(2) + ":" + str(secs).zfill(2)
        else:
            minutes = int(floor(seconds / 60.0))
            secs = seconds % 60
            return str(minutes).zfill(2) + ":" + str(secs).zfill(2)

    def update_dradis(self):
        """
        Forge et envoie un paquet JSON comprenant tout le nécessaire afin d'analyser
        l'état du système.

        Utilisé par Dradis.
        """
        paquet = {
            'type': "status",
            'serverTime': time.time(),
            'selectedReal': liq.get_var("selected"),
            'studios': {}
        }

        if liq.is_connected:
            for studio in session.query(Studio).all():
                studio_status = {}

                jukebox_volume = safe_float(liq.get_var("%s.jukebox.volume" % studio.slug))
                plateau_volume = safe_float(liq.get_var("%s.plateau.volume" % studio.slug))
                bed_volume = safe_float(liq.get_var("%s.bed.volume" % studio.slug))
                fx_volume = safe_float(liq.get_var("%s.fx.volume" % studio.slug))

                is_jukebox = liq.get_var("%s.jukebox.switch" % studio.slug) == "true"
                is_bed = liq.get_var("%s.bed.switch" % studio.slug) == "true"
                is_plateau = plateau_volume > 0
                is_fx = fx_volume > 0

                if is_plateau:
                    mode = "live"
                else:
                    mode = "jukebox"

                studio_status["mode"] = mode

                studio_status["switches"] = {
                    'plateau': is_plateau,
                    'bed': is_bed,
                    'jukebox': is_jukebox,
                    'fx': is_fx
                }

                studio_status["selected"] = studio.selected

                if studio.jukebox and studio.jukebox.current_element:
                    studio_status["current_id"] = studio.jukebox.current_element.id
                    if studio.jukebox.current_element.status == u"playing":
                        studio_status["current_playing_time"] = studio.jukebox.current_element.playing_time
                        studio_status["current_pending_time"] = studio.jukebox.current_element.pending_time
                    else:
                        studio_status["current_playing_time"] = 0
                        studio_status["current_pending_time"] = studio.jukebox.current_element.length
                    studio_status["current_length"] = studio.jukebox.current_element.length

                    if studio.jukebox.current_element.media is not None:
                        studio_status["current_metadatas"] = {
                            "title": studio.jukebox.current_element.media.title,
                            "artist": studio.jukebox.current_element.media.artist,
                            "album": studio.jukebox.current_element.media.album,
                            "filename": studio.jukebox.current_element.media.filename
                        }
                    else:
                        studio_status["current_metadatas"] = {
                            "title": "",
                            "artist": "",
                            "album": ""
                        }
                else:
                    studio_status["current_id"] = -1
                    studio_status["current_playing_time"] = 0
                    studio_status["current_pending_time"] = 0
                    studio_status["current_metadatas"] = {}
                    studio_status["current_length"] = 0

                if studio.jukebox:
                    studio_status["curpos"] = studio.jukebox.curpos

                    studio_status["time_before_next_action"] = studio.jukebox.time_before_next_action()

                studio_status["volumes"] = {
                    'plateau': plateau_volume,
                    'bed': bed_volume,
                    'jukebox': jukebox_volume,
                    'fx': fx_volume
                }

                allvariables = {}
                allcommands = liq.send_command("var.list")
                for ligne in allcommands.split("\n"):
                    nomvar, typevar = ligne.split(' : ')
                    if nomvar.startswith(str(studio.slug)):
                        valvar = liq.get_var(nomvar)
                        if typevar == "string":
                            allvariables[nomvar] = str(valvar.strip('"').rstrip('"'))
                        elif typevar == "float":
                            allvariables[nomvar] = float(valvar)

                studio_status["variables"] = allvariables

                studio_status["last_changed_at"] = studio.last_changed_at

                if studio.selected:
                    paquet["selected_sydroid"] = studio.slug

                paquet["studios"][studio.slug] = studio_status

        else:
            paquet["error"] = "Not connected with Liquidsoap !"

        numauditeurs = 0

        for line in urllib2.urlopen('http://localhost:8000/status3.xsl'):
            try:
                numauditeurs += int(line.split(":")[1].rstrip().rstrip(';'))
            except (IndexError, ValueError):
                pass

        paquet["listeners"] = numauditeurs

        live_metadata = json.loads(liq.send_command("live.metadata").encode('latin1'))

        if isinstance(live_metadata, Mapping):
            paquet["liveMetadata"] = {
                "title": live_metadata["title"] if "title" in live_metadata else "?",
                "artist": live_metadata["artist"] if "artist" in live_metadata else "?",
                "album": live_metadata["album"] if "album" in live_metadata else "?"
            }

        self.lastSentStatus = paquet

        jsoned = self.send_status(paquet)

        md5status = hashlib.md5(jsoned).hexdigest()

        if self.lastLoggedAudience != numauditeurs or (time.time() - self.lastLoggedAudienceTime) > 30:
            self.statsslperm.write(time.strftime("%d/%m/%Y - %H:%M:%S") + "," + str(numauditeurs) + "\n")
            self.statsslperm.flush()
            self.lastLoggedAudience = numauditeurs
            self.lastLoggedAudienceTime = time.time()

        if self.hashstatus != md5status:
            self.hashstatus = md5status

    def getStatus(self, studio):
        timeBeforeNextAction = studio.jukebox.time_before_next_action()

        rightInfo = ""
        if timeBeforeNextAction:
            rightInfo += self.format_sec(timeBeforeNextAction) + " bef. next act."
            if studio.jukebox.current_element and studio.jukebox.current_element.on_air_since:
                rightInfo += " :: [%s/%s]" % \
                             (self.format_sec(studio.jukebox.current_element.playing_time),
                              self.format_sec(studio.jukebox.current_element.length))
        rightInfo += " :: curPos = %d \n" % studio.jukebox.curpos
        rightInfo = rightInfo.rjust(65)

        msg = (" ----------------------------------------------------------------------------\n" +
               "  %s :: %s" +
               " ----------------------------------------------------------------------------\n") \
              % (studio.name.capitalize(), rightInfo)

        return msg

    def getContent(self, studio):
        rendu = "   Pos    Titre - Artiste                                            Id\n"

        for el in studio.jukebox.elements_pending:
            rendu += unicode(el).encode('utf-8') + "\n"

        return rendu

    def __repr__(self):
        return "<View>"

    pass
