# -*- coding: utf-8 -*-
"""
    lpaste
    ~~~~~~~

    A web application to upload snippets of text, usually samples of source code, for public viewing.

    :copyright: (c) 2012 by Burak Sezer.
    :license: BSD, see LICENSE for more details.
"""

# Import standard Python libraries
import os
import time
import datetime

# Import database modules
import pymongo
from bson.objectid import ObjectId
from bson.errors import InvalidId

# Import Pygments for code colouring
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

# Import Werkzeug to deal with WSGI
from werkzeug.wrappers import Response, Request
from werkzeug.routing import Map, Rule
from werkzeug.wsgi import SharedDataMiddleware
from werkzeug.utils import redirect
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.contrib.sessions import Session, SessionStore, SessionMiddleware

# Import Jinja2 for our nice templates
from jinja2 import Environment, FileSystemLoader

DEBUG = True
RELOADER = True


# This class is borrowed from Werkzeug's code.
# examples/contrib/sessions.py
class MemorySessionStore(SessionStore):
    def __init__(self, session_class=None):
        SessionStore.__init__(self, session_class=None)
        self.sessions = {}
        
    def save(self, session):
        self.sessions[session.sid] = session
        
    def delete(self, session):
        self.sessions.pop(session.id, None)
        
    def get(self, sid):
        if not self.is_valid_key(sid) or sid not in self.sessions:
            return self.new()
        return self.session_class(self.sessions[sid], sid, False)

class Application(object):
    def __init__(self):
        self.mongodb = pymongo.Connection()
        self.lpaste_db = self.mongodb.lpaste_database
        self.items = self.lpaste_db.items
        template_path = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(loader=FileSystemLoader(template_path), \
                autoescape=True)
        
        # Routing
        self.url_map = Map([
            Rule("/", endpoint="index"),
            Rule("/<paste_id>", endpoint="get_paste"),
            Rule("/<paste_id>/html", endpoint="get_raw_html"),
            Rule("/<paste_id>/plain", endpoint="get_plain_item"),
            Rule("/<paste_id>/delete", endpoint="delete")
        ])

    def set_flash_message(self, message):
        if not 'flash' in self.session:
            self.session['flash'] = []
        self.session['flash'].append(message)
        self.session.modified = True

    def get_flash_messages(self):
        flash_messages = self.session.get("flash", [])
        if flash_messages:
            self.session['flash'] = []
        return flash_messages

    def select_pygments_alias(self, language):
        aliases = {
                "Python": "python",
                "Jinja2": "jinja",
                "HTML/Jinja2": "html+jinja",
                "Ruby": "ruby",
                "C": "c",
                "C++": "cpp",
                "Jscript": "javascript",
                "DjangoTemplate": "html+django",
                "Sql": "sql",
                "Css": "css",
                "Xml": "xml",
                "Diff": "diff",
                "Ruby": "Ruby",
                "Rhtml": "rhtml",
                "Haskell": "haskell",
                "Apache": "apache",
                "Bash": "bash",
                "Java": "java",
                "Lua": "lua",
                "Scala": "scala",
                "Erlang": "Erlang",
                "HTML": "html",
                "CSS": "css",
                "PHPTemplate": "html+php",
                "PHP": "php",
                "C#": "csharp",
                "CommonLisp": "common-lisp",
        }
        if language in aliases:
            return aliases[language]

    def render_template(self, template_name, **context):
        the_template = self.jinja_env.get_template(template_name)
        return Response(the_template.render(context), mimetype="text/html")

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            return getattr(self, endpoint)(request, **values)
        except InvalidId, NotFound:
            return self.error_404()
        except HTTPException, err:
            return err

    def index(self, request):
        if request.method == "POST":
            item = {
                    'content': request.form["content"],
                    'language': request.form["language"],
                    'poster': request.form["poster"],
                    'title': request.form["title"],
                    'created_at': datetime.datetime.utcnow()

            }
            paste_id = self.items.insert(item)
            return redirect("/%s" % str(paste_id))
        return self.render_template("index.html", \
                messages=self.get_flash_messages())

    def pygmentize(self, my_item, inline_css=False):
        alias = self.select_pygments_alias(my_item["language"])
        lexer = get_lexer_by_name(alias, stripall=True)
        formatter = HtmlFormatter(linenos=True, cssclass="source", noclasses=inline_css)
        return highlight(my_item["content"], lexer, formatter)

    def get_item(self, paste_id):
        my_item = self.items.find_one({"_id": ObjectId(paste_id)})
        if my_item is None:
            raise NotFound
        return my_item

    def get_paste(self, request, paste_id):
        my_item = self.get_item(paste_id)
        my_item["created_at"] = time.strftime("%A %d. %B %Y", \
                my_item["created_at"].timetuple())
        my_item["content"] = self.pygmentize(my_item)
        return self.render_template("show_item.html", \
                item=my_item)

    def get_raw_html(self, request, paste_id):
        my_item = self.get_item(paste_id)
        return Response(self.pygmentize(my_item, inline_css=True))

    def get_plain_item(self, request, paste_id):
        my_item = self.get_item(paste_id)
        return Response(my_item["content"])

    def delete(self, request, paste_id):
        self.get_item(paste_id)
        self.items.remove({"_id": ObjectId(paste_id)})
        self.set_flash_message("The item has been deleted.")
        return redirect("/")

    def error_404(self):
        response = self.render_template('404.html')
        response.status_code = 404
        return response

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        self.session = environ["werkzeug.session"]
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

def lpaste(with_static=True):
    app = Application()
    if with_static:
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
            '/static': os.path.join(os.path.dirname(__file__), 'static')
        })
    return SessionMiddleware(app, MemorySessionStore())

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    app = lpaste()
    run_simple("127.0.0.1", 5000, app, \
            use_debugger=DEBUG, use_reloader=RELOADER)
