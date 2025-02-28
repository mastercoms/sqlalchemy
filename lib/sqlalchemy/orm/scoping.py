# orm/scoping.py
# Copyright (C) 2005-2022 the SQLAlchemy authors and contributors
# <see AUTHORS file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: https://www.opensource.org/licenses/mit-license.php

from . import exc as orm_exc
from .base import class_mapper
from .session import Session
from .. import exc as sa_exc
from ..util import create_proxy_methods
from ..util import ScopedRegistry
from ..util import ThreadLocalRegistry
from ..util import warn
from ..util import warn_deprecated

__all__ = ["scoped_session", "ScopedSessionMixin"]


class ScopedSessionMixin:
    @property
    def _proxied(self):
        return self.registry()

    def __call__(self, **kw):
        r"""Return the current :class:`.Session`, creating it
        using the :attr:`.scoped_session.session_factory` if not present.

        :param \**kw: Keyword arguments will be passed to the
         :attr:`.scoped_session.session_factory` callable, if an existing
         :class:`.Session` is not present.  If the :class:`.Session` is present
         and keyword arguments have been passed,
         :exc:`~sqlalchemy.exc.InvalidRequestError` is raised.

        """
        if kw:
            if self.registry.has():
                raise sa_exc.InvalidRequestError(
                    "Scoped session is already present; "
                    "no new arguments may be specified."
                )
            else:
                sess = self.session_factory(**kw)
                self.registry.set(sess)
        else:
            sess = self.registry()
        if not self._support_async and sess._is_asyncio:
            warn_deprecated(
                "Using `scoped_session` with asyncio is deprecated and "
                "will raise an error in a future version. "
                "Please use `async_scoped_session` instead.",
                "1.4.23",
            )
        return sess

    def configure(self, **kwargs):
        """reconfigure the :class:`.sessionmaker` used by this
        :class:`.scoped_session`.

        See :meth:`.sessionmaker.configure`.

        """

        if self.registry.has():
            warn(
                "At least one scoped session is already present. "
                " configure() can not affect sessions that have "
                "already been created."
            )

        self.session_factory.configure(**kwargs)


@create_proxy_methods(
    Session,
    ":class:`_orm.Session`",
    ":class:`_orm.scoping.scoped_session`",
    classmethods=["close_all", "object_session", "identity_key"],
    methods=[
        "__contains__",
        "__iter__",
        "add",
        "add_all",
        "begin",
        "begin_nested",
        "close",
        "commit",
        "connection",
        "delete",
        "execute",
        "expire",
        "expire_all",
        "expunge",
        "expunge_all",
        "flush",
        "get",
        "get_bind",
        "is_modified",
        "bulk_save_objects",
        "bulk_insert_mappings",
        "bulk_update_mappings",
        "merge",
        "query",
        "refresh",
        "rollback",
        "scalar",
        "scalars",
    ],
    attributes=[
        "bind",
        "dirty",
        "deleted",
        "new",
        "identity_map",
        "is_active",
        "autoflush",
        "no_autoflush",
        "info",
        "autocommit",
    ],
)
class scoped_session(ScopedSessionMixin):
    """Provides scoped management of :class:`.Session` objects.

    See :ref:`unitofwork_contextual` for a tutorial.

    .. note::

       When using :ref:`asyncio_toplevel`, the async-compatible
       :class:`_asyncio.async_scoped_session` class should be
       used in place of :class:`.scoped_session`.

    """

    _support_async = False

    session_factory = None
    """The `session_factory` provided to `__init__` is stored in this
    attribute and may be accessed at a later time.  This can be useful when
    a new non-scoped :class:`.Session` or :class:`_engine.Connection` to the
    database is needed."""

    def __init__(self, session_factory, scopefunc=None):
        """Construct a new :class:`.scoped_session`.

        :param session_factory: a factory to create new :class:`.Session`
         instances. This is usually, but not necessarily, an instance
         of :class:`.sessionmaker`.
        :param scopefunc: optional function which defines
         the current scope.   If not passed, the :class:`.scoped_session`
         object assumes "thread-local" scope, and will use
         a Python ``threading.local()`` in order to maintain the current
         :class:`.Session`.  If passed, the function should return
         a hashable token; this token will be used as the key in a
         dictionary in order to store and retrieve the current
         :class:`.Session`.

        """
        self.session_factory = session_factory

        if scopefunc:
            self.registry = ScopedRegistry(session_factory, scopefunc)
        else:
            self.registry = ThreadLocalRegistry(session_factory)

    def remove(self):
        """Dispose of the current :class:`.Session`, if present.

        This will first call :meth:`.Session.close` method
        on the current :class:`.Session`, which releases any existing
        transactional/connection resources still being held; transactions
        specifically are rolled back.  The :class:`.Session` is then
        discarded.   Upon next usage within the same scope,
        the :class:`.scoped_session` will produce a new
        :class:`.Session` object.

        """

        if self.registry.has():
            self.registry().close()
        self.registry.clear()

    def query_property(self, query_cls=None):
        """return a class property which produces a :class:`_query.Query`
        object
        against the class and the current :class:`.Session` when called.

        e.g.::

            Session = scoped_session(sessionmaker())

            class MyClass:
                query = Session.query_property()

            # after mappers are defined
            result = MyClass.query.filter(MyClass.name=='foo').all()

        Produces instances of the session's configured query class by
        default.  To override and use a custom implementation, provide
        a ``query_cls`` callable.  The callable will be invoked with
        the class's mapper as a positional argument and a session
        keyword argument.

        There is no limit to the number of query properties placed on
        a class.

        """

        class query:
            def __get__(s, instance, owner):
                try:
                    mapper = class_mapper(owner)
                    if mapper:
                        if query_cls:
                            # custom query class
                            return query_cls(mapper, session=self.registry())
                        else:
                            # session's configured query class
                            return self.registry().query(mapper)
                except orm_exc.UnmappedClassError:
                    return None

        return query()


ScopedSession = scoped_session
"""Old name for backwards compatibility."""
