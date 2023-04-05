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
    ('Download', 'https://github.com/libexpat/libexpat/releases'),
    ('Documentation', SITEURL + '/%s/' % _DOC_MASTER),
    ('API', SITEURL + '/%s/api/latest/' % _DOC_MASTER),
    ('Git Repository', _github()),
    ('Users', SITEURL + '/' + PAGE_URL.format(slug='users')),
    ('Report a Bug', _github('/issues')),
)

TIMEZONE = 'UTC'
RELATIVE_URLS = True
THEME = './pelican-chameleon-5e2d5ab49fc551b6becec539b211bfe872ebe836'

if 'pelican-chameleon' in THEME:
    _BS3_THEME_NAME = (
        # 'cerulean'
        # 'cosmo'
        # 'cyborg'
        # 'darkly'
        # 'flatly'
        # 'journal'
        # 'lumen'
        'paper'
        # 'readable'
        # 'sandstone'
        # 'simplex'
        # 'slate'
        # 'solar'
        # 'spacelab'
        # 'superhero'
        # 'united'
        # 'yeti'
    )

    if _BS3_THEME_NAME:
        BS3_THEME = ('/3rdparty/bootswatch/%s/bootstrap.min.css'
                     % _BS3_THEME_NAME)

    BS3_JS = '/3rdparty/bootstrap/3.0.0/js/bootstrap.min.js'
    BS3_URL = '/3rdparty/bootstrap/3.0.0/css/bootstrap.min.css'
    JQUERY_JS = '/3rdparty/jquery/jquery-3.6.4.min.js'
    JQUERY_MIGRATE_JS = '/3rdparty/jquery/jquery-migrate-3.4.1.min.js'

FEED_ALL_ATOM = None
FEED_ALL_RSS = None
FEED_DOMAIN = None

DIRECT_TEMPLATES = ['index']
