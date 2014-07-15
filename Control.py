# -*- encoding: utf-8 -*-
import json

from Liquidsoap import liq
from Logger import sylog
from models import PlaylistElement, Studio, SyCantMove, session, Media, Action
from Utilities import Utilities


class Control:
    sender = None

    def __init__(self):
        pass

    def send_feedback(self, request, result="success", details=None):
        """
        Send feedback to Dradis.
        """

        if "id" not in request:
            request["id"] = None

        objmsg = {"type": "feedback", "id": request['id'], "request": request, "result": result}
        if details is not None:
            objmsg['error_msg'] = details

        sylog("%(result)s: %(details)s" % {'result': result, 'details': repr(details)})

        if self.sender:
            self.sender(objmsg)

    def exec_global(self, request):
        """
        Execute a global-scoped command.
        """

        command = request["command"]

        if command == "go back to perm":
            liq.set_var("selected", "perm")
            liq.send_command("perm-switch.skip")

            self.send_feedback(request)

        elif command == "rescan":
            result = Utilities.rescan()
            self.send_feedback(request, result)

        elif command == "select":
            studio = session.query(Studio).find_by(slug=request["studio"].decode('utf-8'))

            if studio is not None:
                studio.selected = True
                session.add(studio)
                session.commit()
                liq.set_var("selected", str(studio.slug))
                sylog("INFO: Selecting " + studio.slug)
                self.send_feedback(request)
            else:
                self.send_feedback(request, "error", "Unknown studio %s" % request["studio"])

    def exec_command(self, request):
        """
        Execute a studio-related command.
        """

        studio = Studio.find_by(slug=request['studio'])

        try:
            command = request['command']
            flag = request['flag']

            if studio is None:
                return

            if command == "live":
                if flag == "on":
                    studio.jukebox.state = u"stopped"
                    liq.set_var("%s.jukebox.switch" % studio.slug, False)
                    liq.set_var("%s.plateau.volume" % studio.slug, 1.0)

                elif flag == "off":
                    liq.set_var("%s.plateau.volume" % studio.slug, 0.0)
                    liq.set_var("%s.jukebox.volume" % studio.slug, 1.0)

                else:
                    self.send_feedback(request, "error", 'flag should be on or off')

                self.send_feedback(request)

            elif command == "start jukebox":
                studio.jukebox.state = u"playing"
                liq.set_var("%s.jukebox.switch" % studio.slug, True)

                self.send_feedback(request)

                # TODO: Create here a fade-in

                #if stack.lastSentStatus and stack.lastSentStatus["mode"] == "live":
                #    liq.set_var("%s.jukebox.volume" % studio.slug, 0.3)
                if studio.jukebox.current_element is not None and \
                   studio.jukebox.current_element.action is not None and \
                   studio.jukebox.current_element.action.command == "end show":
                    # TODO: ORLY ?
                    self.exec_command({"command": "end show", "studio": studio.slug})
                    studio.jukebox.current_element.mark_as_done()
                    studio.jukebox.curpos += 1
                    studio.mark_as_changed()
                    self.exec_command({"command": "live", "flag": "off", "studio": studio.slug})

            elif command == "start jukebox and live off":
                self.exec_command({"command": "start jukebox", "studio": studio.slug})
                self.exec_command({"command": "live", "flag": "off", "studio": studio.slug})

                self.send_feedback(request)

            elif command == "enable recorder":
                # TODO Enable a recorder
                pass

            elif command == "disable recorder":
                # TODO Disable a recorder
                pass

            elif command == "start recorder":
                # TODO Start a recorder
                pass

            elif command == "start recorder":
                # TODO Stop a recorder
                pass

            elif command == "start recording":
                # TODO Start all enabled recoders
                pass

            elif command == "stop recording":
                # TODO Stop all enabled recorders
                pass

            elif command == "start show":
                studio.jukebox.state = u"playing"
                self.exec_command({"command": "start recording", "studio": studio.slug})
                self.exec_global({"command": "select", "studio": studio.slug})
                self.exec_command({"command": "start jukebox", "studio": studio.slug})

                self.send_feedback(request)

            elif command == "end show":
                studio.jukebox.state = u"stopped"
                liq.set_var("%s.running" % studio.slug, False)
                liq.set_var("%s.jukebox.switch" % studio.slug, False)
                self.exec_command({"command": "stop recording", "studio": studio.slug})

                if studio.selected:
                    studio.selected = False
                    self.exec_command({"command": "go back to perm"})

                self.send_feedback(request)

            elif command == "bed" and flag == "on":
                liq.set_var("%s.bed.switch" % studio.slug, True)
                liq.send_command("%s-bed-switch.skip" % studio.slug)

                self.send_feedback(request)

            elif command == "bed" and flag == "off":
                liq.set_var("%s.bed.switch" % studio.slug, False)

                self.send_feedback(request)

            elif command == "skip":
                liq.send_command("%s-jukebox-stereo.skip" % studio.slug)
                studio.jukebox.current_element.mark_as_done()
                studio.jukebox.curpos += 1

                self.send_feedback(request)

            elif command == "set var":
                liq.set_var(request["key"], request["value"])

            elif command == "push":
                element = PlaylistElement.forge(request["element_type"], int(request["element_id"]))
                element.status = u"ready"

                studio.jukebox.add_element(element)

                self.send_feedback(request)

            elif command == "insert":
                if "action_id" in request:
                    element = session.query(Action).get(int(request["action_id"]))
                elif "media_id" in request:
                    element = session.query(Media).get(int(request["media_id"]))
                else:
                    # ERROR
                    return

                element.status = u"ready"

                studio.jukebox.insert_element(element, int(request["position"]))

                self.send_feedback(request)

            elif command == "remove":
                element = PlaylistElement.find_by(uid=int(request["element_id"]))

                studio.jukebox.remove_element(element)

                session.delete(element)

                self.send_feedback(request)

            elif command == "move":
                element = PlaylistElement.find_by(uid=int(request["element_id"]))

                studio.jukebox.move_element(element, int(request["position"]))

                self.send_feedback(request)

            elif command == "debug":
                if "action" in request:
                    if request["action"] == "set position":
                        studio.jukebox.curpos = int(request["position"])

                    elif request["action"] == "reload current":
                        if studio.jukebox.current_element is not None and \
                           studio.jukebox.current_element.status == "loaded":
                            studio.jukebox.current_element.status = "ready"
                            studio.mark_as_changed()

                    elif request["action"] == "force unselect":
                        studio.selected = False

                    else:
                        self.send_feedback(request, "error", "unknown action %s for debug" % request["action"])
                        return
                else:
                    self.send_feedback(request, "error", "action is required")
                    return

                self.send_feedback(request)

            else:
                self.send_feedback(request, "error", "Unknown command '%s', ignored." % command)

                sylog("Commande %s inconnue ; ignorée." % command)

        except SyCantMove as details:

            self.send_feedback(request, "error", details.message)

        if studio:
            studio.mark_as_changed()

        session.add(studio)
        session.commit()

    def parse_line(self, jsoned):
        try:
            request = json.loads(jsoned)
        except ValueError, e:
            sylog(e.message)
            sylog("Received a corrupted JSON, ignoring...")
            return

        if 'command' not in request or 'id' not in request:
            self.send_feedback(request, "error", "command and id required")

        sylog("INFO: Received %s from %s" % (request['command'], request['id']))

        if 'studio' in request:
            self.exec_command(request)

        else:
            self.exec_global(request)
