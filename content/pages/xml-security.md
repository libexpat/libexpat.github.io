Title: XML Security
Date: 2025-11-24
License: MIT

> Please note, **this website is work-in-progress**.<br />
Be encouraged to [join improving this website](../../doc/contribute-website/).
Thank you!


# Overview

* [External entities (XXE)](#external-entities)
* [Billion laughs attack](#billion-laughs)


# <a name="external-entities"></a> External entities (XXE)

XML eXternal Entity (XXE) vulnerabilities are a common security problem in applications that parse XML
files.

XXE attacks rely on accessing files via `file://` URLs. Some variations (Blind XXE) also utilize access
to remote URLs (e.g, `https://`, `ftp://`). By default, Expat does not access external URLs (both local
and remote) and is, therefore, not affected by XXE.

Expat only supports accessing URLs if a URL handler is configured via
[`XML_SetExternalEntityRefHandler`](https://libexpat.github.io/doc/api/latest/#XML_SetExternalEntityRefHandler).
Configuring a URL handler is therefore risky and should not be done if untrusted XML input is
expected.


# <a name="billion-laughs"></a> Billion laughs attack

TODO

