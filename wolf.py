# -*- coding: utf-8 -*-
# http://wsgi.tutorial.codepoint.net/

import os
import sys
import re
import inspect
from collections import defaultdict
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

PROJECT_DIR = os.path.dirname(os.path.realpath(inspect.getfile(sys._getframe(2))))


def template_environment(folder):
    global environment
    loader = FileSystemLoader(searchpath=os.path.join(PROJECT_DIR, folder))
    environment = Environment(loader=loader, trim_blocks=True, lstrip_blocks=True)


template_environment('')


class Link(object):
    def __init__(self, text, url):
        self.text = text
        self.url = url

    def __repr__(self):
        if self.url:
            return u'<a href="{1}">{0}</a>'.format(self.text, self.url)
        else:
            return u'<a>{0}</a>'.format(self.text)


class Route(object):
    def __init__(self, url, methods, names):
        self.url = url
        self.methods = methods
        self.names = names



def default_error_handler(environ, start_response, status):
    output = 'E R R O R'
    output = output.encode('utf-8')
    headers = [('Content-Type', 'text/plain;charset=UTF-8'),
               ('Content-Length', str(len(output)))]
    start_response(status, headers, sys.exc_info())
    return [output]


def env(environ, start_response):
    """ Show environment variables """
    output = []
    for key, value in environ.iteritems():
        output.append('{0} = {1}'.format(key, value))
    output = "\n".join(output).encode('utf-8')
    start_response('200 OK', [('Content-type', 'text/plain;charset=UTF-8'),
                              ('Content-Length', str(len(output)))])
    return [output]


class WSGI(object):
    def __call__(self, environ, start_response):
        raise Exception
        "__call__ method has to be overridden"


class WSGImiddle(WSGI):
    pass


def rel_link(url):
    ret = url.rstrip('$')
    if ret == '/':
        ret = './'
    else:
        ret = ret.lstrip('/')
    return ret


def extract_name(str):
    return str[:str.find('__')]


def redirect_relative(environ, start_response):
    status = '301 Moved Permanently'
    headers = {'Content-Type': 'text/plain;charset=UTF-8'}
    headers['Location'] = environ['SCRIPT_NAME'] + '/'
    output = 'REDIRECT'
    headers['Content-Length'] = str(len(output))
    start_response(status, headers.items())
    return [output]


class Router(WSGImiddle):
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
            route = self.routes[m.lastindex - 1]
            environ['LINKS'] = [Link(r.names, None if r == route else rel_link(r.url)) for r in self.routes if r.names]
            if route.names and index > 0:
                breadcrumb = Link(route.names, environ['SCRIPT_NAME'])
                try:
                    environ['BREADCRUMBS'].append(breadcrumb)
                except KeyError:
                    environ['BREADCRUMBS'] = [breadcrumb]
            if len(m.groupdict()) > 0:
                try:
                    d = parse_qs(environ['ARGUMENT_STRING'])
                except KeyError:
                    d = {}
                d.update((extract_name(k), v) for k, v in m.groupdict().iteritems() if v is not None)
                environ['ARGUMENT_STRING'] = urlencode(d, True)
            try:
                controller = route.methods[environ['REQUEST_METHOD']]
            except KeyError:
                return error_handler(environ, start_response, '405 Method Not Allowed')
            try:
                print controller.__name__
            except AttributeError:
                print controller.__class__.__name__
            output = controller(environ, start_response)
            if output is not None:
                return output
            else:
                return error_handler(environ, start_response, '404 Not Found')
        else:
            return error_handler(environ, start_response, '404 Not Found')

    def _append(self, app, url, methods=['GET'], names=None):
        route = next((i for i in self.routes if i.url == url), None)
        if route is None:
            route = Route(url, {}, names)
            patt = re.compile('({0})'.format(route.url))
            for _ in xrange(patt.groups):
                self.routes.append(route)
        for method in methods:
            if method in route.methods:
                print >> sys.stderr, \
                    'Route url={} method={}, {} is overriden with {}'.format(
                        route.url, method, route.methods[method].__name__, app.__name__)
            route.methods[method] = app

    def append(self, app, url, methods=['GET'], names=None):
        if url == '/':
            self._append(app, url, methods, names)
        elif len(url) > 1 and url[-1] == '/':
            self._append(app, '/' + url, methods, names)
            self._append(redirect_relative, '/' + url[:-1], methods, None)
        else:
            self._append(app, '/' + url + '$', methods, names)
        routes = []
        rl = None
        patt = re.compile(r'\(\?P<(?P<name>[^>]+)\>')
        names = defaultdict(lambda: 0)
        for r in self.routes:
            if r != rl:
                last = 0
                s = ''
                for m in patt.finditer(r.url):
                    name = m.groups()[0]
                    names[name] += 1
                    s += r.url[last:m.start() + 4] + name + '__' + str(names[name])
                    last = m.end() - 1
                s += r.url[last:]
                routes.append('({0})'.format(s))
            rl = r
        self.pattern = re.compile('|'.join(routes))

    def route(self, url, methods=['GET'], names=None):
        assert isinstance(url, basestring), "route decorator needs url parameter"

        def decorate(function):
            self.append(function, url, methods, names)
            return function

        return decorate

    def __repr__(self):
        ret = []
        for r in self.routes:
            for m, ro in r.methods.iteritems():
                if isinstance(ro, WSGImiddle):
                    for rr in ro.__repr__().split("\n"):
                        ret.append(r.url + rr)
                else:
                    ret.append(r.url + " " + m + " " + str(type(ro)))
        return "\n".join(ret)


class Static(WSGI):
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


class Response(WSGI):
    def __init__(self, status='404 Not Found', output='ERROR'):
        self._status = status
        self._headers = {'Content-Type': 'text/plain;charset=UTF-8'}
        self._output = output

    def headers(self, **kwargs):
        self._headers.update(kwargs)
        return self

    def redirect(self, url, status='301 Moved Permanently'):
        self._status = status
        self._headers['Location'] = url
        self._output = 'REDIRECT'
        return self

    def template(self, name, status='200 OK', **kwargs):
        template = environment.get_template(name)
        self._status = status
        self._headers['Content-Type'] = 'text/html;charset=UTF-8'
        self._output = template.render(**kwargs).encode('utf-8')
        return self

    def output(self, output, status='200 OK'):
        self._status = status
        self._headers = {'Content-Type': 'text/plain;charset=UTF-8'}
        self._output = output
        return self

    def content(self, content_type):
        self._headers['Content-Type'] = content_type
        return self

    def __call__(self, environ, start_response):
        if 'Location' in self._headers and environ['QUERY_STRING']:
            self._headers['Location'] += "?" + environ['QUERY_STRING']
        self._headers['Content-Length'] = str(len(self._output))
        start_response(self._status, self._headers.items())
        return [self._output]


# TODO replace Redirect with Response
class Redirect(WSGI):
    def __init__(self, url, status='301 Moved Permanently', headers=None):
        self.url = url
        self.status = status
        self.headers = headers

    def __call__(self, environ, start_response):
        output = 'R E D I R E C T'
        output = output.encode('utf-8')
        url = self.url
        if len(environ['QUERY_STRING']) > 0:
            url += "?" + environ['QUERY_STRING']
        headers = [('Location', url),
                   ('Content-type', 'text/plain'),
                   ('Content-Length', str(len(output)))
                   ]
        if self.headers:
            headers.extend(self.headers)
        start_response(self.status, headers)
        return [output]


class Template(object):
    def __init__(self, templates):
        scriptname = inspect.getfile(sys._getframe(1))
        scriptpath = os.path.dirname(os.path.realpath(scriptname))
        searchpath = os.path.realpath(os.path.join(scriptpath, templates))

        loader = FileSystemLoader(searchpath=searchpath)
        self.environment = Environment(loader=loader, trim_blocks=True, lstrip_blocks=True)

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


def controller(a=None):
    """ Serve GET, POST and RegEx data as function arguments

        argument starting with underscore are taken from environment
        without parentheses uses default values
        a, alternative content-type
    """
    content_type = 'text/plain;charset=UTF-8'
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
                data_post = parse_post_data(environ)
            try:
                data_url = parse_qs(environ['ARGUMENT_STRING'])
            except KeyError:
                data_url = {}
            args = {}
            defaults = f.__code__.co_argcount
            if f.__defaults__ is not None:
                defaults -= len(f.__defaults__)
            for i, arg in enumerate(f.__code__.co_varnames):
                if arg[0] == '_' and arg[1:].upper() in environ:
                    args[arg] = environ[arg[1:].upper()]
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
            if isinstance(output, WSGI):
                return output(environ, start_response)
            elif isinstance(output, basestring):
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


class DBSession(WSGImiddle):
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

    def __repr__(self):
        return self.controller.__repr__()


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
