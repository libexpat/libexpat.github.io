Title: Common Pitfalls
Date: 2017-07-31
License: MIT


# Overview

* [Character data is split across multiple handler calls](#split-character-data)
* [External entity sub-parsers must be created after parsing has started](#nested-parser-creation-time)
* [Strings passed to handlers are only temporary](#temporary-strings)
* [Element declaration handlers must free their content models](#free-content-model)
* [XML 1.1 and XML 1.0 Fifth Edition are not supported](#xml-version)


# <a id="split-character-data"></a> Character data may be split across multiple handler calls

If you register a character data handler with
`XML_SetCharacterDataHandler()`, you might expect that you would be
called just once for each section of character data.  Unfortunately
you would be wrong.  Expat can and will split up character data in an
arbitrary manner, presenting each set of characters in separate
calls.  The [introductory parser
walkthrough](../expat-internals-a-simple-parse/) shows an example of
that, as the parser makes separate calls to the handler for a newline
and for a pair of spaces.

Your character data handler will need to be able to cope with this
potentially broken-up input.  The usual approach is to accumulate
characters into a user-defined data structure &mdash; the test suite
has a good example of this in its `CharData` structure and support
functions &mdash; and process the whole thing in one go using start
and end element handlers.  If you know how your character data will be
structured, you may well be able to do better than that.


# <a id="nested-parser-creation-time"></a> External entity sub-parsers must be created *after* parsing has started

There is a note in the description of
`XML_ExternalEntityParserCreate()` in `expat.h` that is easy to miss:

> `XML_ExternalEntityParserCreate()` can be called at any point _after_ the
first call to an ExternalEntityRefHandler [...]

Unfortunately this conflicts with a common programming pattern, that
of creating everything ahead of time; in particular, creating
sub-parsers before starting to parse the input, which will be well
before any `ExternalEntityRefHandler` is called.  This appears to work,
but the sub-parsers will be unable to communicate their results back
to the main parser.

There are a number of "fixes" to this issue that generally cause more
serious problems of their own.  The best solution is to do what
`expat.h` says and not create a sub-parser until the appropriate
handler is called.  The test suite has a lot of examples of creating
and disposing of parsers in the `ExternalEntityRefHandler` itself.


# <a id="temporary-strings"></a> Strings pass to handlers are only temporary

Most of the handlers that users register are passed strings of one
form or another.  A start element handler, for instance, is passed the
name of the element that has started and an array of attribute names
and values.  All of these strings are allocated in dynamic memory, so
handlers should not store pointers to them for later use.  If you
really need one of these string parameters for later, make a copy of
the string itself (and remember to free that when you're done!).


# <a id="free-content-model"></a> Element declaration handlers must free their content models

The description of the `XML_ElementDeclHandler` type in `expat.h`
includes the following remark:

> It's the caller's responsibility to free model when finished with it.

This is a little misleading; "the caller" in this context is the
user's program, not the library as you might assume.  It is up to the
user code to call `XML_FreeContentModel()` on the `model` parameter
passed to an element declaration handler, to free the dynamic memory
used for the model.

Note that this does not mean that the content model must be freed in
the element declaration handler itself.  If the user wishes to keep
content models around, for example to validate elements later on, they
are perfectly at liberty to do so.


# <a id="xml-version"></a> XML 1.1 and XML 1.0 Fifth Edition are not supported

Expat supports [XML 1.0 Fourth Edition](https://www.w3.org/TR/2006/REC-xml-20060816/).
It does *not* support:

- [XML 1.1](https://www.w3.org/TR/xml11/)
- [XML 1.0 Fifth Edition](https://www.w3.org/TR/2008/REC-xml-20081126/)

If Expat is asked to parse documents that are targetting
a version of the XML standard younger than XML 1.0 Fourth Edition,
you may receive parse errors.
