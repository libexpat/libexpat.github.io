Title: How to contribute to this website
Date: 2017-06-03
License: MIT
slug: contribute-website

Cool that you found your way here:
We appreciate your help with improving this website!
This page is meant to document how to do that well.


# Basics

This website is maintained using

* [Markdown syntax](https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet)
  files for articles
* [Pelican](https://blog.getpelican.com/)
  (and theme `notmyidea`) to render HTML from Markdown
* [Pull requests](https://github.com/libexpat/libexpat.github.io/pulls)
  against Git repository
  [libexpat/libexpat.github.io](https://github.com/libexpat/libexpat.github.io)
  on GitHub

To render the website with your changes applied,
running `make` should just work.

When making commits, please exclude changes to HTML files
so we can focus on the interesting bits during review.

Thanks!


# Adding new pages

To add new pages, please:

1. Add a new file `content/pages/UPCOMING-TITLE.md`.
1. Integrate links to that new article at
   the news listing (`content/pages/news.md`) and
   the "Latest News" section at the front page (`content/pages/welcome.md`).


<br/>
We are looking forward to your contribution!

The Expat development team
