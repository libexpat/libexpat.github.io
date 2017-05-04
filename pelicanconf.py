# Copyright (C) 2017 Sebastian Pipping <sebastian@pipping.org>
# Licensed under the MIT license

SITENAME = 'Expat XML parser'
SITEURL = 'https://libexpat.github.io'

GITHUB_URL = 'https://github.com/libexpat/libexpat'

def _github(path=''):
    return GITHUB_URL + path

_DOC_MASTER = 'doc'

PAGE_URL = '%s/{slug}/' % _DOC_MASTER
PAGE_SAVE_AS = '%s/{slug}/index.html' % _DOC_MASTER

DISPLAY_PAGES_ON_MENU = False
MENUITEMS = (
    ('Changelog', _github('/blob/master/expat/Changes')),
    ('Download', 'https://sourceforge.net/projects/expat/files/?source=navbar'),
    ('Documentation', SITEURL + '/%s/' % _DOC_MASTER),
    ('Git Repository', _github()),
    ('Report a Bug', _github('/issues')),
)

INDEX_SAVE_AS = '%s/index.html' % _DOC_MASTER

TIMEZONE = 'UTC'
RELATIVE_URLS = True
THEME = 'notmyidea'

FEED_ALL_ATOM = None
FEED_ALL_RSS = None
FEED_DOMAIN = None

DIRECT_TEMPLATES = ['index']
