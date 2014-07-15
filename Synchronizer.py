#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from Logger import sylog

from models import Studio, session
from Liquidsoap import liq
import time


class Synchronizer:
    PRELOAD = 5
    ctl = None

    def __init__(self, ctl):
        self.ctl = ctl

    def synchronize_all(self):
        """
        Effectue une synchronisation pour les studios enregistrés.
        """

        for studio in session.query(Studio).all():
            self.synchronize(studio)

    @staticmethod
    def synchronize(studio):
        """
        Effectue une synchronisation pour la playlist donnée.
        
        La synchronisation consiste à mettre en correspondance les 
        informations stockées dans la playlist et les éléments contenus
        dans Liquidsoap.
        """

        if not liq.is_connected:
            return

        playlist = studio.jukebox

        if playlist is None:
            return

        # Getting info from Liquidsoap

        for element in playlist.elements_pending:
            if element.media and element.will_end_at and element.will_end_at < time.time() and \
               element.status != u"done":
                element.mark_as_done()
                studio.mark_as_changed()

        rawnumeros = liq.send_command("request.on_air")
        numeros = rawnumeros.split(' ')
        for rid in numeros:
            metadatas = liq.parse_metadatas(liq.send_command("request.metadata " + str(int(float(rid)))))
            if 'sydroid_uid' in metadatas.keys():
                element = playlist.element_by_uid(int(metadatas['sydroid_uid']))
                if element is not None and 'on_air' in metadatas.keys():
                    newonair = liq.parse_date(metadatas['on_air'])
                    if element.on_air_since != newonair:
                        element.on_air_since = newonair
                        session.add(element)
                        studio.mark_as_changed()
                    if element.will_end_at > time.time() and element.status != "playing":
                        element.status = "playing"
                        session.add(element)
                        studio.mark_as_changed()
                    elif element.will_end_at <= time.time() and element.status != "done":
                        element.mark_as_done()
                        session.add(element)
                        studio.mark_as_changed()

        if (playlist.current_element is not None and playlist.current_element.status == "done") or \
                (playlist.current_element is None and playlist.elements_to_play.count() > 0):
        #            if playlist.current_element is None:
        #                sylog("DEBUG: No current element for curpos = %d," % playlist.curpos)
        #            else:
        #                sylog("DEBUG: Current element (pos=%d) is done,"  % playlist.curpos)

            playlist.curpos += 1
            #            sylog("DEBUG: CURPOS UP ! (from %d to %d)" % (playlist.curpos - 1, playlist.curpos))
            studio.mark_as_changed()

        session.add(studio)
        session.commit()

        # Start of previous "liquidload"

    #        pendels = playlist.elements_pending
    #        if playlist.state == u"playing":
    #            if playlist.current_element is None:
    #                if not pendels.count():
    #                    # Nothing left to play : let's stop the polling.
    #                    playlist.state = u"stopped"
    #                elif pendels.count() >= 1 and pendels[0].status == "ready":
    #                    # Something ready to play ? Let's go !
    #                    self.play(studio.jukebox_liqname, pendels[0], studio)
    #                    studio.mark_as_changed()
    #            else:
    #                if playlist.current_element.status not in ("playing", "loaded", "done"):
    #                    # Playing element detected ready and not loaded : let's play it.
    #                    self.play(studio.jukebox_liqname, playlist.current_element, studio)
    #                    studio.mark_as_changed()
    #                else:
    #                    if pendels.count() >= 2 and \
    #                       pendels[1].status == "ready" and pendels[1].media is not None and \
    #                       playlist.current_element.pending_time <= Synchronizer.PRELOAD:
    #                        # We can preload the next element : let's do it !
    #                        self.play(studio.jukebox_liqname, pendels[1], studio)
    #                        studio.mark_as_changed()

    def play(self, liquidname, element, studio=None):
        if element.media is not None:
            media = element.media

            cmd = '%s.push annotate:sydroid_uid="%d":%s' % (liquidname, element.id, media.path)
            sylog("DEBUG: Loading media on %s, filename = %s" % (liquidname, media.filename))
            liq.send_command(cmd)
            #sylog("Media %s loaded : \n -> %s" % (media, cmd))
            element.status = "loaded"
        else:
            action = element.action
            if action is None or studio is None:
                # Trying to play something empty ? Oo
                return
            element.on_air_since = time.time()
            sylog("DEBUG: Executing %s, in studio %s" % (action.command, studio.slug))
            self.ctl.exec_command(action.command, studio)
            element.mark_as_done()

        studio.mark_as_changed()
        session.add(studio)
        session.add(element)
        session.commit()