# -*- encoding: utf-8 -*-

from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relation, sessionmaker, relationship, backref
from sqlalchemy.orm.exc import NoResultFound, ObjectDeletedError
from syexceptions import SyCantMove
import os.path
import time

engine = create_engine(os.environ["SYDROID_SQL"], echo=False)

#setup_all()
#
#import codecs
#import sys
#streamWriter = codecs.lookup('utf-8')[-1]
#sys.stdout = streamWriter(sys.stdout)
#
#import sqlalchemy.engine.base
#sqlalchemy.engine.base.Dialect.convert_unicode = True

Base = declarative_base()


class Action(Base):
    __tablename__ = "sy_action"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    command = Column(String(100), nullable=False)

    def __unicode__(self):
        if self.title:
            mtd = self.title
        elif self.command:
            mtd = self.command
        else:
            mtd = u"(vide)"
        return mtd

    def __repr__(self):
        return u"<Action #%d : '%s'>" % (self.id, self.__unicode__())


class Media(Base):
    __tablename__ = "sy_media"

    id = Column(Integer, primary_key=True)
    path = Column(Unicode(500), nullable=False)
    filename = Column(Unicode(255))
    title = Column(Unicode(255))
    artist = Column(Unicode(255))
    album = Column(Unicode(255))
    length = Column(Integer, nullable=False)
    added_at = Column(DateTime)
    updated_at = Column(DateTime)

    def __unicode__(self):
        if self.title and self.artist:
            mtd = u"%s - %s" % (self.title, self.artist)
        else:
            mtd = os.path.basename(u"%s" % self.path)
        return mtd

    def __repr__(self):
        return u"<Media #%d : '%s'>" % (self.id, self.__unicode__())


class Playlist(Base):
    __tablename__ = "sy_playlist"

    id = Column(Integer, primary_key=True)
    curpos = Column(Integer, default=1)
    name = Column(Unicode(200), default=u"Sans nom")

    state = Column(Unicode(200), default=u"stopped")

    def __repr__(self):
        return u"<Playlist #%s : '%s' (%d elements, %s)>" % (self.id,
                                                             self.name,
                                                             len(self),
                                                             self.total_duration())

    def __len__(self):
        return len(self.elements)

    def total_duration(self):
        """
        Total duration of the playlist.
        """
        duration = 0
        for element in self.elements:
            duration += element.length
        return duration

    @property
    def elements_query(self):
        """
        Retourne une requête pointant vers les éléments de la playlist.
        """
        return session.query(PlaylistElement).filter_by(playlist=self)

    @property
    def elements_pending(self):
        """
        Retourne une requête pointant vers les éléments restant de la playlist,
        dont l'élément en cours.
        """
        return self.elements_query.filter(PlaylistElement.position >= self.curpos) \
            .order_by(PlaylistElement.position)

    @property
    def current_element(self):
        try:
            return self.elements_query.filter(PlaylistElement.position == self.curpos).first()
        except NoResultFound:
            return None

    @property
    def elements_to_play(self):
        """
        Retourne une requête pointant vers les éléments restant à lire. Si l'élément
        actuel n'est pas en cours de lecture, il s'agit de la même chose que elements_pending.
        """
        if self.current_element is None or self.current_element != "playing":
            return self.elements_query.filter(PlaylistElement.position >= self.curpos)
        else:
            return self.elements_query.filter(PlaylistElement.position > self.curpos)

    @property
    def uids(self):
        """
        Retourne la liste de tous les uids contenus dans la liste.
        """
        return self.elements_query.select(PlaylistElement.id).all()

    @staticmethod
    def element_by_uid(uid):
        """
        Retourne l'élément indiqué par l'uid.
        """
        try:
            element = session.query(PlaylistElement).get(uid)
            return element
        except ObjectDeletedError:
            return None

    def element_by_pos(self, pos):
        """
        Retourne l'élément positionné à la position pos.
        """
        try:
            element = self.elements_query.filter(PlaylistElement.position == pos).first()
            return element
        except NoResultFound:
            return None

    @property
    def last_element(self):
        """
        Retourne la position du dernier élément de la playlist.
        """
        try:
            return self.elements_query.filter(PlaylistElement.position > -100) \
                .order_by(PlaylistElement.position.desc()).first()
        except NoResultFound:
            return None

    @property
    def last_element_played(self):
        """
        Retourne le dernier élément joué, d'après sa date de lecture.
        """
        try:
            return self.elements_query.query.filter(PlaylistElement.on_air_since is not None) \
                .order_by(PlaylistElement.on_air_since.desc()).first()
        except NoResultFound:
            return None

    def time_before_next_action(self):
        """
        Calcule le temps en secondes précédant la prochaine action enregistrée.
        """
        base = 0

        for element in self.elements_pending.all():
            base += element.pending_time

        #if self.maxTBNA < base:
        #    self.maxTBNA = base

        return base

    def add_element(self, element):
        """
        Ajoute un élément à la playlist, à sa fin.
        """
        if element in self.elements:
            return  # U ARE ALREADY HERE DUDE

        if self.last_element:
            element.position = self.last_element.position + 1
        else:
            element.position = 0

        element.added_at = int(time.time())

        element.playlist = self
        self.elements.append(element)

        self.studio.mark_as_changed()

    def remove_element(self, element):
        """
        Retire un élément de la playlist.
        """
        if not element in self.elements:
            return  # U DON'T BELONG HERE DUDE

        allafter = self.elements_query.filter(PlaylistElement.position > element.position).all()

        for el in allafter:
            el.position -= 1

        self.elements.remove(element)

        element.playlist = None

        self.studio.mark_as_changed()

    def move_element(self, element, position):
        """
        Déplace un élément à un endroit précis de la playlist.
        """
        if not element in self.elements:
            return  # U DON'T BELONG HERE DUDE

        if position < self.curpos:
            raise SyCantMove("Impossible de placer un élément avant l'élément joué.")

        try:
            lastnonreadypos = self.elements_pending.filter(PlaylistElement.status != "ready") \
                .order_by(PlaylistElement.position.desc()).first()

            if position <= lastnonreadypos:
                raise SyCantMove("Impossible de placer un élément avant un élément déjà préchargé.")
        except NoResultFound:
            pass

        if position == self.curpos and self.current_element is not None and \
           self.current_element.status != "ready":
            return

        self.remove_element(element)

        if self.last_element is None or position <= self.last_element.position:
            allafter = self.elements_query.filter(PlaylistElement.position >= position).all()

            for el in allafter:
                el.position += 1
        else:
            position = self.last_element.position + 1

        element.position = position

        element.playlist = self
        self.elements.append(element)

        self.studio.mark_as_changed()

    def insert_element(self, element, position):
        """
        Insère un élément dans la playlist, à la position donnée.

        Techniquement, cela est effectué en ajoutant l'élément, puis en le déplaçant
        au bon endroit.
        """

        if self.last_element is not None and position > self.last_element.position:
            self.add_element(element)
        else:
            self.add_element(element)
            self.move_element(element, position)


class PlaylistElement(Base):
    __tablename__ = "sy_playlist_element"

    id = Column(Integer, primary_key=True)
    position = Column(Integer)
    status = Column(String(8), default="nothing")

    added_at = Column(DateTime)
    edited_at = Column(DateTime)
    on_air_since = Column(DateTime)
    done_since = Column(DateTime)
    skipped = Column(Boolean)

    length_hint = Column(Integer)
    comment = Column(UnicodeText)

    media_id = Column(Integer, ForeignKey('sy_media.id'))
    media = relationship("Media")

    action_id = Column(Integer, ForeignKey('sy_action.id'))
    action = relationship("Action")

    playlist_id = Column(Integer, ForeignKey('sy_playlist.id'))
    playlist = relationship("Playlist", backref="elements")

    status_corresp = {'ready': ':', 'loaded': '=', 'playing': '>', 'done': 'X', 'nothing': '?'}

    @property
    def will_end_at(self):
        """
        Retourne l'heure probable de fin du passage de l'élément.
        """
        if self.on_air_since is None:
            return None

        return int(self.on_air_since) + self.length

    @property
    def content(self):
        """
        Retourne l'action ou le média contenu dans l'élément.
        """
        if self.action:
            return self.action
        else:
            return self.media

    @property
    def length(self):
        """
        Retourne la durée probable de l'élément, soit d'après la durée
        du fichier audio correspondant, soit de la durée indiquée par
        l'utilisateur, dans le cas d'une action.
        """
        if self.action:
            return self.length_hint if self.length_hint is not None else 0
        elif self.media:
            return self.media.length
        else:
            return 0  # Empty playlist element

    @property
    def playing_time(self):
        """
        Retourne le nombre de secondes déjà jouées de cet élément.
        Évidemment, ceci n'a de sens que si l'élément est en cours
        de lecture.
        """
        if self.status == "playing":
            return time.time() - self.on_air_since
        elif self.status == "done":
            return self.length
        else:
            return 0

    @property
    def pending_time(self):
        """
        Temps restant de l'élément.
        """
        if self.status == "playing":
            return self.length - self.playing_time
        else:
            return self.length

    def mark_as_done(self):
        """
        Marque l'élément comme effectué.
        """
        self.status = "done"
        self.done_since = time.time()
        return

    def __repr__(self):
        return "<PlaylistElement #%d, position=%d, '%s'>" % (self.id, int(self.position), self.__str__())

    @staticmethod
    def find_by(uid=None, pos=None, playlist=None):
        """
        Retourne un élément de playlist de la base correspondant aux critères.
        """
        try:
            if uid is not None:
                return session.query(PlaylistElement).get(uid)
            elif pos is not None and playlist is not None:
                return session.query(PlaylistElement).filter_by(position=pos).filter_by(playlist=playlist).first()
            else:
                return None
        except NoResultFound:
            return None

    @staticmethod
    def forge(content_type, content_id):
        try:
            if content_type == "action":
                the_action = session.query(Action).get(content_id)
                return PlaylistElement(action=the_action)
            else:
                the_media = session.query(Media).get(content_id)
                return PlaylistElement(media=the_media)

        except NoResultFound:
            return None


class Studio(Base):
    __tablename__ = "sy_studio"

    id = Column(Integer, primary_key=True)
    name = Column(Unicode(100))
    slug = Column(Unicode(10), unique=True)

    jukebox = relationship("Playlist", backref=backref("studio", uselist=False))
    jukebox_id = Column(Integer, ForeignKey('sy_playlist.id'))
    jukebox_liqname = Column(Unicode(100))

    bed_id = Column(Integer, ForeignKey('sy_media.id'))  # ManyToOne('Media')
    bed = relationship("Media")
    #bed_uid = Column(Integer)
    bed_on_air_since = Column(DateTime)
    bed_liqname = Column(Unicode(100))

    fx_liqname = Column(Unicode(100))

    rec_show_liqname = Column(Unicode(100))
    rec_show_enabled = Column(Boolean)
    rec_show_active = Column(Boolean)
    rec_gold_liqname = Column(Unicode(100))
    rec_gold_enabled = Column(Boolean)
    rec_gold_active = Column(Boolean)

    selected = Column(Boolean)

    last_changed_at = Column(DateTime)

    def __str__(self):
        return "<Studio slug=%r>" % self.slug

    def mark_as_changed(self):
        self.last_changed_at = int(time.time())

    @staticmethod
    def find_by(uid=None, slug=None):
        """
        Retourne un élément de playlist de la base correspondant aux critères.
        """
        try:
            if uid is not None:
                return session.query(Studio).get(uid)
            elif slug is not None:
                return session.query(Studio).filter_by(slug=slug).one()
            else:
                return None
        except NoResultFound:
            return None


Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

session = Session()
