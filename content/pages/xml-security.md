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

[**X**ML e**X**ternal **E**ntity (XXE) vulnerabilities](https://en.wikipedia.org/wiki/XML_external_entity_attack)
are a common security problem in applications that parse XML files.

XXE attacks rely on accessing files via `file://`, `https://`, `ftp://` or relative URLs.
By default, Expat does not access external URLs — neither local nor remote — and is,
therefore, not affected by XXE.

Expat only supports accessing URLs if a self-made external entity handler is configured via
[`XML_SetExternalEntityRefHandler`](https://libexpat.github.io/doc/api/latest/#XML_SetExternalEntityRefHandler).
Configuring such a handler is therefore risky and should not be done if untrusted XML input is
expected.


# <a name="billion-laughs"></a> Billion laughs attack

TODO

