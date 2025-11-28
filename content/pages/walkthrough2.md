Title: Expat Internals: Parsing XML Declarations
Date: 21 October 2017
License: MIT
Category: Maintenance
Tags: internal, walkthrough
Author: Rhodri James
Summary: A walk-through of parsing an XML declaration
Slug: expat-internals-parsing-xml-declarations

_Written by Rhodri James_


This article follows on from the [first
walkthrough](../expat-internals-a-simple-parse/) of the parser's
internal workings.  Instead of the very simple piece of XML that we
saw last time, we will look at the common opening of an XML document,
the [XML
declaration](https://www.w3.org/TR/2008/REC-xml-20081126/#sec-prolog-dtd).
I am going to assume that you have read the
[walkthrough](../expat-internals-a-simple-parse/) and are familiar
with the weird and wonderful world of Expat's macros and
multiply-included source files.

As before, you are welcome to fire up `gdb` and follow the code paths
yourself as you read the article.  You will need to copy the following
lines of XML to a file:

    :::xml
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
    <doc>Hello, world</doc>

and compile and run the `outline` example program on it.


## What Is An XML Declaration?

An _XML declaration_ is part of the
[prologue](https://www.w3.org/TR/2008/REC-xml-20081126/#sec-prolog-dtd)
of an XML document, the part that defines the structure of the rest of
the document.  It specifies which version of the XML standard is being
used, what character encoding is being used, and whether the document
stands alone or expects to use external resources.  If it is present,
the XML declaration must appear first, right at the start of the
input.

Before we start, it's worth looking into exactly what goes into an XML
declaration.  According to [section 2.8 of the XML
standard](https://www.w3.org/TR/2008/REC-xml-20081126/#sec-prolog-dtd),
an XML declaration is:

    :::
    [23] XMLDecl      ::= '<?xml' VersionInfo EncodingDecl? SDDecl? S? '?>'
    [24] VersionInfo  ::= S 'version' Eq ("'" VersionNum "'" | '"' VersionNum '"')
    [3]  S            ::= (#x20 | #x9 | #xD | #xA)+
    [25] Eq           ::= S? '=' S?
    [26] VersionNum   ::= '1.' [0-9]+
    [80] EncodingDecl ::= S 'encoding' Eq ('"' EncName '"' | "'" EncName "'")
    [81] EncName      ::= [A-Za-z] ([A-Za-z0-9._] | '-')*
    [32] SDDecl       ::= S 'standalone' Eq (("'" ('yes' | 'no') "'") | ('"' ('yes' | 'no') '"'))

(The numbers in square brackets are the production numbers in the
standard, for reference.  Some of them have been dragged in from other
sections.)

This may look confusing if you aren't used to reading
[BNF](https://en.wikipedia.org/wiki/Backus%E2%80%93Naur_form), but in
practise it's quite straightforward.  The particular thing to notice
is that every single literal character listed in these productions can
be encoded in ASCII.  This drastically reduces the amount of work the
parser will have to do converting the input; once it knows it has an
XML declaration, every character that cannot be encoded in ASCII is
invalid.

The other thing to notice is that the "attributes" of the XML
declaration have to occur in a defined order.  The version information
must be present, and must be first.  The encoding declaration must be
next if it is present, and finally the standalone declaration.
Nothing else is allowed.  Again, this drastically simplifies the parsing
logic.

Armed with this information, let's see what the parser makes of our
XML declaration.


## Prologue Parsing

    :::
    <?xml version="1.0"...
    ^
    + ptr

The initial stages of the parse are identical to those of the
[previous walkthrough](../expat-internals-a-simple-parse/): the parser
defaults to assuming that the input will be UTF-8 and `initScan()`
sees no reason in the first few characters of the input to revise that
assumption.  It is only once `normal_prologTok()` takes control that
things start to differ.  The code performs the familiar checks for
whether there is any input and making sure it only has whole
characters, then switches on the byte type of "<".

    :::c
    case BT_LT:
      {
        ptr += MINBPC(enc)
        REQUIRE_CHAR(enc, ptr, end);
        switch (BYTE_TYPE(enc, ptr)) {

As before, "<" is perfectly acceptable, so the code goes on to
consider the next character, "?".  This has a byte type of `BT_QUEST`,
which has its own case in the switch statement:

    :::c
    case BT_QUEST:
      return PREFIX(scanPi)(enc, ptr + MINBPC(enc), end, nextTokPtr);

The sequence of characters "<?" in an XML document either means that
we have an XML declaration, a [text
declaration](https://www.w3.org/TR/2008/REC-xml-20081126/#sec-TextDecl)
or a [processing
instruction](https://www.w3.org/TR/2008/REC-xml-20081126/#sec-pi).
A text declaration is almost identical to an XML declaration, and
takes the place of an XML declaration in an externally parsed entity.
At this point in the parse we treat XML declarations and text
declarations as the same thing, and will sort out the difference
later.

The function `normal_scanPi()` checks to see whether we have a
processing instruction or one of the declarations.

    :::c
    const char *target = ptr;
    REQUIRE_CHAR(enc, ptr, end);
    switch (BYTE_TYPE(enc, ptr)) {
    CHECK_NMSTRT_CASES(enc, ptr, end, nextTokPtr)

The first thing `normal_scanPi()` does is to take a copy of the input
pointer as it is passed in, in our case pointing to the "x" of "xml".
If this text turns out to be a processing instruction the parser will
need to know the name that follows the "<?" characters, called the
_target_ of the processing instruction.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
      ^
      + ptr, target

With the target pointer securely stashed away, we then commence the
familiar trudge<sup>[1](#trudge)</sup> through an XML name.  The macro
`REQUIRE_CHAR()` ensures that there is a character in the buffer to
test, which there is, and we then switch on its byte type.  "x" has a
byte type of `BT_NMSTRT`, meaning a character that can legally start
an XML name. The magic macro `CHECK_NMSTRT_CASES()` accepts this
character and moves `ptr` on to examine the next character.

    :::c
    while (HAS_CHAR(enc, ptr, end)) {
      switch (BYTE_TYPE(enc, ptr)) {
      CHECK_NAME_CASES(enc, ptr, end, nextTokPtr)

We then loop through the following characters, checking that we
continue to have a valid name.  The character "m" and "l", both also
having byte type `BT_NMSTRT`, are considered acceptable for a name by
`CHECK_NAME_CASES()`.  Then we get to the space, which has a byte type
of `BT_S`.

    :::c
    case BT_S: case BT_CR: case BT_LF:
      if (!PREFIX(checkPiTarget)(enc, target, ptr, &tok)) {

The tokenizer regards whitespace as ending the target name.  It
therefore calls `normal_checkPiTarget()` to see what sort of target
name it has; in particular if the name is "xml" (which it is), it's
not a processing instruction at all!


## Target Practise

`normal_checkPiTarget()` has to do something slightly more complicated
than just doing a `strcmp()` of the input text to see if it is "xml".
The XML standard, in an effort to avoid accidents, forbids processing
instructions to have targets that are "XML", "Xml", "xML" or indeed
any combination of different letter cases of the word "xml".  It
therefore returns the correct token for the target, `XML_TOK_PI` or
`XML_TOK_XML_DECL`, through a pointer and its actual return value is a
boolean; 1 (success) for a valid target and 0 (failure) for an invalid
one.

    :::c
    int upper = 0;
    *tokPtr = XML_TOK_PI;

The function keeps a flag to indicate that it has seen an uppercase
(invalid) character.  `upper` will remain zero as long as none of "X",
"M" or "L" are seen in the appropriate character position.

    :::c
    if (end - ptr != MINBPC(enc)*3)
      return 1;

Then the code makes the first obvious check; if the name isn't exactly
three characters long, it can't possibly be "xml" so must be a
processing instruction target.  We do have three characters, so the
parse proceeds.

    :::c
    switch (BYTE_TO_ASCII(enc, ptr)) {
    case ASCII_x:
      break;
    case ASCII_X:
      upper = 1;
      break;
    default:
      return 1;
    }
    ptr += MINBPC(enc);

We test the first character.  Is it "x"?  Then we might have an XML
declaration.  Is it "X"?  Then we don't have an XML declaration, but
we might not have a valid processing instruction target either.  We
set the flag `upper` and carry on in case of problems.  Otherwise this
must be a processing instruction target, so we happily return success.
In our case we have "x", so we drop through and consider the next
character.

The same logic is applied to the next character being "m" or "M", and
the final character being "l" or "L".  In our case we have the right
letters in the right place, so `upper` is left at zero.

    :::c
      if (upper)
        return 0;
      *tokPtr = XML_TOK_XML_DECL;
      return 1;
    }

`upper` doesn't flag an invalid name for us, so we set the token
pointer to `XML_TOK_XML_DECL` and return success.  All fairly
straightforward, though it looks a little peculiar when laid out as
it is in the code.

## Macro Abuse Redux

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
      ^  ^
      |  + ptr
      + target

While we have a valid start of an XML declaration, we still have to
make sure that we have the closing "?>" that delimits the whole
declaration.  That's what the next steps in `normal_scanPi()` do.

    :::c
    ptr += MINBPC(enc);
    while (HAS_CHAR(enc, ptr, end)) {
      switch (BYTE_TYPE(enc, ptr)) {
      INVALID_CASES(ptr, nextTokPtr)

`INVALID_CASES()` is a magic macro we haven't met before.  It's
another horribly tangled creature like `CHECK_NMSTRT_CASES()` that is
hard to comprehend because of all the subordinate macros.
Substituting the `INVALID_LEAD_CASE` macros makes it somewhat easier
to read:

    :::c
    case BT_LEAD2:
      if (end - ptr < 2)
        return XML_TOK_PARTIAL_CHAR;
      if (IS_INVALID_CHAR(enc, ptr, 2)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 2;
      break;

    case BT_LEAD3:
      if (end - ptr < 3)
        return XML_TOK_PARTIAL_CHAR;
      if (IS_INVALID_CHAR(enc, ptr, 3)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 3;
      break;

    case BT_LEAD4:
      if (end - ptr < 4)
        return XML_TOK_PARTIAL_CHAR;
      if (IS_INVALID_CHAR(enc, ptr, 4)) {
        *nextTokPtr = ptr;
        return XML_TOK_INVALID;
      }
      ptr += 2;
      break;

    case BT_NONXML:
    case BT_MALFORM:
    case BT_TRAIL:
      *nextTokPtr = ptr;
      return XML_TOK_INVALID;

Let's take those cases in order.  `BT_LEAD2`, you may recall,
indicates a character that is the start of a sequence of two bytes.
If there are less than two bytes in the input buffer we don't have a
complete character to examine, so return `XML_TOK_PARTIAL_CHAR`.  Then
we call `IS_INVALID_CHAR()`, which is a macro that takes a little
disentangling.  It wraps (in this case) the `isInvalid2()` function in
the encoding table, which for UTF-8 points to the function
`utf8_isInvalid2()`, which calls the macro `UTF8_INVALID2()`, which
returns 1 (success, i.e. the character is invalid) if the next two
bytes of the input do not form a legal UTF-8 two byte sequence.  If
the sequence isn't valid, `INVALID_CASES()` will update the next token
pointer to this sequence and return `XML_TOK_INVALID` to pass on the
error.  Failing that, the sequence is accepted and the current input
pointer is moved on two bytes.  `BT_LEAD3` and `BT_LEAD4` work
similarly, checking for malformed three and four byte sequences and
using `utf8_isInvalid3()` and `utf8_isInvalid4()` respectively.

`BT_NONXML` is the byte type reserved for bytes that cannot form a
character permitted in XML.  That includes the ASCII [control
characters](https://en.wikipedia.org/wiki/Control_character) other
than whitespace characters, and bytes that would start a four byte
sequence that would encode a [Unicode
codepoint](https://unicode.org/glossary/#code_point) outside the
permitted range.

`BT_MALFORM` is slightly different; it is reserved for 0xFE and 0xFF,
which are never defined for any purpose in UTF-8.

Finally, `BT_TRAIL` indicates a byte that would follow a `BT_LEAD2`,
`BT_LEAD3` or `BT_LEAD4` byte.  We should never see one of these,
because it should always be dealt with when processing the relevant
leading byte.

    :::c
    default:
      ptr += MINBPC(enc);
      break;
    }

So if we encounter an invalid byte, it will cause us to exit
`normal_scanPi()` protesting its invalidity.  What we are actually
looking for is a question mark, `BT_QUEST`, and if we don't find it we
just move on to look at the next byte.  If we do find it, more
interesting things happen.

    :::c
    case BT_QUEST:
      ptr += MINBPC(enc);
      REQUIRE_CHAR(enc, ptr, end);
      if (CHAR_MATCHES(enc, ptr, ASCII_GT)) {
        *nextTokPtr = ptr + MINBPC(enc);
        return tok;
      }
      break;

Once we have checked to see if there is another character in the buffer for
us to look at, we compare that character with ">" to see if we have a
"?>" closing sequence.  (`CHAR_MATCHES()` is a macro that hides
whether we are doing an 8-bit or 16-bit comparison).  If we do, we
point the next token pointer to the character after the ">" (if there
is one) and return whichever token `normal_checkPiTarget()` supplied
us with.  Otherwise we have just found an isolated "?" and must carry
on with the search.  Notice that this means that processing
instructions may not contain the sequence "?>" even in a quoted
string, which is a correct if perhaps surprising feature of the XML
standard.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
      ^                                                       ^
      + target                                    *nextTokPtr +

In our case we will move along the characters, falling into the
default case of our `switch` statement until we finally reach the
closing "?>", set the next token pointer to the newline and return
`XML_TOK_XML_DECL`.

## Back to the Parser

The call stack unwinds all the way back to `prologParser()`, which
promptly throws us at `doProlog()`.  As you may recall, this starts
with some housekeeping, setting up the event pointers, then tests to
see if the token is negative, indicating some problem.
`XML_TOK_XML_DECL` is decidedly positive, so instead we call
`XmlTokenRole()` to find out what it means in context.  Because we are
at the start of the parse, `XmlTokenRole()` translates to the
`prolog0()` handler function.

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
      case XML_TOK_XML_DECL:
        state->handler = prolog1;
        return XML_ROLE_XML_DECL;

`prolog0()` converts our token into `XML_ROLE_XML_DECL`, but unlike
the [first walkthrough](../expat-internals-a-simple-parse/) it sets
the role handler function pointer to `prolog1` rather than `error`.
You might suspect that we will stay with the prologue processor this
time, and you'd be right.  There may, after all, be more XML prologue
to come.

    :::c
    switch (role) {
    case XML_ROLE_XML_DECL:
      {
        enum XML_Error result = processXmlDecl(parser, 0, s, next);
        if (result != XML_ERROR_NONE)
          return result;
        enc = parser->m_encoding;
        handleDefault = XML_FALSE;
      }
      break;

The big switch statement in `doProlog()` directs us to call
`processXmlDecl()` to, er, process the XML declaration.

    :::c
    static enum XML_Error
    processXmlDecl(XML_Parser parser, int isGeneralTextEntity,
                   const char *s, const char *next)

The same function handles both XML declarations and text declarations,
since they are almost identical in form.  The second argument,
`isGeneralTextEntity`, distinguishes the two cases.  For us it is
zero (`XML_FALSE`), since we are not processing a general text entity.

    :::c
    const char *encodingName = NULL;
    const XML_Char *storedEncName = NULL;
    const ENCODING *newEncoding = NULL;
    const char *version = NULL;
    const char *versionend;
    const XML_Char *storedversion = NULL;
    int standalone = -1;
    if (!(parser->m_ns
          ? XmlParseXmlDeclNS
          : XmlParseXmlDecl)(isGeneralTextEntity,
                             parser->m_encoding,
                             s,
                             next,
                             &parser->m_eventPtr,
                             &version,
                             &versionend,
                             &encodingName,
                             &newEncoding,
                             &standalone)) {

After initializing a whole bunch of local variables, we then choose
which function to process the declaration with.  `parser->m_ns` is a parser
field that is `XML_TRUE` if we have a non-standard _namespace separator_
defined, a choice made when creating the parser.  We don't, so
`XmlParseXmlDecl()` gets called.  Surprisingly, given that it starts
"Xml...", this is not a macro.  It is a veneer function from the
multiply-included file `xmltok_ns.c` that calls `doParseXmlDecl()`,
supplying it with the correct function to find any encoding named in
the declaration, in this case the aptly-named `findEncoding()`.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
    ^                                                         ^
    + ptr                                                 end +

`doParseXmlDecl()` starts by initializing a bunch of local variables
and then stepping the pointers over the fixed start and end of the
declaration.

    :::c
    const char *val = NULL;
    const char *name = NULL;
    const char *nameEnd = NULL;
    ptr += 5 * enc->minBytesPerChar;
    end -= 2 * enc->minBytesPerChar;
    if (!parsePseudoAttribute(enc, ptr, end, &name, &nameEnd, &val, &ptr)
        || !name) {

It then calls `parsePseudoAttribute()` to get the first name/value
pair in the declaration.  We refer to these as "pseudo-attributes"
because they are fixed and limited by the standard as we noted
earlier; only certain "attribute" names are valid, and only in certain
orders.  Notice that this condition also tests if the `name` pointer
is NULL; that will be important later.

## Pseudo-Attribute Parsing

    :::c
    if (ptr == end) {
      *namePtr = NULL;
      return 1;
    }

The first thing `parsePseudoAttribute()` does is to check if there is
anything to parse.  Recall that the pointers have been moved over the
fixed parts of the declaration:

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
         ^                                                  ^
         + ptr                                          end +

If the two pointers are equal, that would mean that we have run out of
pseudo-attributes to parse, so the correct thing to do is to set the
name pointer `namePtr` to NULL and return 1 for success.  If this
happened at this point of the parse, we would have a completely empty
XML declaration, which is an error.  The check back in
`doParseXmlDecl()` for a NULL name pointer catches this case and will
return an error back up the call chain.

Anyway in our case the pointers are still a good way apart, so we move
on to the next test.

    :::c
    if (!isSpace(toAscii(enc, ptr, end))) {
      *nextTokPtr = ptr;
      return 0;
    }

What we are attempting to do is to determine if `ptr` is pointing to a
whitespace character.  Unfortunately we can't just use the standard
library `isspace()` function for two reasons; first, our input
encoding may not be what `isspace()` is expecting, and second, XML
only accepts a limited set of characters as valid whitespace, and in
particular does not regard locale-specific spaces as being
whitespace.  Only a space, tab, newline or carriage return are
acceptable.

Therefore we have two steps to perform here.  First, `toAscii()` is
called to convert the input to a single ASCII character, or -1 if the
character isn't legal ASCII.  After that, `isSpace()` (note the
capital 'S') compares that against the short list of whitespace
characters.

    :::c
    static int
    toAscii(const ENCODING *enc, const char *ptr, const char *end)
    {
      char buf[1];
      char *p = buf;
      XmlUtf8Convert(enc, &ptr, end, &p, p + 1);
      if (p == buf)
        return -1;
      else
        return buf[0];
    }

`toAscii()` is a simple function making use of the encoding's
conversion functions.  `XmlUtf8Convert()` is a macro like the
`XmlConvert()` macro that was mentioned in the [previous
walkthrough](../expat-internals-a-simple-parse/), except that it
selects the appropriate function to convert to UTF-8 rather than to
the internal encoding.  In our case these happen to be the same thing;
`XmlUtf8Convert()` invokes `utf8_toUtf8()` as described in that
walkthrough.  Arguably much simpler functions could be used, but the
conversion functions happen to be there.

We deliberately supply only one byte of output buffer, because we are
only looking for ASCII characters, and we don't bother with the return
value.  It is enough to check whether the output buffer pointer we
pass to the conversion function is moved on; if it is, we have ASCII
because those are the only UTF-8 characters that fit in a single byte.

    :::c
    static int FASTCALL
    isSpace(int c)
    {
      switch (c) {
      case 0x20:
      case 0xD:
      case 0xA:
      case 0x9:
        return 1;
      }
      return 0;
    }

In our case we have a space (0x20), which is decoded and fed to
`isSpace()`.  This performs the obvious switch and returns 1; a space
is indeed a whitespace character.

Back in `parsePseudoAttribute()` we have the space required to
separate pseudo-attributes, so we don't throw our hands up in
horror<sup>[2](#horror)</sup> and return an error.  Instead we proceed
to skip over any further optional whitespace:

    :::c
    do {
      ptr += enc->minBytesPerChar;
    } while (isSpace(toAscii(enc, ptr, end)));
    if (ptr == end) {
      *namePtr = NULL;
      return 1;
    }

If this puts us at the end of the declaration, again we return with a
NULL name pointer and let the caller decide whether this is an error.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
          ^                                                 ^
          + ptr                                         end +

Fortunately for us there is plenty of text left in the declaration,
and our `ptr` is pointing to the start of the pseudo-attribute name.
We record that, and start a long loop wandering along the name.

    :::c
    *namePtr = ptr;
    for (;;) {
      c = toAscii(enc, ptr, end);
      if (c == -1) {
        *nextTokPtr = ptr;
        return 0;
      }

Each character is converted to a single-byte ASCII value.  This is a
plausible thing to do because all of the pseudo-attributes as defined
by the XML standard have names that consist solely of ASCII
characters.  If `toAscii()` returns an error (-1), we cannot have a
valid pseudo-attribute name so we return 0 to signal an error.

    :::c
    if (c == ASCII_EQUALS) {
      *nameEndPtr = ptr;
      break;
    }

If we reach an equals sign, we have the end of the pseudo-attribute
name.  We record that and break out of the loop.

    :::c
    if (isSpace(c)) {
      *nameEndPtr = ptr;
      do {
        ptr += enc->minBytesPerChar;
      } while (isSpace(c = toAscii(enc, ptr, end)));
      if (c != ASCII_EQUALS) {
        *nextTokPtr = ptr;
        return 0;
      }
      break;
    }

Alternatively if we have whitespace, we also have the end of the
pseudo-attribute name, but we need to hunt on until we find something
that isn't whitespace.  If that something isn't an equals sign, we
have an error; otherwise we break out of the loop just like when we
found the equals sign earlier.

    :::c
    ptr += enc->minBytesPerChar;

Finally we move the input pointer on.  This raises the question of
whether we can run off the end of our input buffer and start trying to
parse gibberish, since we don't explicitly test for `ptr` reaching
`end`.  We can't run off the buffer, as it happens; the conversion
function will catch that and return an error, so `toAscii()` will also
return an error and `parsePseudoAttribute()` will pass the error on.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
          ^      ^                                          ^
          |      + ptr                                  end +
          |      + *nameEndPtr
          + *namePtr

We exit the loop with the start- and end-of-name pointers set to
capture the pseudo-attribute name, "version" in this case.  Before
starting in on the pseudo-attribute value, we have one more check to
make.

    :::c
    if (ptr == *namePtr) {
      *nextTokPtr = ptr;
      return 0;
    }

The only way that `ptr` can be the same as `*namePtr` is if the first
character of the "name" was actually the equals sign.  That's clearly
an error, so we would return 0 to complain about it.  Fortunately we
don't have that problem, so we move `ptr` on from the equals and skip
over any whitespace there might be before the pseudo-attribute value.

    :::c
    ptr += enc->minBytesPerChar;
    c = toAscii(enc, ptr, end);
    while (isSpace(c)) {
      ptr += enc->minBytesPerChar;
      c = toAscii(enc, ptr, end);
    }
    if (c != ASCII_QUOT && c != ASCII_APOS) {
      *nextTokPtr = ptr;
      return 0;
    }

What we want now is a quoted string for our value.  XML accepts either
single or double quotes, or `ASCII_APOS` and `ASCII_QUOT` as the
macros used here call them.  There are macro definitions for most of
the ASCII characters in the file `ascii.h` as hexadecimal numbers.
It's not entirely clear why these are considered preferable to
character literals, but the code makes liberal use of them.
Regardless, we have a double quote here so we don't return an error.

    :::c
    open = (char)c;
    ptr += enc->minBytesPerChar;
    *valPtr = ptr;

What we do need to do at this point is record which of the quote
characters were used to open the string, which is just a matter of
storing it in the local variable `open`.  The next character must be
the start of the value proper, so we move the pointer on and record
that.

Obviously the next thing we want to do is to skip along input string
until we run off the end (and `toAscii()` returns an error) or we find
our closing quote.  However only a limited number of characters are
allowed in the value of any pseudo-attribute: ASCII alphanumerics, a
period, a minus sign or an underscore.  The following loop therefore
looks rather different to the equivalent for handling normal element
attributes:

    :::c
    for (;; ptr += enc->minBytesPerChar) {
      c = toAscii(enc, ptr, end);
      if (c == open)
        break;
      if (!(ASCII_a <= c && c <= ASCII_z)
          && !(ASCII_A <= c && c <= ASCII_Z)
          && !(ASCII_0 <= c && c <= ASCII_9)
          && c != ASCII_PERIOD
          && c != ASCII_MINUS
          && c != ASCII_UNDERSCORE) {
        *nextTokPtr = ptr;
        return 0;
      }
    }

Once we have found the closing quotes, we can just set the next token
pointer to the (hopefully) following space and return 1 for success.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
          ^      ^ ^   ^                                    ^
          |      | |   + *nextTokPtr                    end +
          |      | + *valPtr
          |      + *nameEndPtr
          + *namePtr

Notice that there is no "end of value" pointer; it has to be deduced
from the next token pointer.

## Dealing With The Declaration

    :::c
    if (!XmlNameMatchesAscii(enc, name, nameEnd, KW_version)) {

Control returns in `doParseXmlDecl()`, where we have the first
pseudo-attribute in the declaration and so don't immediately raise an
error.  Instead we check to see if we have the right name; the first
pseudo-attribute must be "version" according to the XML standard.
Again we can't do something as straightforward as `memcmp()` because
of encoding issues, so we roll our own<sup>[3](#roll)</sup> in the
form of `XmlNameMatchesAscii()`.  Just to catch you out, this is a
macro for a function in the encoding table, this time
`normal_nameMatchesAscii()`.

The `KW_version` that we pass to `normal_nameMatchesAscii()` is a
`char` constant array made up of `ASCII_` macro-ed characters spelling
out "version"; it is somewhat puzzling why this is preferable to a
string literal, since it is obviously not as clear.  However, that's
the way the parser likes it.  Ours not to reason
why.<sup>[5](#lightbrigade)</sup>

    :::c
    static int PTRCALL
    PREFIX(nameMatchesAscii)(const ENCODING *UNUSED_P(enc),
                             const char *ptr1,
                             const char *end1, const char *ptr2)
    {
      for (; *ptr2; ptr1 += MINBPC(enc), ptr2++) {
        if (end1 - ptr1 < MINBPC(enc))
          return 0;
        if (!CHAR_MATCHES(enc, ptr1, *ptr2))
          return 0;
      }
      return ptr1 == end1;
    }

`normal_nameMatchesAscii()` is pretty straightforward.  It loops
through both the input string `ptr1` and the comparison string `ptr2`,
checking that it hasn't run out of input string and using
`CHAR_MATCHES()` to do encoding-aware comparisons, finishing when it
runs out of comparison string.  In accordance with its name it returns
1 (`XML_TRUE`) if the input text matches the ASCII comparison string,
and 0 (`XML_False`) if not.  The input text is "version", so in our
case we get a 1.

Back in `doParseXmlDecl()`, we know we have the `version`
pseudo-attribute so we load the passed-in pointers with the version
number string:

    :::c
    if (versionPtr)
      *versionPtr = val;
    if (versionEndPtr)
      *versionEndPtr = ptr;

The checks that pointers have actually been passed are unnecessary
&mdash; they always are &mdash; but they cost little and provide peace
of mind.

Then we call `parsePseudoAttribute()` again for the next
pseudo-attribute:

    :::c
    if (!parsePseudoAttribute(enc, ptr, end, &name, &nameEnd, &val, &ptr)) {
      *badPtr = ptr;
      return 0;
    }
    if (!name) {
      if (isGeneralTextEntity) {
        /* a TextDecl must have an EncodingDecl */
        *badPtr = ptr;
        return 0;
      }
      return 1;
    }

This time we are allowed not to have an attribute (i.e. for `name` to
be NULL), since we are an XML declaration not a text declaration
(i.e. `isGeneralTextEntity` is zero).  If there wasn't anything after
the `version` we would just exit with success here, however in our
case there is:

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
                        ^       ^ ^        ^                ^
                        |       | + val    + ptr        end +
                        + name  + nameEnd

We want it to be "encoding" to be valid according the XML standard,
and indeed it is.  We are then treated to the ASCII version of
`IS_NMSTRT_CHAR()`.

    :::c
    if (XmlNameMatchesAscii(enc, name, nameEnd, KW_encoding)) {
      int c = toAscii(enc, val, end);
      if (!(ASCII_a <= c && c <= ASCII_z) &&
          !(ASCII_A <= c && c <= ASCII_Z)) {
        *badPtr = val;
        return 0;
      }
      if (encodingName)
        *encodingName = val;
      if (encoding)
        *encoding = encodingFinder(enc, val, ptr - enc->minBytesPerChar);

An encoding name must begin with an ASCII alphabetic character, which
is a pretty straightforward check.  `parsePseudoAttribute()` has
already checked that the rest of the characters in the encoding name
are valid, so we don't need to do the equivalent of `IS_NAME_CHAR()`
on them.  Assuming we pass the test, we stash a pointer to the
encoding name and call the `encodingFinder` function supplied.

## Encoding Names

    :::c
    static const ENCODING *
    NS(findEncoding)(const ENCODING *enc, const char *ptr, const char *end)
    {
    #define ENCODING_MAX 128
      char buf[ENCODING_MAX];
      char *p = buf;
      int i;
      XmlUtf8Convert(enc, &ptr, end, &p, p + ENCODING_MAX - 1);
      if (ptr != end)
        return 0;
      *p = 0;
      if (streqci(buf, KW_UTF_16) && enc->minBytesPerChar == 2)
        return enc;
      i = getEncodingIndex(buf);
      if (i == UNKNOWN_ENC)
        return 0;
      return NS(encodings)[i];
    }

Finding an encoding given its name is a slightly involved process.
First we have to convert the name into UTF-8 so that we can compare it
properly.  The pre-defined encoding names are not particularly long,
so a buffer of 128 bytes should be more than enough; if we fail to
convert the whole of the encoding name, clearly we aren't going to
match any of the encodings we know about!

Then there is a little special case to deal with.  `streqci()` is a
case-insensitive ASCII string comparison routine returning `XML_TRUE`
(success) if the two strings are the same after converting their
characters to uppercase.  `enc->minBytesPerChar` contains the size of
the "character unit" we referred to earlier, i.e. 2 for UTF-16 and 1
for everything else.  The condition `streqci(buf, KW_UTF_16) &&
enc->minBytesPerChar == 2` is therefore asking "Have we been asked for
UTF-16 _without specifying big or little endian_, and are we already
using UTF-16?"  If we are, we choose to use the same endianness of
UTF-16 that we are already using; this must be right, otherwise we
couldn't have read the declaration in the first place!

Assuming that's not the case, we call `getEncodingIndex()` to search
the encodings table for the name.  This is a straightforward array of
strings rather than anything more complicated; encoding names are
rarely looked up while parsing, so the power and speed of [hash
tables](../expat-internals-the-hash-tables) for example are
unnecessary.

    :::c
    static int FASTCALL
    getEncodingIndex(const char *name)
    {
      static const char * const encodingNames[] = {
        KW_ISO_8859_1,
        KW_US_ASCII,
        KW_UTF_8,
        KW_UTF_16,
        KW_UTF_16BE,
        KW_UTF_16LE,
      };
      int i;
      if (name == NULL)
        return NO_ENC;
      for (i = 0;
           i < (int)(sizeof(encodingNames)/sizeof(encodingNames[0]));
           i++)
        if (streqci(name, encodingNames[i]))
          return i;
      return UNKNOWN_ENC;
    }

`getEncodingIndex()` is pretty simple.  It returns `NO_ENC` (6) if
there is no encoding name to match, `UNKNOWN_ENC` (-1) if none of the
names match, or a constant giving the index into the encodings table
of the encoding requested if it does match something.  In our case we
have "us-ascii", which unsurprisingly matches `KW_US_ASCII` and so
returns 1 (`US_ASCII_ENC`).  Back in `findEncoding()`, this leads us
to return `encodings[1]`, which is the encoding structure
`ascii_encoding`.

## Alone I Stand

With the encoding found (or not, `doParseXmlDecl()` doesn't actually
care), we call `parsePseudoAttribute()` again to see if there is any
more to do.  Which there is.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
                                            ^         ^ ^   ^
                                       name + nameEnd + |   + ptr
                                                    val +   + end

According to the XML standard, the third pseudo-attribute must be
"standalone", and it mustn't be present in text declarations.

    :::c
    if (!XmlNameMatchesAscii(enc, name, nameEnd, KW_standalone)
        || isGeneralTextEntity) {
      *badPtr = name;
      return 0;
    }

Furthermore its value must be either "yes" or "no"; nothing else is
allowed.

    :::c
    if (XmlNameMatchesAscii(enc, val,
                            ptr - enc->minBytesPerChar, KW_yes)) {
      if (standalone)
        *standalone = 1;
    }
    else if (XmlNameMatchesAscii(enc, val,
                                 ptr - enc->minBytesPerChar, KW_no)) {
      if (standalone)
        *standalone = 0;
    }
    else {
      *badPtr = val;
      return 0;
    }

That's all that is allowed in an XML declaration.  The only thing left
for `doParseXmlDecl()` to do is to skip over any trailing whitespace
and complain if there's anything else in the declaration.

    :::c
      while (isSpace(toAscii(enc, ptr, end)))
        ptr += enc->minBytesPerChar;
      if (ptr != end) {
        *badPtr = ptr;
        return 0;
      }
      return 1;
    }

## Declaration Handling

Returning back to `processXmlDecl()`, we have set up a lot of
pointers.

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
                   ^   ^          ^                           ^
           version +   |          + encodingName        *next +
            versionend +

In addition, `newEncoding` points to the encoding structure
`ascii_encoding` and `standalone` is now 1.  We then perform some
basic checks and transfer these results somewhere more useful.

    :::c
    if (!isGeneralTextEntity && standalone == 1) {
      parser->m_dtd->standalone = XML_TRUE;
    #ifdef XML_DTD
      if (parser->m_paramEntityParsing == XML_PARAM_ENTITY_PARSING_UNLESS_STANDALONE)
        parser->m_paramEntityParsing = XML_PARAM_ENTITY_PARSING_NEVER;
    #endif /* XML_DTD */
    }

As previously mentioned, text declarations don't allow the
pseudo-parameter `standalone` to be present, so we ignore it if
`isGeneralTextEntity` is `XML_TRUE`.  This is a redundant check;
`standalone` will have been left alone (-1) if `isGeneralTextEntity`
is `XML_TRUE`, but a little paranoia doesn't hurt.  Otherwise
`standalone == 1` causes us to set the `standalone` flag in the
parser's DTD structure.  We also check the parameter entity parsing
control, which could have been set to parse external entities unless
the XML document is supposed to be standalone.  Since we know now that
it is supposed to be standalone, we update that control field to
disallow external parsing.  External entities are a large topic for
another time, so we won't go into the ramifications of that now.

If there is an XML declaration handler, or failing that a default
handler, that gets called next.  Let's assume that we don't have
handlers and move on to dealing with the encoding.  This is more
complicated than you might hope.

    :::c
    if (parser->m_protocolEncodingName == NULL) {
      if (newEncoding) {
        if (newEncoding->minBytesPerChar != parser->m_encoding->minBytesPerChar
            || (newEncoding->minBYtesPerChar == 2 &&
                newEncoding != parser->m_encoding)) {
          parser->m_eventPtr = encodingName;
          return XML_ERROR_INCORRECT_ENCODING;
        }
        parser->m_encoding = newEncoding;
      }

If we have previously set an encoding, for example by the user calling
`XML_SetEncoding()`, that overrides anything the XML declaration might
say.  We will have the parser field `m_protocolEncodingName` pointing to
the overriding encoding name in that case, so we skip this whole
section if the field is not NULL.

Otherwise if the declaration gave an encoding, i.e. `newEncoding` is
not NULL (which indeed is correct), we need to check if it's
compatible with what we've already seen.  In particular, if the
requested encoding has a different size of "character unit" to the
encoding we've been using all along, or we have swapped the endianness
of the UTF-16 encoding we were using, something is wrong.
As [section 4.3.3 of the XML
standard](https://www.w3.org/TR/2008/REC-xml-20081126/#charencoding)
rather wordily puts it,

> In the absence of information provided by an external transport
> protocol (e.g. HTTP or MIME), it is a fatal error for an entity
> including an encoding declaration to be presented to the XML
> processor in an encoding other than that named in the declaration
> [...]

If all is well, we update the `m_encoding` field of the parser structure
with the new encoding.  From now on, our parsing will expect ASCII
input.  Notice that we don't update `m_protocolEncodingName`; that is
for overrides only.

    :::c
    else if (encodingName) {
      enum XML_Error result;
      if (!storedEncName) {
        storedEncName = poolStoreString(
          &parser->m_temp2Pool, parser->m_encoding, encodingName,
          encodingName + XmlNameLength(parser->m_encoding, encodingName));
        if (!storedEncName)
          return XML_ERROR_NO_MEMORY;
      }
      result = handleUnknownEncoding(parser, storedEncName);
      poolClear(&parser->m_temp2Pool);
      if (result == XML_ERROR_UNKNOWN_ENCODING)
        parser->m_eventPtr = encodingName;
      return result;
    }


If `newEncoding` is NULL but `encodingName` is not, the declaration
must have given us an encoding name that `findEncoding()` didn't
recognise.  In that case we turn matters over to a user-defined
unknown encoding handler if there is one, and protest if it doesn't
sort things out.  User-defined encodings are a complicated and lengthy
subject that we will go into in a future document; for now, be glad
that we are not doing that.

After that, we just tidy up any temporary copies of strings we may
have made and return success.

## Continuing the Parse

When `processXmlDecl()` returns control to `doProlog()`, all that
remains in the declaration-specific code is for us to ensure we use
the new encoding (if there is one) and don't gratuitously call any
user-defined default handler.  Doing the by-now familiar dance of
checking the parsing state, we end up calling `XmlPrologTok()` with
our updated parse pointers:

    :::
    <?xml version="1.0" encoding="us-ascii" standalone="yes"?>
                                                              ^
                                                            s +
    <doc>Hello, world</doc>
                            ^
                        end +

As you may recall, `XmlPrologTok()` is really a macro disguising a
function pointer field of the encoding table.  We have a new encoding
table now, but its prologue tokenizer is still `normal_prologTok()`.
In fact `normal_prologTok()` is used for all 8-bit encodings,
regardless of their internal differences.

After ensuring that there is text to parse, which there is, and that
we only deal in whole character units, `normal_prologTok()` switches
on the byte type of the newline character.  This is `BT_LF`:

    :::c
    case BT_S: case BT_LF:
      for (;;) {
        ptr += MINBPC(enc);
        if (! HAS_CHAR(enc, ptr, end))
          break;
        switch (BYTE_TYPE(enc, ptr)) {

Whitespace is meaningless at this point, so we can skip over any
further spaces, tabs or newlines that we find.  This is complicated a
little by having to deal with carriage return/linefeed pairs, which
are used as line endings on some operating systems.

    :::c
    case BT_S: case BT_LF:
      break;

Spaces and line feeds (newlines) are easy, we just ignore them.

    :::c
    case BT_CR:
      /* don't split CR/LF pair */
      if (ptr + MINBPC(enc) != end)
        break;
      /* fall through */

Carriage returns we allow through if there is a following character to
check, otherwise we will treat it as a non-space character just in
case it was going to be followed by something other than a line feed.

    :::c
    default:
      *nextTokPtr = ptr;
      return XML_TOK_PROLOG_S;
    }

The moment we reach a non-whitespace character (or a lone carriage
return), we set the next token pointer to it and return
`XML_TOK_PROLOG_S`.  This is what happens straight away in our parse;
the character after the newline is the "<" at the start of "&lt;doc&gt;".

`doProlog()` loops back to check for errors and ask `XmlTokenRole()`
what `XML_TOK_PROLOG_S` means in this context.  `XmlTokenRole()` is
now the handler `prolog1()` if you recall, and that has no particular
interest in whitespace:

    :::c
    switch (tok) {
    case XML_TOK_PROLOG_S:
      return XML_ROLE_NONE;

`XML_ROLE_NONE` means there is nothing to do for this, which
`doProlog()` duly does.  Or doesn't.  Whatever.  It then calls the
tokenizer again to see what's next.

    :::
    <doc>Hello, world</doc>
    ^                       ^
    + ptr               end +

`normal_prologTok()` sees the "<" and as before looks at the next
character "d".  This has a byte type of `BT_HEX`:

    :::c
    case BT_NMSTRT:
    case BT_HEX:
    case BT_NONASCII:
    case BT_LEAD2:
    case BT_LEAD3:
    case BT_LEAD4:
      *nextTokPtr = ptr - MINBPC(enc);
      return XML_TOK_INSTANCE_START;
    }

We have seen `XML_TOK_INSTANCE_START` in our [first
walkthrough](../expat-internals-a-simple-parse/), but then we were
using `prolog0()` as the handler.  This time we have `prolog1()`, so
we can't necessarily expect it will tell us the same role.

    :::c
    case XML_TOK_INSTANCE_START:
      state->handler = error;
      return XML_ROLE_INSTANCE_START;

In fact we do get exactly the same role, so `doProlog()` will pass
control on to the content processor and everything will continue as
you would expect from last time.  In the interests of brevity we will
stop here, but you are welcome to carry on tracing the execution path
through the library.  The more you do it, the more used you will get
to the peculiar little habits Expat has.

## Conclusions

Processing an XML declaration is unlike most of the parsing the
library does, because the XML standard puts some very strict limits on
what is and is not permitted in the declaration.  All of the valid
characters permitted in the declaration are in the ASCII character
set, which dramatically simplifies decoding the input.  The attributes
have fixed names and must appear in a specific order, simplifying the
parse.  All in all it is a much more tightly defined environment than
anything else in an XML document, and the parser takes considerable
advantage of that.

Hopefully this article has shed a little light on this rather
different corner of the parser, and helped you understand a little
more of how Expat works.  As ever, please don't hesitate to contact me
if you want to know more details, or if you have anything you would
specifically like covered in a future article.

---

## Footnotes

<a id="trudge">1</a>: to walk heavily or wearily.  Trudging
definitely involves effort.

<a id="horror">2</a>: an expression of dismay or disgust, by
implication somewhat theatrical.

<a id="roll">3</a>: "roll your own" is a phrase first applied to
cigarettes.  Those who don't like the cigarettes the tobacco companies
produce can buy paper, filters and tobacco and literally roll a
cigarette for themselves<sup>[4](#smoking)</sup>.  The phrase has
become applied to many cases of creating an item for yourself rather
than buying a pre-made version.

<a id="smoking">4</a>: [smoking is bad for your
health](https://www.nhs.uk/smokefree/why-quit/smoking-health-problems).
Seriously.  Trust the medical profession on this one.

<a id="lightbrigade">5</a>:

> Theirs not to make reply,<br />
Theirs not to reason why,<br />
Theirs but to do and die,<br />
Into the valley of Death<br />
Rode the six hundred.

From _The Charge of the Light Brigade_ by Alfred, Lord Tennyson,
commemorating a suicidal charge at the Battle of Balaclava.

&mdash;Rhodri James, 28th July 2017
