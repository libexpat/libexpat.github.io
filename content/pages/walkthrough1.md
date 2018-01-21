Title: Expat Internals: A Simple Parse
Date: 23 June 2017
License: MIT
Category: Maintenance
Tags: internal, walkthrough
Author: Rhodri James
Summary: A walk-through of parsing some simple XML

_Written by Rhodri James_

# Expat Internals: A Simple Parse

This is the first in a series of articles intended to demystify the
internal workings of the Expat library.  Expat is very densely written
and full of clever tricks to parse input quickly and efficiently.
Unfortunately this makes it very hard to read and understand,
particularly when multiple layers of macros obscure what is going on.
This article is intended for people who would like to help out by
working on the code, but who find the complexity difficult to deal
with.

To do this, we will walk through a parse of a simple bit of XML and
show you how the library hangs together.  If you want, you can fire up
`gdb` and follow the code paths yourself.  We won't go through every
line in detail, just enough to give you a handle on how Expat works.

This article assumes that you already know how to use Expat to parse
XML.  If you don't, I recommend you at least read the [introductory
article](https://www.xml.com/pub/1999/09/expat/index.html) mentioned
on the [Getting Started page](../getting-started/).

First, a warning.  I am British, and so is my spelling.  I bend the
knee<sup>[1](#bendknee)</sup> for words like "program" where the US
spelling is considered appropriate in IT, but I insist on the right
spelling of "prologue" and the like.  I also tend to write in mildly
whimsical idiomatic English.  Fortunately for you lot, Sebastian (the
maintainer, bug-fixer and Grand Poobah<sup>[2](#poobah)</sup> of
Expat) is German, and has this distressing habit of asking me what I
actually mean.  Expect footnotes.

## The Setup

We will work with the following few lines of XML:

    :::xml
    <doc>
      <element>One</element>
    </doc>

If you want to follow along, save that into a file (say
`~/test/simple.xml`), compile the `outline` example program and run
it.

    :::sh
    $ make examples/outline
    $ examples/outline < ~/test/simple.xml
    doc
      element

Let's assume that we've created our parser, registered all the
handlers we want to use, and read in the file.  We pick up the story
as we call `XML_Parse()`, passing the whole file in one go.

## Initial Parsing State

We first indulge ourselves with a little defensive programming:

    :::c
    enum XML_Status XMLCALL
    XML_Parse(XML_Parser parser, const char *s, int len, int isFinal)
    {
      if ((parser == NULL) || (len < 0) || ((s == NULL) && (len != 0))) {
        if (parser != NULL)
          parser->m_errorCode = XML_ERROR_INVALID_ARGUMENT;
        return XML_STATUS_ERROR;
      }
      switch (parser->m_parsingStatus.parsing) {
      ...

`XML_Parse()` is called by users, who are notoriously lackadaisical
and apt to forget that they are supposed to give us correctly-formed
arguments.  We therefore check to see if our input is nonsensical,
and if it is we will return `XML_STATUS_ERROR` and, if possible, set
the `m_errorCode` of the parser structure to something meaningful, in
this case `XML_ERROR_INVALID_ARGUMENT`.  This is kinder than producing
alarming address exceptions when we attempt to access non-existant
memory and the like.

After that, we examine the current overall state of the parser, held
in the parser field `parser->m_parsingStatus.parsing`.  Since we have
a newly-created parser structure that hasn't done any parsing yet, it
is in the `XML_INITIALIZED` state.  That results in a call to the
function `startParsing()` which creates the salt value used by the
hash function.  While that is a fascinating exercise all on its own,
it is beyond the scope of what we want to look at in this article.
Let's just assert that it is successful and move on.

Once we have started the parser, we naturally update the parser state
to `XML_PARSING`.  Then, assuming we actually have some input (`len`
is not zero) and libexpat has been compiled in the usual way
(i.e. `XML_CONTEXT_BYTES` is defined) we have the following bit of
code:

    :::c
    void *buff = XML_GetBuffer(parser, len);
    if (buff == NULL)
      return XML_STATUS_ERROR;
    else {
      memcpy(buff, s, len);
      return XML_ParseBuffer(parser, len, isFinal);
    }

At first sight, this looks like it allocates a buffer big enough for
the text to be parsed, copies the input into it and then does the
parse, somehow mysteriously having access to the same buffer.  Why,
you might ask, are we wasting time and memory copying perfectly good
text into a new buffer?

What's actually going on is a little more complicated.
`XML_GetBuffer()` in fact extends the parser's internal buffer so
that it has enough space for the text to be parsed _as well as anything
that is already in the buffer,_ and returns a pointer to this new
space.  In our case we have no previous text, but this really comes
into its own when parsing large files that can't be read in one go.
The library user can just call `XML_Parse()` on each chunk of the
input in turn, without having to worry about each chunk ending in some
convenient place.  The library handles all that behind the scenes,
storing enough context in the internal buffer that it can resume the
parse from any point.

## XML_ParseBuffer: Parsing Starts Here

The first thing we see in `XML_ParseBuffer()` is the same dance with
the parsing state as we saw before.  This time our state is
`XML_PARSING` so we drop straight through with no more ado.

There is then a lot of setting of pointer variables, mostly in parser
fields.  The important lesson to take away from this section is that
the parser deals with its input through start and end pointers, rather
than NUL termination.  This is particularly important when the input
is UTF-16 or similar, and zero bytes can be expected quite frequently
in the input.

Then we call `parser->m_processor()` to do the actual parsing.  There
are in fact several processor functions, which provide the high-level
syntax handling for different situations during parsing.  We start off
with `prologInitProcessor()`, the processor that handles the start-up
of parsing and allows for
an
[XML prologue](https://www.w3.org/TR/2000/REC-xml-20001006#sec-prolog-dtd) to
be present.  This does some more initialisation, this time setting up
the character encoding to use before palming<sup>[3](#palm)</sup> the
rest of the work off onto `prologProcessor()`.  We will discuss encodings
in another article; for now, all we need to know is that we haven't
told the parser in advance what encoding will be used, so it will try
to deduce the answer from the input text.  The default assumption is
that the input will
be [UTF-8 encoded](https://en.wikipedia.org/wiki/UTF-8).

`prologProcessor()` starts off by calling `XmlPrologTok()`.  You
will look long and hard for a function by that name; it's actually a
macro hiding one of several function pointers held in the encoding
structure that invokes an appropriate tokenizer.  The tokenizer's job
is to split the input into its lexical units and convert it to an
internal character format, in this case UTF-8.  If the library had
been compiled with `XML_UNICODE` defined, it would be UTF-16.

At the start of parse, we don't know exactly what character encoding
we have, so we _scan_ the input for clues rather than consuming it and
spitting out tokens.  That means `XmlPrologTok()` initially points us
to the function `initScanProlog()`, which can be found in the file
`xmltok_ns.c`.  This may look a little peculiar to you.  Time for
another digression.

## Included Sources

When you look for `initScanProlog()` in the sources, you find
something that looks a little odd.  The definition actually says
`NS(initScanProlog)`, which looks like the function name is being
wrapped by a macro for no particular reason.

There is in fact a good reason for this; `xmltok_ns.c` isn't passed
directly to the compiler.  Instead it is included in `xmltok.c` twice,
with different definitions of the `NS()` and `ns()` macros, to provide
appropriate functions depending on whether or not the parser was told
to expect XML namespaces when it was created.  Namespaces are a can of
worms for another day, so we'll assume for now that we created a
parser without them.

There is a good reason for this somewhat confusing behaviour.  The
biggest benefit is that if you discover a bug in your code, you only
have to fix it once.  There is no chance of the namespace and
non-namespace versions of the code getting out of step, because they
are the _same_ code template.  On the minus side, it becomes harder to
read the code and be sure what is going to happen.

Hang on to your hats<sup>[4](#hats)</sup>, it's about to become a lot
more confusing.

The same thing happens with the tokenizer functions in
`xmltok_impl.c`, except that they are included three times for the
three different types of encodings; "normal" (8-bit, including UTF-8,
ASCII, and Latin-1), "big2" (big-endian UTF-16) and "little2"
(UTF-16).  A huge number of macros get defined to make this work, some
of them redirecting to dedicated functions and some to other macros,
sometimes via function tables and sometimes not.  It's horribly
confusing and hard to follow, even using breakpoint debugging.

Follow me down the rabbit-hole<sup>[5](#rabbit)</sup>.  I won't mind
if you lie down and whimper every now and then.  I did.

## Scanning for the encoding

Back to our parse.  `initScanProlog()` throws us to `initScan()`,
which mercifully is just a normal function.  This looks through the
first few bytes of the input for a clue as to what encoding is being
used.  We start by assembling the first two bytes into a sixteen-bit
value to see if we get a byte order mark or a UTF-16 encoding of "<",
which we don't.  We conclude that we probably have UTF-8 input, the
parser's default guess.

Once that is done, we get passed to the real tokenizer, `XmlTok()`.
Sad to say, this is another macro, this time passing us to
`normal_prologTok()`, which is one of the multiply-included tokenizer
functions I warned you about.  This tokenizer is tuned to recognise
things that should appear at the very start of a piece of XML.  It
starts off much like every other tokenizer.

    :::c
    if (ptr >= end)
      return XML_TOK_NONE

First it checks if there is anything to parse, i.e. that the start of
the input `ptr` hasn't reached the end of the input at `end`.

    :::c
    if (MINBPC(enc) > 1) {
      size_t n = end - ptr;
      if (n & (MINBPC(enc) - 1)) {
        n &= ~(MINBPC(enc) - 1);
        if (n == 0)
          return XML_TOK_PARTIAL;
        end = ptr + n;
      }
    }

Then it makes sure that it only deals with whole character units; the
macro `MINBPC` returns the minimum number of bytes required to
represent a single character in the encoding we are using.  The
relationship between characters and bytes is somewhat complicated, but
every character encoding has such a minimum number of bytes.  Limited
encodings like ASCII or Latin-1 only use one byte to encode
characters, and cannot represent anything else.  UTF-8 uses between
one and four bytes for any Unicode character; its `MINBPC` is 1.
UTF-16 by contrast uses sixteen bits (two bytes) to represent the most
common Unicode characters and four bytes for all the rest, so its
`MINBPC` is 2.  Expat doesn't support UTF-32, but if it did the
encoding would have a `MINBPC` of 4.

The code rounds the length of the input down to be an integer number
of `MINBPC` "units", and the `end` pointer is adjusted accordingly.  This
does not mean that the (potentially shortened) input will only contain
whole characters &mdash; it could for example end with the first two
bytes of a four-byte UTF-16 character &mdash; but it does guarantee
that there will be enough information for the code to decide whether
it has a complete character at the end or not.  For our simple ASCII
input this makes no difference at all, since all of the characters are
one byte long.

    :::c
    switch (BYTE_TYPE(enc, ptr) {

Then the code looks at the first character of our XML, "<", and passes
it to the macro `BYTE_TYPE`.  This is a bit of a nightmare to
untangle, but after some digging through `xmltok.c` you can figure out
that what you actually have is:

    :::c
    #define BYTE_TYPE(enc, p) SB_BYTE_TYPE(enc, p)
    #define SB_BYTE_TYPE(enc, p) \
      (((struct normal_encoding *)(enc))->type[(unsigned char)*(p)])

In other words, we look up the character in the `type` array of the
encoding.  That constant array is constructed in `xmltok.c` using
include files.  The UTF-8 encoding uses `asciitab.h` for characters
0x00 to 0x7f, and `utf8tab.h` for characters 0x80 to 0xff.  If you
look up "<" (0x3c) in `asciitab.h`, you will find it listed as `BT_LT`
(Byte Type Less Than, obviously).

    :::c
    case BT_LT:
      {
        ptr += MINBPC(enc);
        REQUIRE_CHAR(enc, ptr, end);
        switch (BYTE_TYPE(enc, ptr)) {

`normal_prologTok()` reacts to that by moving on to the next character
and ensuring that there is one.  The `REQUIRE_CHAR` macro is defined
at the top of the file, and returns the value `XML_TOK_PARTIAL` if
there isn't at least one character left in the input.  Fortunately for
us there is, so we don't have to deal with that unexpected hidden
`return` statement, but bear it in mind for the future: some of the
"convenience" macros in this file can and will exit your function!

    :::
    <doc>
     ^
     +-- ptr

We have a next character, "d", so we find its byte type again.  This
is a `BT_HEX`, a character that could legitimately be a hexadecimal
digit.  It can also legitimately be the start of an XML element name,
which is the important thing here.

    :::c
    case BT_HEX:
      /* ... */
      *nextTokPtr = ptr - MINBPC(enc);
      return XML_TOK_INSTANCE_START;

The tokenizer recognises "<d" as the potential start of a name, sets
the "next token" pointer back to the opening angle bracket and returns
`XML_TOK_INSTANCE_START`.  You'll notice that it doesn't try to parse
the element itself.  That's because this is the _prologue_ tokenizer,
and having a normal element means that we must have finished the
prologue and be into the main content of the XML &mdash; an XML
prologue can only legitimately contain an XML declaration, processing
instructions (both starting with "<?"), a document type declaration or
comments (both starting with "<!").  Since our example XML has no
prologue at all, we can be happy that the parser got this right!

## Processing the Token

    :::
    <doc>
    ^
    +-- s, next

We return all the way back to `prologProcessor()`, which now has its
variable `next` pointing to the "<".  It then calls `doProlog()`,
which decides what the `XML_TOK_INSTANCE_START` actually means in this
context.

    :::c
    for (;;) {
      int role;
      XML_Bool handleDefault = XML_TRUE;
      *eventPP = s;
      *eventEndPP = next;
      if (tok <= 0) {
        /* ... */

The function starts by doing some housekeeping with event pointers,
which we will ignore for the moment. Then it does something slightly
odd-looking; it tests to see if the token is a negative number.

Tokens inside Expat are generally positive numbers.  A few are
specifically negative to indicate an error condition, such as
`XML_TOK_INVALID`.  However the tokenizers will also return the
negative of a positive token if they think the input will parse to a
particular token but just hasn't got there yet.  For instance, a
quoted string is recognised with the token `XML_TOK_LITERAL`.  If a
tokenizer recognises an opening quote and doesn't see a closing quote,
it will instead return `-XML_TOK_LITERAL` and leave the processor
function to decide whether or not that is good enough.  In our case we
have `XML_TOK_INSTANCE_START`, which is positive and skips all of that
decision logic.

    :::c
    role = XmlTokenRole(&parser->m_prologState, tok, s, next, enc);
    switch (role) {

Instead, `doProlog()` calls `XmlTokenRole()` to find out what role the
token plays here at the start of our XML.  If you looked at that
function name and wondered if it was another of the macros hiding a
function pointer, give yourself a pat on the back.  It calls the
function pointer `handler` in `parser->m_prologState`.

These handler functions effectively implement a state machine for the
parser.  We start off in `prolog0`.

    :::c
    static int PTRCALL
    prolog0(PROLOG_STATE *state,
            int tok,
            const char *ptr,
            const char *end,
            const ENCODING *enc)
    {
      switch (tok) {
      /* ... */
      case XML_TOK_INSTANCE_START:
        state->handler = error;
        return XML_ROLE_INSTANCE_START;

`prolog0` turns our token into `XML_ROLE_INSTANCE_START` and
transitions to `error`.  This is a bit of insurance against the
parser's internal logic failing.  `prolog0` knows that the start of an
element means that we have no more prologue, so the prologue handler
shouldn't be called again in this parse.  The `error` handler is there
to return an error if this ever happens.

The big switch statement in `doProlog()` drops us into a large
wodge<sup>[6](#wodge)</sup> of code that only kicks into life if we
had set the parser up to want an external DTD.  We didn't do that, so
it skips down:

    :::c
    case XML_ROLE_INSTANCE_START:
      /* useForeignDTD stuff... */
      parser->m_processor = contentProcessor;
      return contentProcessor(parser, s, end, nextPtr);

Setting `m_processor` field of the parser structure to
`contentProcessor` signals the end of the XML prologue and the start of
the actual content of our XML.  The parser could at this point return
and let `XML_ParseBuffer()` go round its loop, doing the housekeeping
and then calling the processor function again.  As an optimisation, it
calls `contentProcessor()` directly from here.

## Parsing the Content

    :::c
    for (;;) {
      const char *next = s;
      int tok = XmlContentTok(enc, s, end, &next);
      *eventEndPP = next;
      switch (tok) {

`contentProcessor()` immediately
palms<sup>[3](#palm)</sup> the hard work off on
`doContent()`, the main workhorse function of the parser.  Like
`doProlog()`, it starts by fiddling with the event pointers.  In
content processing the tokenizer has not been called in advance, so
the processor then calls the tokenizer `XmlContentTok()`, yet another
macro hiding a function pointer in the encoding structure which throws
us into `normal_contentTok()`.

    :::c
    static int PTRCALL
    PREFIX(contentTok)(const ENCODING *enc, const char *ptr,
                       const char *end,
                       const char **nextTokPtr)
    {
      if (ptr >= end)
        return XML_TOK_NONE;
      if (MINBPC(enc) > 1) {
        /* ... */
      }
      switch (BYTE_TYPE(enc, ptr)) {
      case BT_LT:
        return PREFIX(scanLt)(enc, ptr + MINBPC(enc), end, nextTokPtr);

`normal_contentTok()` starts out identically to `normal_prologTok()`,
checking if there is anything to parse, adjusting the `end` pointer so
that it only deals in whole characters and switching on the byte type
of the first character, which is again `BT_LT`.  However in this case
it hands the work of dealing with an XML element off to a
sub-function, `normal_scanLt()`.

    :::c
    static int PTRCALL
    PREFIX(scanLt)(const ENCODING *enc, const char *ptr, const char *end,
                   const char **nextTokPtr)
    {
    #ifdef XML_NS
      int hadColon;
    #endif
      REQUIRE_CHAR(enc, ptr, end);
      switch (BYTE_TYPE(enc, ptr)) {
      CHECK_NMSTRT_CASES(enc, ptr, end, nextTokPtr)

The first thing `normal_scanLt()` does is to ensure that there is a
character there for it to check, using `REQUIRE_CHAR`.

    :::
    <doc>
     ^
     +-- ptr

There is, so it switches on the character type `BT_HEX`, just as the
prologue tokenizer did.  You might hope at this point to see `case
BT_HEX` in the source, but alas life is not so simple.  There are many
byte types that may be legal at the start of an XML name, and in
particular multi-byte characters in UTF-8 may or may not be legal.  In
order to cover all these cases without replicating code everywhere, we
descend into macro madness.

## Macro Abuse

The `CHECK_NMSTRT_CASES` macro is a horrible, tangled thing that knows
it is part of a switch statement, and like `REQUIRE_CHAR` can exit the
function without further ado.  Let's make it a little more
comprehensible by substituting the `CHECK_NMSTART_CASE` macros in as
well:

    :::c
    case BT_NONASCII:
      if (!IS_NMSTRT_CHAR_MINBPC(enc, ptr)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }

    case BT_NMSTRT:
    case BT_HEX:
      ptr += MINBPC(enc);
      break;

    case BT_LEAD2:
      if (end - ptr < 2)
        return XML_TOK_PARTIAL_CHAR;
      if (!IS_NMSTRT_CHAR(enc, ptr, 2)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 2;
      break;

    case BT_LEAD3:
      if (end - ptr < 3)
        return XML_TOK_PARTIAL_CHAR;
      if (!IS_NMSTRT_CHAR(enc, ptr, 3)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 3;
      break;

    case BT_LEAD4:
      if (end - ptr < 4)
        return XML_TOK_PARTIAL_CHAR;
      if (!IS_NMSTRT_CHAR(enc, ptr, 4)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 4;
      break;

Let's take those last cases first.  `BT_LEAD4` indicates a character
that is the start of a sequence of four bytes.  Note that here we are
talking about bytes, not units of `MINBPC`, which can be a little
confusing when the input is UTF-16.  The code in this case checks that
there are at least four bytes in the input, then invokes the
`IS_NMSTRT_CHAR` macro to determine if this four-byte sequence could
start a name.  This is a cunning wrapper for the `isNmstrt4` function
pointer in the encoding.

We can find out what function `enc->isNmstrt4()` translates to by
looking up the encoding table, `utf8_encoding`.  This is not as easy
as it sounds because of the helpful macros used in the table
construction, but a little persistence shows us that the function is
named `utf8_isNmstrt4()`.  A little more persistence tells us that
this is not quite true; `utf8_isNmstrt4()` is a macro disguise for
`isNever()`, a function that always returns False.  This makes sense,
since none of the characters encoded as four bytes in UTF-8 are valid
starts of names.

`BT_LEAD3` similarly indicates a character that is the start of a
sequence of three bytes.  Its case checks that there are at least
three bytes available, then calls through the `isNmstrt3` function
pointer in the encoding.  This time `utf8_isNmstrt3()` as it becomes
is a real function, one that uses macros to turn the UTF-8 into
a [Unicode codepoint](http://unicode.org/glossary/#code_point) and
look up that codepoint (an integer in the range 0&ndash;1114111
(0x10ffff in hexadecimal), or rather 2048&ndash;65535
(0x0800&ndash;0xffff in hex) given that it comes from a three-byte
UTF-8 sequence<sup>[7](#utf83)</sup>) in a large bit array.  If the
corresponding bit is set, that Unicode character is a valid
start-of-name character.

`BT_LEAD2` works just like `BT_LEAD3`, just with two-byte
sequences.

`BT_HEX` and `BT_NMSTRT` are easy.  The first one is a letter that
could be a valid hexadecimal digit, i.e. "a" or "f" or "A" to "F".
The second is any other letter.  In both cases we just accept them as
valid and move the parse pointer on, which is what actually happens in
our example parse.

Finally, `BT_NONASCII` is an odd case that only crops up in UTF-16
encodings.  It indicates a 16-bit character that is out of the ASCII
range, isn't the leading or trailing half of a surrogate pair, and
isn't an invalid character (0xffff or 0xfffe).  The code calls
`IS_NMSTRT_CHAR_MINBPC` very much like the leading character cases
call `IS_NMSTRT_CHAR`.  Working through the nest of conditional
compilations in `xmltok.c`, `IS_NMSTRT_CHAR_MINBPC` turns out to
always return 0 for "normal" encodings, so for us a `BT_NONASCII`
character would always be invalid.

## Back to the Parser

So we were parsing the first character of our XML element, "d", which
has a byte type of `BT_HEX`.  The `CHECK_NMSTRT_CASES` macro accepts
that byte type as described above, and moves the parse pointer on:

    :::
    <doc>
      ^
      +-- ptr

It also clears a local variable `hadColon`, a flag used in parsing
namespaces.  There are no namespaces in our input text (i.e. no colons
in any names), so we can ignore it for now.

    :::c
    /* we have a start-tag */
    while (HAS_CHAR(enc, ptr, end)) {
      switch (BYTE_TYPE(enc, ptr)) {
      CHECK_NAME_CASES(enc, ptr, end, nextTokPtr)

We then drop into a `while` loop, the condition being that we have at
least one more character to examine.  We do, so we examine the
`BYTE_TYPE` of the next character, "o".  It's a `BT_NMSTRT`, and like
the `BT_HEX` before it's swept up by `CHECK_NAME_CASES`, a macro very
much like `CHECK_NMSTRT_CASES` except allowing a few more byte types
through.  It accepts the character and moves the parse pointer on.

    :::
    <doc>
       ^
       +-- ptr

The same thing happens for the "c", except that it's a `BT_HEX` again.

    :::
    <doc>
        ^
        +-- ptr

The ">" has a byte type of `BT_GT`, which has its own case at last.

    :::c
    case BT_GT:
    gt:
      *nextTokPtr = ptr + MINBPC(enc);
      return XML_TOK_START_TAG_NO_ATTS;

(Don't be confused by the `gt:` in the code.  It's a jump label, the
result of a possibly slightly overenthusiastic bit of optimisation.)

The function sets the "next token" pointer to the character following
the ">" (the newline at the end of the line), and returns
`XML_TOK_START_TAG_NO_ATTS`.  A start tag (element) with no attributes
is exactly what this is.

## We Have An Element, Now What?

    :::
    <doc>
    ^    ^
    |    +-- next
    +-- ptr

We return out to `doContent()`, which promptly switches on the token
that has been returned.  `XML_TOK_START_TAG_NO_ATTS` leads us to a
large chunk of code that introduces another efficiency saving that the
parser implements.  Fortunately this one is quite obvious.

    :::c
    case XML_TOK_START_TAG_NO_ATTS:
      /* fall through */
    case XML_TOK_START_TAG_WITH_ATTS:
      {
        TAG *tag;
        enum XML_Error result;
        XML_Char *toPtr;
        if (parser->m_freeTagList) {
          tag = parser->m_freeTagList;
          parser->m_freeTagList = parser->m_freeTagList->parent;
        }
        else {
          tag = (TAG *)MALLOC(parser, sizeof(TAG));
          if (!tag)
            return XML_ERROR_NO_MEMORY;
          tag->buf = (char *)MALLOC(parser, INIT_TAG_BUF_SIZE);
          if (!tag->buf) {
            FREE(tag);
            return XML_ERROR_NO_MEMORY;
          }
          tag->bufEnd = tag->buf + INIT_TAG_BUF_SIZE;
        }

We want to allocate a TAG structure to hold information about our
element, so that for example we can recognise its close tag.  We are
going to need to do this many times for a long parse, freeing the TAG
structure once we are done with the element.  This means going back to
the heap allocators a lot, which is not necessarily an efficient thing
to do.  So instead of freeing the TAG structures, the parser keeps
them on a linked list on the `m_freeTagList` field of the parser
structure, avoiding all that expensive allocation.

In this case, this is our first TAG structure, so there is nothing on
the free list for us to reuse, so we have to allocate anyway, using
`MALLOC()`.

## A Digression Into Allocation

`MALLOC()` is of course a macro, hiding a function pointer in the
parser structure.  There are three of these: `MALLOC()`, `REALLOC()`
and `FREE()`.  They are used for all allocations in the parser (and
for consistency are made available to user-defined handler functions
through the `XML_MemMalloc()`, `XML_MemRealloc()` and `XML_MemFree()`
functions).  This allows us to plug in custom allocators used by the
whole parser, for example to track heap usage levels or test error
handling.

We didn't specify a set of allocation functions when we created our
parser, so we got the standard system `malloc()`, `realloc()` and
`free()` by default.

## Back to the Parse

The myriad fields of the TAG structure are then set up for our "doc"
element.  Things to notice are that the `rawName` is actually a
pointer into the input text (so the function calculating its length is
yet another macro-masked affair looking a lot like the tokenizer
functions), and that TAGs are held on a linked list, parent to child,
attached to the parser structure.  The actual name of the tag is then
copied into the TAG's buffer using `XmlConvert()`, yet another macro
masking a function pointer in the encoder structure.

    :::c
    static enum XML_Convert_Result PTRCALL
    utf8_toUtf8(const ENCODING *UNUSED_P(enc),
                const char **fromP, const char *fromLim,
                char **toP, const char *toLim)
    {
      bool input_incomplete = false;
      bool output_exhausted = false;

      /* Avoid copying partial characters (due to limited space). */
      const ptrdiff_t bytesAvailable = fromLim - *fromP;
      const ptrdiff_t bytesStorable = toLim - *toP;
      if (bytesAvailable > bytsStorable) {
        fromLim = *fromP + bytesStorable;
        output_exhausted = true;
      }

      /* Avoid copying partial characters (from incomplete input). */
      {
        const char * const fromLimBefore = fromLim;
        _INTERNAL_trim_to_complete_utf8_characters(*fromP, &fromLim);
        if (fromLim < fromLimBefore) {
          input_incomplete = true;
        }
      }

      {
        const ptrdiff_t bytesToCopy = fromLim - *fromP;
        memcpy(*toP, *fromP, bytesToCopy);
        *fromP += bytesToCopy;
        *toP += bytesToCopy;
      }

      if (output_exhausted) /* needs to go first */
        return XML_CONVERT_OUTPUT_EXHAUSTED;
      else if (input_incomplete)
        return XML_CONVERT_INPUT_INCOMPLETE;
      else
        return XML_CONVERT_COMPLETED;
    }

This sends us to the function `utf8_toUtf8()`, which sounds like an
identity function.  It isn't quite; it makes allowance for not having
enough space in the destination buffer for the whole of the source
string.  All of the conversion functions do this, returning
`XML_CONVERT_INPUT_INCOMPLETE` if the input hasn't been exhausted,
`XML_CONVERT_OUTPUT_EXHAUSTED` if the output has been filled (not
necessarily the same thing if multi-byte characters are involved), or
`XML_CONVERT_COMPLETED` if all is well.  The calling code will do some
shuffling and reallocation if the TAG buffer was too small, and
similar code can be seen in other places that the conversion functions
are used.

In our case there is plenty of space in the buffer for the element
name, so we simply finish setting up the TAG fields and make sure that
the name has the correct termination for internal format (just a NUL
for our UTF-8).  It also has a length field, for added reassurance and
consistency issues.  Then we call `storeAtts()` to handle the tag's
attributes.

## Strings and Tables

You might hope that the act of parsing our grand total of no
attributes would be pretty simple.  Unfortunately quite a lot of
important internal parser workings get introduced here, in particular
the hash tables and string pools.

    :::c
    /* lookup the element type name */
    elementType = (ELEMENT_TYPE *)lookup(parser, &dtd->elementTypes, tagNamePtr->str,0);
    if (!elementType) {
      const XML_Char *name = poolCopyString(&dtd->pool, tagNamePtr->str);
      if (!name)
        return XML_ERROR_NO_MEMORY;
      elementType = (ELEMENT_TYPE *)lookup(parser, &dtd->elementTypes, name,
                                           sizeof(ELEMENT_TYPE));
      if (!elementType)
        return XML_ERROR_NO_MEMORY;
      if (parser->m_ns && !setElementTypePrefix(parser, elementType))
        return XML_ERROR_NO_MEMORY;
    }
    nDefaultAtts = elementType->nDefaultAtts;

The parser keeps a number of hash tables for various different
purposes.  The one we are concerned with here is the `elementTypes`
table in the DTD substructure of the parser.  If we had a
comprehensive DTD, it might well have had a definition for the `<doc>`
tag complete with a list of attributes, default values and so on.  The
first thing `storeAtts()` does, therefore, is to call `lookup()` to
find out if such a definition exists.  Without going into too much
detail, this searches the hash table for the the name "doc", doesn't
find it (since we have no DTD) and returns a NULL pointer.

Since we don't have a definition for the "doc" tag, the next thing to
do is to create one.  If you recall that we said the element's name is
actually a pointer into it's own buffer.  If we use that pointer as
our key to the hash table, then when the tag is freed and probably
reused, the key could have been changed to anything.  To avoid that,
the code uses `poolCopyString()` to create a copy of the string that
is guaranteed to last for the lifetime of the parser and will be freed
with it.  String pools are a topic worthy of a whole article on their
own, so we won't go into details here.

Once the code has its safe copy of the tag name, it does something
strange-looking; it calls `lookup()` again.  It turns out that
`lookup()` is a bit mis-named; in fact it is the only function used to
interact with the hash tables in normal operation.  If the last
parameter passed to `lookup()` is zero, it returns NULL as mentioned
above if it doesn't find the name.  If instead a non-zero number is
passed, `sizeof(ELEMENT_TYPE)` in this case, it will create a new
entry in the hash table for that name if necessary, and will allocate,
zero and return that many bytes of memory as the entry.  The first
field in the memory is presumed to be a pointer, and will point to the
key name when the memory is returned.  **DO NOT FIDDLE WITH THIS**, it
is important to the way the hash tables work.

    :::c
    /* get the attributes from the tokenizer */
    n = XmlGetAttributes(enc, attStr, parser->m_attsSize, parser->m_atts);

The actual parsing of the attributes is done by `XmlGetAttribute()`,
which by now you should have recognised as being really a function
pointer on the encoder structure.  In our case it directs us to
`normal_getAtts()`.  In the interests of brevity we'll skip through
that, and just note that it returns 0, correctly indicating that we
have no attributes.  With no default attributes from our
lack-of-definition either, the rest of the function consists of not
taking a large number of conditional branches, eventually returning
having done essentially no more.

## Back to the Parse (Again)

    :::c
    if (parser->m_startElementHandler)
      parser->m_startElementHandler(parser->m_handlerArg, tag->name.str,
                                    (const XML_Char **)parser->m_atts);
    else if (parser->m_defaultHandler)
      reportDefault(parser, enc, s, next);
    poolClear(&parser->m_tempPool);
    break;

Back in `doContent()`, there is little more to do for this start
element tag.  This is the point at which the user can intervene with a
start element handler (which indeed the `outline` program does).  Any
temporary strings created in the parser's temporary string pool are
released (don't ask, it _is_ that complicated), and we finally drop
out of the big switch statement.  We run through the parsing state
dance again, doing nothing since we are still `XML_PARSING`, and then
go back to the top of the loop and call `normal_contentTok()` again.

    :::
    <doc>
         ^
         +-- ptr
      <element>One</element>

This time we examine the newline after the `<doc>` tag, which has a
byte type of `BT_LF`.

    :::c
    case BT_LF:
      *nextTokPtr = ptr + MINBPC(enc);
      return XML_TOK_DATA_NEWLINE;

`normal_contentTok()` accepts this and sets the next token pointer to
the space at the start of the next line.

    :::c
    case XML_TOK_DATA_NEWLINE:
      if (parser->m_characterDataHandler) {
        XML_Char c = 0xA;
        parser->m_characterDataHandler(parser->m_handlerArg, &c, 1);
      }
      else if (parser->m_defaultHandler)
        reportDefault(parser, enc, s, next);
      break;

The `XML_TOK_DATA_NEWLINE` return value causes the giant switch
statement to pass a line feed character in the appropriate encoding to
any character data handler the user may have registered.  Another trip
around the parsing state dance and we come back to calling
`normal_contentTok()` again.

    :::
      <element>One</element>
    ^
    +-- ptr

There is nothing special to be done immediately for a space, it turns
out, so `normal_contentTok()` skips past it and starts a loop examining
input characters one by one while there are any left.  The next
character is also a space, and therefore also skipped.  The next is a
"<", which is different, so the function updates the next token
pointer to point to it and returns `XML_TOK_DATA_CHARS`.

    :::c
    case XML_TOK_DATA_CHARS:
      {
        XML_CharacterDataHandler charDataHandler = parser->m_characterDataHandler;
        if (charDataHandler) {
          if (MUST_CONVERT(enc, s)) {
            for (;;) {
              ICHAR *dataPtr = (ICHAR *)parser->m_dataBuf;
              const enum XML_Convert_Result convert_res = XmlConvert(enc, &s, next, &dataPtr, (ICHAR *)parser->m_dataBufEnd);
              *eventEndPP = s;
              charDataHandler(parser->m_handlerArg, parser->m_dataBuf,
                              (int)(dataPtr - (ICHAR *)parser->m_dataBuf));
              if ((convert_res == XML_CONVERT_COMPLETED) || (convert_res == XML_CONVERT_INPUT_INCOMPLETE))
                break;
              *eventPP = s;
            }
          }
          else
            charDataHandler(parser->m_handlerArg,
                            (XML_Char *)s,
                            (int)((XML_Char *)next - (XML_Char *)s));
        }
        else if (parser->m_defaultHandler)
          reportDefault(parser, enc, s, next);
      }
      break;

In this case the data character are all spaces, but they are treated
the same way as any other data characters.  They are converted into
the parser's internal format using `XmlConvert()` as above, assuming
that they need conversion, before being fed to any character data
handler the user may have registered.  As you can see from this,
character data is not necessarily fed to the handler in a single lump.
Here we have fed the newline and the two spaces separately; other
character data may be split up to avoid overflowing the internal
buffer, so it becomes the handler's job to hold whatever state it
needs between invocations.

Then we check the parsing state and loop around again.

    :::
      <element>One</element>
      ^
      +-- ptr

We've already seen how the parser accepts a simple start element tag,
so we don't need to go through that again.  A few more turns around
the loop and we have:

    :::
      <element>One</element>
               ^
               +-- ptr

It turns out that an "O" character (`BT_NMSTRT`) is no more
interesting to `normal_contentTok()` than a space (`BT_S`), so it
behaves in exactly the same way and `doContent()` ends up presenting
the string "One" to the character data handler.  This shows up a
problem with writing handlers; a character data handler on its own
_cannot know_ whether the data it has been handed is a continuation of
the previous data or not.  If we had a handler in this example, it
would have no way of telling that the `"\n"` of the first call was
joined to the `"  "` of the second, but not to the `"One"` of the
third.  It needs help from start and end element handlers to tell what
data should be joined together and what shouldn't.

## End Tags

    :::
      <element>One</element>
                  ^
                  +-- ptr

Moving on, we call `normal_contentTok()` with something a bit
different.  The initial "<" is recognised as a `BT_LT` like before,
causing us to call `normal_scanLt()`.

    :::c
    case BT_SOL:
      return PREFIX(scanEndTag)(enc, ptr + MINBPC(enc), end, nextTokPtr);

Parsing the "/" is a bit different, however; it has a type of
`BT_SOL`<sup>[8](#solidus)</sup>, which drops us into
`normal_scanEndTag()`.

    :::c
    static int PTRCALL
    PREFIX(scanEndTag)(const ENCODING *enc, const char *ptr,
                       const char *end, const char **nextTokPtr)
    {
      REQUIRE_CHAR(enc, ptr, end);
      switch (BYTE_TYPE(enc, ptr)) {
      CHECK_NMSTRT_CASES(enc, ptr, end, nextTokPtr)
      /* ... */
      }
      while (HAS_CHAR(enc, ptr, end)) {
        switch (BYTE_TYPE(end, ptr)) {
        CHECK_NAME_CASES(enc, ptr, end, nextTokPtr)
        /* ... */
        case BT_GT:
          *nextTokPtr = ptr + MINBPC(enc);
          return XML_TOK_END_TAG;

The start-of-parse pointer `ptr` has been moved on:

    :::
      <element>One</element>
                    ^
                    +-- ptr

so `normal_scanEndTag()` first looks at the "e" of "element".  Through
the magic of `CHECK_NMSTRT_CASES()` it regards the "e" as acceptable
and moves the pointer on.  It then loops through the remaining
characters, accepting them through `CHECK_NAME_CASES()` until it
finally reaches the ">".  It sets the "next token" pointer to the
newline after the ">" and returns `XML_TOK_END_TAG` all the way back
to `doContent()`.

    :::c
    case XML_TOK_END_TAG:
      if (parser->m_tagLevel == startTagLevel)
        return XML_ERROR_ASYNC_ENTITY;

The first thing `doContent()` does with an `XML_TOK_END_TAG` is to
check that it hasn't closed more tags than it opened.  This could
happen, for example if an overly-optimistic general entity expanded to
an end tag.  The XML document

    :::xml
    <?xml version="1.0"?>
    <!DOCTYPE foodoc [
      <!ENTITY foo "<b>text</b></a>">
    ]>
    <a>&foo;

trips exactly this test, while

    :::xml
    <?xml version="1.0"?>
    <!DOCTYPE foodoc [
      <!ENTITY foo "<b>text</b>">
    ]>
    <a>&foo;</a>

is just fine.  In any case we don't have that problem; we have opened
two tags and are closing one for the first time.

    :::c
    TAG *tag = parser->m_tagStack;
    parser->m_tagStack = tag->parent;
    tag->parent = parser->m_freeTagList;
    parser->m_freeTagList = tag;
    rawName = s + enc->minBytesPerChar*2;
    len = XmlNameLength(enc, rawName);
    if (len != tag->rawNameLength
        || memcmp(tag->rawName, rawName, len) != 0) {
      *eventPP = rawName;
      return XML_ERROR_TAG_MISMATCH;
    }
    --parser->m_tagLevel;

Confident that we are least starting off on the right foot, the parser
pops the last tag structure off its list and compares its name to the
tag name that it just parsed.  This is done as a byte-by-byte
comparison of the input strings (recall that `tag->rawName` points
into the input buffer), so no substitution of equivalent characters or
character sequences can be done.  It also has implications for how
much of the input must be held in the internal buffer, unless we do
something about it.  Remember that for later.

The names match in our case, so the parser calls any end element
handler the user may have registered and tidies up.  That is
straightforward in our case; we have no namespace bindings confusing
the issue, and we aren't the root tag.

    :::
      <element>One</element>
                            ^
                            +-- ptr
    </doc>

Next we have the newline, which again is just passed to the character
data handler.

    :::
    </doc>
    ^
    +-- ptr

Finally the end tag for the `doc` element.  Unsurprisingly this works
exactly as the end tag for the `element` element up to the point of
tidying up.  At this juncture `doContent()` realises that it has
closed the last open tag, and calls `epilogProcessor()` to handle any
remaining input.  Very little is permitted by the XML standard at this
point; only comments, processing instructions and whitespace.

    :::c
    static enum XML_Error PTRCALL
    epilogProcessor(XML_Parser parser,
                    const char *s,
                    const char *end,
                    const char **nextPtr)
    {
      parser->m_processor = epilogProcessor;
      parser->m_eventPtr = s;
      for (;;) {
        const char *next = NULL;
        int tok = XmlPrologTok(parser->m_encoding, s, end, &next);
        parser->m_eventEndPtr = next;
        switch (tok) {

`epilogProcessor()` is the last processor that will be invoked in a
parser, so the first thing it does is to make itself the current
processor function.  Then it loops through the remaining input,
calling `normal_prologTok()` to find out what is there.  Comments,
processing instructions and whitespace is fine; anything else is an
error.  We have nothing but a single newline, which the processor
happily consumes.

    :::c
    if (result == XML_ERROR_NONE) {
      if (!storeRawNames(parser))
        return XML_ERROR_NO_MEMORY;
    }
    return result;

Finally we exit back to `contentProcessor()` with a success, so it
calls `storeRawNames()`.  As you might imagine, this fixes the problem
we noted earlier about needing to keep the whole of the input in our
internal buffer so that we have the raw tag names for comparisons.  It
does this by stashing the raw names in the tag's internal buffer after
the tag name as rendered in the internal encoding, allocating more
space if needed.  It also fixes up all the pointers to make this an
invisible change outside the TAG structure itself.

In our case there are no open tags remaining, so `storeRawNames()` has
nothing to do.  We return, eventually arriving back in
`XML_ParseBuffer()` with a success, `XML_ERROR_NONE`.  One final time
we do the parsing state dance, but it's slightly different this time.
Because we fed the whole input into `XML_Parse` in one go, the
`isFinal` flag is true, so we change the parse state to `XML_FINISHED`
to make sure the parser will complain if we try to use it again.  When
we return this time, we return right the way out of the library to the
user code, still indicating success.

## Conclusions

So there you have it.  A quick skip through the Expat parser in action
in only 7,000 words.  While we used a pretty simple example, most of
the general principles you can see in action here apply more generally
to how the code works.  The important observations to take away from
this are:

* Macro abuse is rife:
    * Most (but not all) functions starting with `Xml` are in fact
      macros going through the function table in a character encoding.
    * Some macros can return from a function without warning.
    * Source files `xmltok_ns.c` and `xmltok_impl.c` get included
      multiple times in `xmltok.c` with different macro definitions.
* There are two levels of parsing:
    * _tokenizers_ determine what is in the input stream, and
      frequently vary according to the input character encoding as a
      result.
    * _processors_ determine what the tokens mean in context.  They
      often use _handler_ functions to implement a state machine.
* Hash tables are used internally for efficient storage and lookup.
* String pools are used for a variety of temporary and permanent
  copies of strings.

I plan to write more articles of this type in the future, including
in-depth looks at some of the more complex mechanisms in the parser
such as hash tables, and walkthroughs of more complex XML. Please let
me know if you would like an explanation of anything in particular.

---

## Footnotes

<a name="bendknee">1</a>: to kneel or submit, figuratively in this
case.  A relic of our feudal past.

<a name="poobah">2</a>: a humorous title derived from the character
Pooh-Bah in Gilbert and Sullivan's opera _The Mikado_, who listed
among his various titles "Lord High Everything Else".  Sometimes used
to mock overly self-important people, but Sebastian really does do
everything else!

<a name="palm">3</a>: "to palm something off on someone" means to pass
responsibility for something to someone.  It is usually used in the
sense of selling a fake or counterfeit object, though not here.

<a name="hats">4</a>: get ready for a surprise.  Comes from the days
when men commonly wore hats (think of all those fedora-wearing private
eyes and investigative reporters of the pulp-era stories and films),
and you would need to hold on to it if you took a wild journey in an
open-topped car.

<a name="rabbit">5</a>: _Alice in Wonderland_ by Lewis Carroll.  If
you needed this footnote, go and add to your education immediately.

<a name="wodge">6</a>: an undefined but significant amount of
something.

<a name="utf83">7</a>: UTF-8 encodes codepoints U+0800 to U+FFFF into
three bytes as follows:

    :::
    1110xxxx 10xxxxxx 10xxxxxx

So U+FFFF would become the sequence `0xEF 0xBF 0xBF`.

<a name="solidus">8</a>: "solidus" is the proper technical name for a
slash that no one ever uses.  Erm, maybe I should rephrase that...

&mdash;Rhodri James, 23rd June 2017
