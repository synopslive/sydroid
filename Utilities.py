import calendar
import time
import sqlalchemy
import tagpy
import os
from models import Media, Studio, Playlist, session


class Utilities:
    def __init__(self):
        pass

    @staticmethod
    def generate_studios():
        for letter in ('a', 'b'):
            if session.query(Studio).filter_by(slug=u"studio_%s" % letter).count() == 0:
                studio_x = Studio(name=u"Studio %s" % letter,
                                  slug=u"studio_%s" % letter,
                                  jukebox_liqname=u"studio_%s_jukebox_playlist" % letter,
                                  bed_liqname=u"studio_%s_bed_playlist" % letter,
                                  fx_liqname=u"studio_%s_fx_playlist" % letter,
                                  rec_show_liqname=u"studio_%s_recorder_show" % letter,
                                  rec_show_enabled=False,
                                  rec_show_active=False,
                                  rec_gold_liqname=u"studio_%s_recorder_gold" % letter,
                                  rec_gold_enabled=False,
                                  rec_gold_active=False,
                                  selected=False)
                session.add(studio_x)
        session.commit()

    @staticmethod
    def attach_empty_playlists():
        for letter in ('a', 'b'):
            studio = session.query(Studio).filter_by(slug=u"studio_%s" % letter).one()

            if studio.jukebox is None:
                studio.jukebox = Playlist()
                session.add(studio)

        session.commit()

    @staticmethod
    def rescan(force=False):
        dossier = "/home/synopslive/media/"

        totalsec = notag = tagged = total = addednum = updatednum = deletednum = intacts = 0

        alltimes = {}
        notfound = []

        for path, updated_at in session.query(Media.path, Media.updated_at):
            alltimes[path] = calendar.timegm(updated_at.utctimetuple())
            notfound.append(path)

        for root, dirs, files in os.walk(dossier):
            for name in files:
                if name.lower().endswith("mp3") or name.lower().endswith("ogg"):
                    elpath = os.path.join(os.path.abspath(root), name)
                    elfilename = os.path.basename(elpath)
                    alreadyexists = elpath in alltimes.keys()
                    if alreadyexists:
                        notfound.remove(elpath)
                    if force or not alreadyexists or elpath in alltimes and \
                            os.stat(elpath).st_mtime > alltimes[elpath]:
                        f = tagpy.FileRef(os.path.join(root, name))
                        t = f.tag()

                        if not t.isEmpty() and t.title and t.artist:
                            tagged += 1
                        else:
                            notag += 1

                        nbsec = f.audioProperties().length

                        totalsec += nbsec

                        eltitle = t.title or None
                        elartist = t.artist or None
                        elalbum = t.album or None
                        try:
                            elpath = elpath.decode("utf-8")
                            elfilename = elfilename.decode("utf-8")
                        except UnicodeDecodeError:
                            try:
                                elpath = elpath.decode("latin1")
                                elfilename = elfilename.decode("latin1")
                            except UnicodeDecodeError:
                                pass

                        ellength = nbsec

                        if not alreadyexists:
                            session.add(Media(path=elpath,
                                              filename=elfilename,
                                              title=eltitle,
                                              artist=elartist,
                                              album=elalbum,
                                              length=int(ellength),
                                              added_at=sqlalchemy.func.now(),
                                              updated_at=sqlalchemy.func.now()))

                            addednum += 1

                        elif alreadyexists:
                            media = session.query(Media).filter_by(path=elpath).first()

                            media.filename = elfilename
                            media.title = eltitle
                            media.album = elalbum
                            media.artist = elartist
                            media.length = int(ellength)
                            media.updated_at = int(time.time())

                            updatednum += 1

                        del elpath, eltitle, elartist, elalbum, ellength
                        del t, f

                        total += 1
                    else:
                        intacts += 1

        if len(notfound):
            for apath in notfound:
                media = session.query(Media).filter_by(path=apath).first()

                session.delete(media)

                deletednum += 1

        session.commit()

        return {
            "added": addednum,
            "updated": updatednum,
            "deleted": deletednum,
            "total": total,
            "untouched": intacts,
            "tagged": tagged,
            "untagged": notag,
            "totalsec": totalsec
        }
