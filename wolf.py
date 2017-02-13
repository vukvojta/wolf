# -*- coding: utf-8 -*-
# http://wsgi.tutorial.codepoint.net/

import os
import sys
import re
import inspect
from functools import wraps
from urlparse import parse_qs
from urllib import urlencode
from jinja2 import Environment, FileSystemLoader

"""
error page
debug report
"""

"""
support methods
HEAD
OPTIONS
"""


"""
Authentication fills:
AUTH_TYPE
REMOTE_USER

Authorization returns groups based on REMOTE_USER
SQL 'WITH RECURSIVE' query

Every controller lists authorized groups (maybe allow/deny ?) in decorator
and returns
'401 Unauthorized' if not logged in OR offer authentication
'403 Forbidden' if logged in and denied
"""


def default_error_handler(environ, start_response, status):
    output = 'E R R O R'
    output = output.encode('utf-8')
    headers = [('Content-Type', 'text/plain;charset=UTF-8'),
               ('Content-Length', str(len(output)))]
    start_response(status, headers, sys.exc_info())
    return [output]

def env(environ, start_response):
    output = []
    for k in environ.keys():
        output.append("=".join([k, str(environ[k])]))
    output = "\n".join(output).encode('utf-8')
    status = "200 OK"
    headers = [('Content-Type', 'text/plain;charset=UTF-8'),
               ('Content-Length', str(len(output)))]
    start_response(status, headers, sys.exc_info())
    return [output]

class Router(object):
    def __init__(self, *args):
        self.routes = []
        for route in args:
            self.append(*route)

    def __call__(self, environ, start_response):
        try:
            error_handler = environ['ERROR_HANDLER']
        except KeyError:
            error_handler = default_error_handler
        m = self.pattern.match(environ['PATH_INFO'])
        if m:
            index = m.end()
            if index == 0:
                environ['PATH_INFO'] += '/'
            else:
                if environ['PATH_INFO'][index - 1] == '/':
                    index -= 1
            environ['SCRIPT_NAME'] += environ['PATH_INFO'][:index]
            environ['PATH_INFO'] = environ['PATH_INFO'][index:]
            route = self.routes[m.lastindex - 1][1]
            if len(m.groupdict()) > 0:
                try:
                    d = parse_qs(environ['ARGUMENT_STRING'])
                except KeyError:
                    d = {}
                d.update((k, v) for k, v in m.groupdict().iteritems() if v is not None)
                environ['ARGUMENT_STRING'] = urlencode(d, True)
            try:
                controller = route[environ['REQUEST_METHOD']]
            except KeyError:
                return error_handler(environ, start_response, '405 Method Not Allowed')
            output = controller(environ, start_response)
            if output is not None:
                return output
            else:
                return error_handler(environ, start_response, '404 Not Found')
        else:
            return error_handler(environ, start_response, '404 Not Found')

    def append(self, app, url, methods=['GET']):
        route = next((i for i in self.routes if i[0] == url), None)
        if route is None:
            route = (url, {})
            patt = re.compile('({0})'.format(route[0]))
            for _ in xrange(patt.groups):
                self.routes.append(route)
        for method in methods:
            if method in route[1]:
                print >> sys.stderr, \
                    'Route url={} method={}, {} is overriden with {}'.format(
                        route[0], method, route[1][method].__name__, app.__name__)
            route[1][method] = app
        routes = []
        rl = None
        for r in self.routes:
            if r != rl:
                routes.append('({0})'.format(r[0]))
            rl = r
        self.pattern = re.compile('|'.join(routes))

    def route(self, url, method=None):
        assert isinstance(url, basestring), "route decorator needs url parameter"

        def decorate(function):
            if method is None:
                self.append(function, url)
            else:
                self.append(function, url, method)
            return function

        return decorate

    def __str__(self):
        ret = []
        for r in self.routes:
            for m, ro in r[1].iteritems():
                if isinstance(ro, Router):
                    for rr in ro.__str__().split("\n"):
                        ret.append(r[0] + rr)
                else:
                    ret.append(r[0] + " " + m)
        return "\n".join(ret)


class Static(object):
    block_size = 1024
    types = {'.ico': 'image/x-icon',
             '.gif': 'image/gif',
             '.jpg': 'image/jpeg',
             '.jpeg': 'image/jpeg',
             '.png': 'image/png',
             '.svg': 'image/svg+xml',
             '.js': 'application/javascript',
             '.otf': 'application/font-sfnt',
             '.eot': 'application/vnd.ms-fontobject',
             '.ttf': 'application/font-ttf',
             '.woff': 'application/font-woff',
             '.woff2': 'application/font-woff2',
             '.css': 'text/css;charset=UTF-8',
             '.html': 'text/html;charset=UTF-8',
             }

    def __init__(self, path):
        self.path = path

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO']
        if path != '':
            filename = os.path.join(self.path, *environ['PATH_INFO'].split('/'))
        else:
            filename = self.path
        try:
            fin = open(filename, "rb")
            size = os.path.getsize(filename)
            status = '200 OK'
            extension = os.path.splitext(filename)[1]
            headers = [('Content-Type', self.types[extension]),
                       ('Content-Length', str(size))]
            start_response(status, headers)
            if 'wsgi.file_wrapper' in environ:
                return environ['wsgi.file_wrapper'](fin, self.block_size)
            else:
                return iter(lambda: fin.read(self.block_size), '')
        except IOError:
            return


def redirect(start_response, status, url, headers=None):
    if headers is None:
        headers = []
    output = 'R E D I R E C T'
    output = output.encode('utf-8')
    headers.append(('Location', url))
    start_response(status, headers)
    return [output]


class Redirect(object):
    def __init__(self, url):
        self.url = url

    def __call__(self, environ, start_response):
        output = 'R E D I R E C T'
        output = output.encode('utf-8')
        url = self.url
        if len(environ['QUERY_STRING']) > 0:
            url += "?" + environ['QUERY_STRING']
        start_response('301 Moved Permanently', [('Location', url),
                                                 ('Content-type', 'text/plain'),
                                                 ('Content-Length', str(len(output)))])
        return [output]


class Template(object):
    def __init__(self, templates):
        scriptname = inspect.getfile(sys._getframe(1))
        scriptpath = os.path.dirname(os.path.realpath(scriptname))
        searchpath = os.path.realpath(os.path.join(scriptpath, templates))

        loader = FileSystemLoader(searchpath=searchpath)
        self.environment = Environment(loader=loader,
                                       trim_blocks=True, lstrip_blocks=True)

    def render_and_respond(self, start_response, template_name, status='200 OK',
                           content_type='text/html;charset=UTF-8', **kwargs):
        template = self.environment.get_template(template_name)
        output = template.render(**kwargs)

        output = output.encode('utf-8')
        headers = [('Content-Type', content_type),
                   ('Content-Length', str(len(output)))]
        start_response(status, headers)
        return [output]

    def render(self, template_name, **kwargs):
        template = self.environment.get_template(template_name)
        return template.render(**kwargs).encode('utf-8')


def parse_get_data(environ):
    return parse_qs(environ['QUERY_STRING'])


def parse_post_data(environ):
    try:
        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
    except ValueError:
        request_body_size = 0
    return parse_qs(environ['wsgi.input'].read(request_body_size))


def get_client_address(environ):
    """ Get HTTP request address """
    try:
        return environ['HTTP_X_FORWARDED_FOR'].split(',')[-1].strip()
    except KeyError:
        return environ['REMOTE_ADDR']


def controller(a=None, m=None):
    content_type = 'text/html'
    if isinstance(a, basestring):
        content_type = a

    def decorate(f):
        @wraps(f)
        def ctrl(environ, start_response):
            try:
                error_handler = environ['ERROR_HANDLER']
            except KeyError:
                error_handler = default_error_handler
            data_get = parse_qs(environ['QUERY_STRING'])
            if environ['REQUEST_METHOD'] == 'POST':
                data_post = parse_post_data()
            try:
                data_url = parse_qs(environ['ARGUMENT_STRING'])
            except KeyError:
                data_url = {}
            args = {}
            defaults = f.__code__.co_argcount
            if f.__defaults__ is not None:
                defaults -= len(f.__defaults__)
            for i, arg in enumerate(f.__code__.co_varnames):
                if m is not None and arg in m:
                    args[arg] = environ[m[arg]]
                elif arg in data_url:
                    args[arg] = data_url[arg][0]
                elif environ['REQUEST_METHOD'] == 'POST' and arg in data_post:
                    args[arg] = data_post[arg][0]
                elif arg in data_get:
                    args[arg] = data_get[arg][0]
                elif i < defaults:
                    # Missing argument which is not default
                    return error_handler(environ, start_response, '404 Not Found')
            output = f(**args)
            if output is not None:
                start_response('200 OK', [('Content-type', content_type),
                                          ('Content-Length', str(len(output)))])
                return [output]
            else:
                return error_handler(environ, start_response, '404 Not Found')

        return ctrl

    if callable(a):
        return decorate(a)
    else:
        return decorate


class DBSession(object):
    def __init__(self, controller, session_obj):
        self.controller = controller
        self.session_obj = session_obj

    def __call__(self, environ, start_response):
        session = self.session_obj()
        environ['DB_SESSION'] = session
        try:
            output = self.controller(environ, start_response)
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()
        return output


def dbsession(session_obj):
    def decorate(f):
        @wraps(f)
        def controller(environ, start_response):
            session = session_obj()
            environ['DB_SESSION'] = session
            try:
                output = f(environ, start_response)
                session.commit()
            except:
                session.rollback()
                raise
            finally:
                session.close()
            return output

        return controller

    return decorate

class Link(object):
    def __init__(self, text, url):
        self.text = text
        self.url = url

class Paging(object):
    def __init__(self, rows, perpage, page, link):
        """ rows in db table, perpage rows on one page, page to show"""
        self.perpage = perpage
        try:
            self.page = int(page)
        except (TypeError, ValueError):
            self.page = 1
        self.pages = rows / perpage + ((rows % perpage) > 0)
        self.link = link

    def in_range(self):
        return self.page >= 1 and self.page <= self.pages

    def limit(self):
        return self.perpage * (self.page - 1), self.perpage

    def _linky(self, x):
        return Link(x, None) if x == self.page else Link(x, '%s/%d' % (self.link, x) if x > 1 else self.link)

    def links(self):
        paging = [self._linky(1)]
        if self.page > 4:
            paging.append(Link('...', None))
        if self.page == 4:
            paging.append(self._linky(self.page - 2))
        if self.page - 1 > 1:
            paging.append(self._linky(self.page - 1))
        if self.page > 1 and self.page < self.pages:
            paging.append(self._linky(self.page))
        if self.page + 1 < self.pages:
            paging.append(self._linky(self.page + 1))
        if self.page == self.pages - 3:
            paging.append(self._linky(self.page + 2))
        if self.page < self.pages - 3:
            paging.append(Link('...', None))
        paging.append(self._linky(self.pages))
        return paging
