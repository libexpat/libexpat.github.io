Title: XML Security
Date: 2025-11-24
License: MIT

> Please note, **this website is work-in-progress**.<br />
Be encouraged to [join improving this website](../../doc/contribute-website/).
Thank you!


# Overview

* [External entities (XXE)](#external-entities)
* [Billion laughs attack](#billion-laughs)


# <a id="external-entities"></a> External entities (XXE)

[**X**ML e**X**ternal **E**ntity (XXE) vulnerabilities](https://en.wikipedia.org/wiki/XML_external_entity_attack)
are a common security problem in applications that parse XML files.

XXE attacks rely on accessing files via `file://`, `https://`, `ftp://` or relative URLs.
By default, Expat does not access external URLs — neither local nor remote — and is,
therefore, not affected by XXE.

Expat only supports accessing URLs if a self-made external entity handler is configured via
[`XML_SetExternalEntityRefHandler`](https://libexpat.github.io/doc/api/latest/#XML_SetExternalEntityRefHandler).
Configuring such a handler is therefore risky and should not be done if untrusted XML input is
expected.


# <a id="billion-laughs"></a> Billion laughs attack

By recursively nesting entities, it is possible to have a relatively small XML input file that generates a
huge output after processing entities and/or takes a long time to process. In case of high memory
usage, an XML parser may crash if the out-of-memory situation is not handled gracefully. This is known as a
billion laughs attack.

Expat includes countermeasures against billion laugh attacks. By default, Expat stops processing inputs if
the output is more than 100 times larger than the input and larger than 8 MiB.

The billion laughs attack in Expat, which affected versions before 2.4.0, is tracked as
[CVE-2013-0340](https://www.cve.org/CVERecord?id=CVE-2013-0340).

Note that there are variations of the billion laughs attack and other denial of service issues in XML parsing.
Examples include [CVE-2025-59375](https://www.cve.org/CVERecord?id=CVE-2025-59375) (inputs can cause large
dynamic memory allocation, fixed in 2.7.2) and
[CVE-2024-8176](https://www.cve.org/CVERecord?id=CVE-2024-8176) (crash due to deep recursion, fixed in 2.7.0).
