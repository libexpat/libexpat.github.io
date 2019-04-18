Title: Expat Internals: Encodings
Date: 6 February 2018
License: MIT
Category: Maintenance
Tags: internal, encodings
Author: Rhodri James
Summary: How character encodings work in Expat

_Written by Rhodri James_


Expat has a comprehensive but confusing system to handle different
character encodings of its input byte stream.  This article attempts
to dispel some of the confusion surrounding the system and help future
maintainers understand what it does.


## What Is A Character Encoding?

A _character encoding_ in Expat is a combination of tables and
functions that translates a sequence of bytes into [Unicode
codepoints](http://unicode.org/glossary/#code_point) and from there
to UTF-8 or UTF-16 (as configured at compile time).  This includes
functions to determine various syntactic elements of XML, such as
whether a byte sequence translates to a codepoint that would be valid
in an XML name, and functions that perform basic parsing such as the
tokenizers.

Encoding tables are layered structures, with up to three levels of
layering depending on whether the encodings are built-in or created by
the user (see the [article on custom
encodings](../../doc/writing-a-custom-encoding/) for more details of the
latter).  In consequence building the tables is a complex and
tiresome business, so helper macros are used to ensure that they are
set up correctly and consistently.  Helpful as this is for validation,
it makes the encoding tables markedly harder to read.


## The `ENCODING` Structure

The lowest level of the encoding system is the `ENCODING` or `struct
encoding` structure, found in `xmltok.h`.  It consists primarily of
function pointers and arrays of function pointers for some of the most
basic requirements of the parser.

    :::c
    struct encoding {
      SCANNER scanners[XML_N_STATE];

The `scanners` (sometimes referred to as `tokenizers`) are the
functions implementing the high-level state machine of the parser.  So
far we have seen two scanners in the
[walkthrough](../../doc/expat-internals-a-simple-parse)
[articles](../../doc/expat-internals-parsing-xml-declarations), both
using the "normal" (8-bit predefined) encoding: the prologue tokenizer
`normal_prologTok()` parsing the prologue of an XML document, and the
content tokenizer `normal_contentTok()` which takes over once the
prologue is finished.  There are two more tokenizers in this array:
the CDATA section tokenizer `normal_cdataSectionTok()` used for
processing text in `<![CDATA[...]]>` constructions, and the ignore
section tokenizer `normal_ignoreSectionTok()` used for conditional
sections.  Other encodings will of course have their own versions of
these functions.

    :::c
      SCANNER literalScanners[XML_N_LITERAL_TYPES];

There are in fact two more scanners, effectively substates of the
parser which is why they are not in the `scanners` array.  The first
is `normal_attributeValueTok()`, which is used to read the value of an
attribute; the second, `normal_entityValueTok()`, is used to read the
value of a general or parameter entity.  Again, other encodings have
their own versions.

You may have noticed that the tokenizers we have mentioned are named
`normal_stateTok` rather than `utf8_stateTok` or `ascii_stateTok`.  In
fact all of the predefined 8-bit character encodings use the same
functions in the `ENCODING` structures.  We will see more about this
later on.  For now we will carry on assuming that we are looking at
a "normal" encoding.

    :::c
      int (PTRCALL *nameMatchesAscii)(const ENCODING *enc,
                                      const char *ptr1,
                                      const char *end1,
                                      const char *ptr2);

The `nameMatchesAscii` function pointer, as its name implies, compares
an XML name against a NUL-terminated ASCII string.  It takes a pointer
to the start and end of the input string to be compared, allowing the
function to be used directly on the input string.  It is described in
detail in
the [second walkthrough](../expat-internals-parsing-xml-declarations),
for parsing XML declaration "pseudoattributes".  As explained there,
all names in an XML declaration must be valid ASCII, so this
optimised check is well worth while.

    :::c
      int (PTRFASTCALL *nameLength)(const ENCODING *enc, const char *ptr);

The next function pointer in the structure is `nameLength`, which as
you might imagine counts the number of _bytes_ (not codepoints or
character units) in the XML name passed as a parameter.  The name does
not need to be NUL-terminated; the function simply counts the bytes of
all characters found until it comes across a character that is not
legal in a name.  It can therefore be used directly on the input
bytestream.

    :::c
      const char *(PTRFASTCALL *skipS)(const ENCODING *enc, const char ptr*);

The `skipS` function pointer does exactly what its name suggests; it
returns a pointer to the next non-whitespace character in the input
string.  For this purpose, only a space, tab, carriage return or
linefeed character are considered whitespace, as required by the XML
standard.

    :::c
      int (PTRCALL *getAtts)(const ENCODING *enc,
                         const char *ptr,
                         int attsMax,
                         ATTRIBUTE *atts);

The function pointed to by `getAtts` is a major piece of parsing
logic; it's job is to extract the names and values of all the
attributes in the input string.  As the comments make clear, it must
only be called on a known well-formed start tag or empty element tag,
as it assumes any syntax errors in the input have already been caught.

This function will be discussed in more detail when we examine
attribute parsing in a future walkthrough.

    :::c
      int (PTRFASTCALL *charRefNumber)(const ENCODING *enc, const char *ptr);

      int (PTRCALL *predefinedEntityName)(const ENCODING *enc,
                                          const char *ptr,
                                          const char *end);

A pair of fields deal with the decoding of references.  The field
`charRefNumber` points to a function that parses a numerical character
reference, i.e. input of the form `"&#123;"` or `"&#x123;"`.  It
returns either the referenced codepoint or `-1` if the codepoint
decoded is not legal.  Again the implementations assume that the
reference is syntactically valid.

Similarly, the `predefinedEntityName` field supplies a function to
check the input bytestream against the short list of predefined XML
entities: `&lt;`, `&gt;`, `&amp;`, `&quot;` and `&apos;`.  This
function expects to be passed a start pointer pointing to the
character after the ampersand and an end pointer pointing to the
semicolon.  It returns the codepoint of the character identified, or
zero if the name passed in is not one of the predefined entities.

    :::c
      void (PTRCALL *updatePosition)(const ENCODING *,
                                     const char *ptr,
                                     const char *end,
                                     POSITION *pos);

The `updatePosition` field points to a function which takes an input
stream (with start and end pointers) and a pointer to a `POSITION`
structure (row and column coordinates) which is assumed to be
accurate to the start of the input.  The function moves the row and
column numbers on, counting each _codepoint_ (not byte) as a single
item, and starting a new row for each carriage return, linefeed or
carriage return-linefeed combination.  This should match the
human-readable input, allowing users to easily and quickly identify
where problems are.

    :::c
      int (PTRCALL *isPublicId)(const ENCODING *enc,
                                const char *ptr,
                                const char *end,
                                const char **badPtr);

The `isPublicId` field points to a function which takes pointers to
the quotes at the start and end of a Public ID field, and a pointer to
a pointer for reporting errors through.  Public IDs may contain a
longer list of characters than an XML name, and the function reads
character units from the input text to ensure that they are all
valid.  If the input text does constitute a value Public ID, the
function returns 1; otherwise it returns 0 and sets the error pointer
`*badPtr` to point to the first invalid character in the input.

    :::c
      enum XML_Convert_Result (PTRCALL *utf8Convert)(const ENCODING *enc,
                                                     const char **fromP,
                                                     const char *fromLim,
                                                     char **toP,
                                                     const char *toLim);
      enum XML_Convert_Result (PTRCALL *utf16Convert)(const ENCODING *enc,
                                                      const char **fromP,
                                                      const char *fromLim,
                                                      unsigned short **toP,
                                                      const unsigned short *toLim);

The final two function pointer fields, `utf8Convert` and
`utf16Convert`, are the character conversion functions that we have
met before in the guise of `XmlConvert`.  The primary use of these
functions is to convert the input encoding into the internal encoding.
Since the internal encoding is chosen as UTF-8 or UTF-16 at compile
time, you might hope that only one of these functions would have to be
in the structure.  Unfortunately `utf8Convert` is used explicitly to
convert the input to ASCII for processing the XML prologue, as can be
seen in the [second
walkthrough](../../doc/expat-internals-parsing-xml-declarations).  This
is slightly irritating; in a UTF-8 build, the `utf16Convert` function
must be linked in but will never be called.

    :::c
      int minBytesPerChar;

The number of bytes required to represent the shortest character in
the encoding, this field is used somewhat inconsistently.  It is
widely used in `xmlparse.c` for instance as the amount to increment
input pointers by, but `xmltok_impl.c` uses the macro `MINBPC(enc)`
instead.  Normal builds of the library hard-coded this macro to 1 or 2
as appropriate to the encoding, for efficiency reasons.

    :::c
      char isUtf8;

This field is a flag that indicates exactly what it says; non-zero if
the encoding is UTF-8 and zero otherwise.  It is used to avoid some
unnecessary conversions.

    :::c
      char isUtf16;

The final field looks like it should also be a flag to indicate that
the encoding is UTF-16.  It is slightly more complicated than that; it
is set non-zero if the encoding is the same endianness of UTF-16 as
would be used internally if the code was compiled to have a UTF-16
encoding.  This is convenient for determining if the input under this
encoding needs to be converted to the other endianness of UTF-16 for
the internal encoding.

To complicate matters, the parser's "initial encoding" structure, a
guess at what encoding the input will be in, abuses this field for
something else entirely.  Hidden under the `INIT_ENC_INDEX` and
`SET_INIT_ENC_INDEX` macros, the field holds the index into the
parser's internal encodings table of its guess at the initial
encoding.  This looks confusing when you dig under the macros, but the
two uses are quite distinct and never clash.


### Implementations

The functions used in the `ENCODING` structures are implemented in the
file `xmltok_impl.c`.  There is a lot of macro magic in this file,
allowing the file to be included three times in `xmltok.c` with
different macro definitions.  This creates three basic `ENCODING`
layouts, one for 8-bit encodings and one each for big- and
little-endian 16-bit encodings.

The actual code has been discussed in the various walkthroughs in some
detail, and I don't propose to repeat that here.  It is important to
note, however, that the code is carefully written so that different
functions can be used for details of decoding; functions that are
defined in the `normal_encoding` structure.


## The `normal_encoding` Structure

The `ENCODING` structure supplies the core functionality of an
encoding that drives the parser's internals.  This is then wrapped
(subclassed, if you want to take an object-oriented view of things)
with another structure, `struct normal_encoding`, which supplies the
functions and tables that turn a generic 8-bit encoding in a UTF-8
encoding or a Latin-1 encoding.

    :::c
    struct normal_encoding {
      ENCODING enc;
      unsigned char type[256];

After the base `ENCODING`, the first and most important item in a
`normal_encoding` is the `type` table.  This is an array of "byte
type" values that define what each possible input byte means to the
XML parsing functions.  Some byte types are very specific, such as
`BT_LT`, the byte type for a "<" character.  Others are much more
generic, such as `BT_NMSTRT`, a character which can legitimately start
an XML name but has no other significance.

An important set of byte types from our point of view are `BT_LEAD2`,
`BT_LEAD3` and `BT_LEAD4`, the byte types that indicate that this byte
starts a sequence of two, three or four bytes.  Obviously these
sequences need further decoding to determine exactly what sorts of
characters they represent.  Fortunately the possibilities are very
limited, and the `normal_encoding` structure contains sets of three
functions pointers, one for each possible sequence length, that ask
the three questions the parser is interested in.

    :::c
      int (PTRFASTCALL *isName2)(const ENCODING *, const char *);
      int (PTRFASTCALL *isName3)(const ENCODING *, const char *);
      int (PTRFASTCALL *isName4)(const ENCODING *, const char *);

The first set are the `isName` functions.  These should return a true
(non-zero) value if the character can legally be part of an XML name.
These are implemented as bitmap table lookups, a fast method that
doesn't take up as much memory as you might assume.

    :::c
      int (PTRFASTCALL *isNmstrt2)(const ENCODING *, const char *);
      int (PTRFASTCALL *isNmstrt3)(const ENCODING *, const char *);
      int (PTRFASTCALL *isNmstrt4)(const ENCODING *, const char *);

The `isNmstrt` functions perform a similar check, returning a true
(non-zero) value if the character can legally start an XML name.  A
number of character can be in a name as long as they don't start it,
so separate functions are needed.  Again, these functions are
implemented as bitmap table lookups.

    :::c
      int (PTRFASTCALL *isInvalid2)(const ENCODING *, const char *);
      int (PTRFASTCALL *isInvalid3)(const ENCODING *, const char *);
      int (PTRFASTCALL *isInvalid4)(const ENCODING *, const char *);

The final set of functions detect invalid byte sequences.  They return
a true (non-zero) value if the byte sequence does not decode into a
valid Unicode codepoint.  These are simpler to write algorithmically
than by lookup; they would involve very sparse tables.

Although we have described the structure fields above as if they
applied to all of the basic encodings, only 8-bit encodings actually
use them.  The macro definitions for the 16-bit encodings still use
the `type` table as an optimisation, but use the function
`unicode_byte_type()` to convert the input into a byte type.  Slightly
different logic is used to deal with [surrogate
pairs](http://unicode.org/glossary/#surrogate_pair), and as a result
none of the functions are needed.


## Table-Building Macros

As I mentioned at the start of this article, the complex nature of
encodings means that a lot of macros are used to make creating them
safer.  The most basic of these is the `PREFIX()` macro, which is used
throughout `xmltok_impl.h` to convert generic function name like
`prologTok` into `normal_prologTok`, `big2_prologTok` or
`little2_prologTok`.  As you might expect, the table-building macros
make extensive use of `PREFIX()` to ensure the same consistency of
names.

A majority of the definitions of each `ENCODING` structure is then
handled by a single macro:

    :::c
    #define IGNORE_SECTION_TOK_VTABLE , PREFIX(ignoreSectionTok)
    #define VTABLE1 \
      { PREFIX(prologTok), PREFIX(contentTok), \
        PREFIX(cdataSectionTok) IGNORE_SECTION_TOK_VTABLE }, \
      { PREFIX(attributeValueTok), PREFIX(entityValueTok) }, \
      PREFIX(nameMatchesAscii), \
      PREFIX(nameLength), \
      PREFIX(skipS), \
      PREFIX(getAtts), \
      PREFIX(charRefNumber), \
      PREFIX(predefinedEntityName), \
      PREFIX(updatePosition), \
      PREFIX(isPublicId)

(The odd layered definition of `IGNORE_SECTION_TOK_VTABLE` is so that
it can be easily omitted in builds of the library that have DTD
parsing permanantly disabled.  We have ignored that option to date
because it is rarely used any more.)

If you compare the definition of `VTABLE1` with the `ENCODING`
structure, you will notice that it includes everything up to the
`toUtf8` and `toUtf16` encoding functions themselves.  Logically you
might expect that the encoding functions would be the principle
difference between the various 8-bit encodings, and you would be
right; all the other 8-bit functions in the tables are the familiar
"normal_blahBlahBlah" that we have mostly already seen.

Since we only have two built-in 16-bit encodings, little- and
big-endian UTF-16, there is a further macro to help build those
`ENCODING` structures:

    :::c
    #define VTABLE VTABLE1, PREFIX(toUtf8), PREFIX(toUtf16)

For the `struct normal_encoding` structures that wrap the `ENCODINGs`,
there are three more macros defined.  One of them,
`STANDARD_VTABLE()`, sets fields we have not yet mentioned because
they do not exist in a standard build of the
library.<sup>[1](#stdvtable)</sup>  In normal builds, the macro
substitutes away to nothing.

`NORMAL_VTABLE()` is rather more useful, as it fills in the nine
function pointers with function names having a common prefix:

    :::c
    #define NORMAL_VTABLE(E) \
      E ## isName2, \
      E ## isName3, \
      E ## isName4, \
      E ## isNmstrt2, \
      E ## isNmstrt3, \
      E ## isNmstrt4, \
      E ## isInvalid2, \
      E ## isInvalid3, \
      E ## isInvalid4

`NORMAL_VTABLE()` does its own prefixing rather than using the
`PREFIX()` macro to allow for variation.  In fact the prefix used most
commonly is "utf8_", as you may recall from the walkthroughs.

Finally, `NULL_VTABLE` sets those same function pointers to NULL for
encodings that don't use the same mechanism.  The function pointers in
the `normal_encoding` structure are never accessed directly, but
always through more macros which, for some encodings, side-step the
encoding structure entirely.


## The Built-In Encodings

At this point you may be thinking that the worst is over.  All you
have to do is substitute a few macros and the shape of the various
built-in encodings should be obvious.  Let's take a look at those
tables and see if things really are that simple.  For simplicity, we
will ignore the encoding variations for the "namespace" build,
i.e. when the compile-time symbol `XML_NS` is
defined.<sup>[2](#ns)</sup>


### UTF-8 Encoding

The basic encoding table for UTF-8 input is as follows:

    :::c
      static const struct normal_encoding utf8_encoding = {
        { VTABLE1, utf8_toUtf8, utf8_toUtf16, 1, 1, 0 },
        {
    #define BT_COLON BT_NMSTRT
    #include "asciitab.h"
    #undef BT_COLON
    #include "utf8tab.h"
        },
        STANDARD_VTABLE(sb_) NORMAL_VTABLE(utf8_)
      };

The redefinition of `BT_COLON` as `BT_NMSTRT` looks a little odd, but
it's part of the support for `XML_NS` (which needs to react to colons
differently in some way), so we can ignore it for now.  The two
include files simply contain the byte types for the lower (ASCII) and
upper halves of the `type` array.  Obviously we don't want to type in
that data repeatedly and risk copying errors, and we choose to put it
in a separate file and include it here because it is less ugly than
defining huge macros.

Substituting the macros we mentioned above (but leaving the include
files alone; the byte types really aren't that interesting), we get:

    :::c
      static const struct normal_encoding utf8_encoding = {
        {
          { normal_prologTok, normal_contentTok,
            normal_cdataSectionTok, normal_ignoreSectionTok },
          { normal_attributeValueTok, normal_entityValueTok },
          normal_nameMatchesAscii,
          normal_nameLength,
          normal_skipS,
          normal_getAtts,
          normal_charRefNumber,
          normal_predefinedEntityName,
          normal_updatePosition,
          normal_isPublicId,
          utf8_toUtf8, utf8_toUtf16,
          .minBytesPerChar=1,
          .isUtf8=1,
          .isUtf16=0
        },
        {
    #define BT_COLON BT_NMSTRT
    #include "asciitab.h"
    #undef BT_COLON
    #include "utf8tab.h"
        },
        utf8_isName2,
        utf8_isName3,
        utf8_isName4,
        utf8_isNmstrt2,
        utf8_isNmstrt3,
        utf8_isNmstrt4,
        utf8_isInvalid2,
        utf8_isInvalid3,
        utf8_isInvalid4
      };

`utf8_toUtf8` and `utf8_toUtf16` are defined a little further up
`xmltok.h` from this definition, and the `normal_` functions are all
defined in one of the inclusions of `xmltok_impl.c`.  The other
`utf8_` functions are all defined much further up `xmltok.c`, except
that `utf8_isName4` and `utf8_isNmstrt4` are themselves macros that
become the function `isNever` which, predictably, always returns
false.

So far, so good.


### UTF-8 Internal Encoding

Expat keeps a separate encoding to handle its internal UTF-8
representation of data, which is what it is compiled to use by
default.  This `internal_utf8_encoding` structure differs from
`utf8_encoding` only in that it includes the data file "iasciitab.h"
rather than "asciitab.h".  The only difference between the two files
is that the carriage return character 0x0D has a byte type of BT_S
instead of BT_CR.  Once input has been rendered into internal format,
carriage return/linefeed combinations have already been dealt with, no
the special casing isn't needed any more.


### Latin-1 Encoding

Because of it's popularity and simplicity, Expat has a built-in
encoding to handle ISO 8859-1, better known as Latin-1.  It's encoding
structure looks like this:

    :::c
      static const struct normal_encoding latin1_encoding = {
        {
          { normal_prologTok, normal_contentTok,
            normal_cdataSectionTok, normal_ignoreSectionTok },
          { normal_attributeValueTok, normal_entityValueTok },
          normal_nameMatchesAscii,
          normal_nameLength,
          normal_skipS,
          normal_getAtts,
          normal_charRefNumber,
          normal_predefinedEntityName,
          normal_updatePosition,
          normal_isPublicId,
          latin1_toUtf8, latin1_toUtf16,
          .minBytesPerChar=1,
          .isUtf8=0,
          .isUtf16=0
        },
        {
    #define BT_COLON BT_NMSTRT
    #include "asciitab.h"
    #undef BT_COLON
    #include "latin1tab.h"
        },
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL
      };

This all looks very straightforward until you meet that large section
of NULL pointers at the end.  Those should be pointing to functions to
check 2-, 3- and 4-byte sequences for various properties.  Won't the
lack of those functions cause problems in parsing, you might ask?

The answer is no.  All characters in a Latin-1 encoding are
represented by a single input byte, so there are no multi-byte
sequences to test.  The byte types `BT_LEAD2`, `BT_LEAD3` and
`BT_LEAD4` do not occur in Latin-1's byte type table.

Since Latin-1 is a character for character direct map onto Unicode
codepoints U+0000 to U+00FF, the conversion functions are very
straightforward.  I don't propose to go into them any further.


### ASCII Encoding

The American Standard Code for Information Interchange (ASCII) is one
of the older computer character encodings.  Each character is encoded
in seven bits, and again is character for character mapped onto
Unicode codepoints U+0000 to U+007F.  It won't surprise you that the
Expat encoding structure for ASCII is almost identical to that for
Latin-1:

    :::c
      static const struct normal_encoding ascii_encoding = {
        {
          { normal_prologTok, normal_contentTok,
            normal_cdataSectionTok, normal_ignoreSectionTok },
          { normal_attributeValueTok, normal_entityValueTok },
          normal_nameMatchesAscii,
          normal_nameLength,
          normal_skipS,
          normal_getAtts,
          normal_charRefNumber,
          normal_predefinedEntityName,
          normal_updatePosition,
          normal_isPublicId,
          ascii_toUtf8, latin1_toUtf16,
          .minBytesPerChar=1,
          .isUtf8=1,
          .isUtf16=0
        },
        {
    #define BT_COLON BT_NMSTRT
    #include "asciitab.h"
    #undef BT_COLON
        },
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL
      };

It is worth noting that the `isUtf8` field is set to 1; all valid
ASCII is automatically also valid UTF-8.


### UTF-16 Encoding

Things get more complicated when we start looking at the built-in
UTF-16 encodings, not least because there is even more use of macros
to avoid duplicating code between the big- and little-endian
variants.  (If anyone else feels faintly ill after reading the macro
`DEFINE_UTF16_TO_UTF8()`, don't worry, you're in good company.)  We
will concentrate on little-endian UTF-16; big-endian UTF-16 is exactly
the same except for reversing the order of the input bytes.

The encoding structure doesn't look too outrageous:

    :::c
      static const struct normal_encoding little2_encoding = {
        {
          { little2_prologTok, little2_contentTok,
            little2_cdataSectionTok, little2_ignoreSectionTok },
          { little2_attributeValueTok, little2_entityValueTok },
          little2_nameMatchesAscii,
          little2_nameLength,
          little2_skipS,
          little2_getAtts,
          little2_charRefNumber,
          little2_predefinedEntityName,
          little2_updatePosition,
          little2_isPublicId,
          little2_toUtf8, little2_toUtf16,
          .minBytesPerChar=2,
          .isUtf8=0,
          .isUtf16=1 if native byte order is also little-endian,
                  =0 otherwise
        },
        {
    #define BT_COLON BT_NMSTRT
    #include "asciitab.h"
    #undef BT_COLON
    #include "latin1tab.h"
        },
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL
      };

Other than the slightly unexpected setting of `isUTF16`, this is
mostly understandable.  The NULL pointers are a cause for concern this
time, though; UTF-16 consists entirely of two-byte and four-byte
sequences.  Also doesn't that make the byte type table a bit useless?

Remember that I mentioned above that the fields of our
`normal_encoding` structure are never accessed directly, but always
through macros?  That's what saves us in this case; for the UTF-16
encodings, the macro definitions are changed before they are used in
"xmltok_impl.c", and those macros don't do anything so simple as just
call a function pointer.

Let's start with the `BYTE_TYPE()` macro, which in simpler encodings
just indexes into the `type` array.  In this case what it actually
turns into, reduced to its simplest version, is the expression:

    :::c
    p[1] == 0 ?
      little2_encoding.type[p[0]] :
      unicode_byte_type(p[1], p[0])

where `p` is the two-byte sequence being decoded.  In English, and
considering the input as one sixteen-bit value rather than two bytes,
if the top eight bits of the value are zero, we look up the bottom
eight bits in the `type` array exactly as if they were a Latin-1
(which if you recall is correct), and otherwise calls the function
`unicode_byte_type` to algorithmically determine the byte type.  It
will return `BT_LEAD4` if the value is the first of a surrogate pair,
`BT_TRAIL` if it is the second of a surrogate pair (almost always a
mistake), `BT_NONXML` for values that shouldn't be used at all, and
`BT_NONASCII` for (non-ASCII) "normal" characters.  So far so good, we
aren't trying to access invalid memory or anything else embarrassing.

Let's look at the name comparison macros next.  In eight-bit
encodings, `IS_NAME_CHAR(enc, p, n)` calls the `isName<n>` function
pointer in the encoding.  In the 16-bit encodings, it evaluates to
zero, which means that the `CHECK_NAME_CASE` macro will always decide
that a `BT_LEAD2`, `BT_LEAD3` or `BT_LEAD4` byte type is never a valid
character to be in a name.  The only one of those that can ever occur
is `BT_LEAD4`, and it turns out to be entirely correct that no
codepoint represented by a surrogate pair in UTF-16 is a valid
character for a name.

`IS_NAME_CHAR_MINBPC(enc, p)` is the macro used to see if a single
character unit (16-bit value in our case) is valid in a name.  In
8-bit encodings this never really gets called, because the byte type
can give a precise-enough answer.  In our case it translates instead
into a look-up into the `namingBitmap` table, which is exactly what it
sounds like; a bitmap of which 16-bit values represent a legitimate
character for naming purposes.  There is some careful use of macros to
minimise the size of the bitmap and merge it with the equivalent
bitmap for valid characters at the start of a name, but essentially it
is a simple look-up.

`IS_NMSTRT_CHAR` and `IS_NMSTRT_CHAR_MINBPC` are redefined in exactly
the same way, while `IS_INVALID_CHAR` is defined always to return
zero; given how the other macros are defined, it is never required in
the 16-bit world.  The net result is that there is no requirement for
the NULLed-out function pointers, and we can rest easy.

It will take you quite a while to convince yourself that everything
I've said above is true.  There are multiple levels of macros involved
in accessing the encoding structures, and multiple levels of macros
obscuring the code paths `xmltok_impl.c`, and walking through them all
is no easy task.


### UTF-16 Internal Encoding

As with UTF-8, there is also a version of the UTF-16 encoding intended
to be used on internal data when the library has been compiled to
store it as UTF-16.  As before, `internal_little2_encoding` differs
from `little2_encoding` only in that it include "iasciitab.h" rather
than "asciitab.h"


## Conclusions

Expat's encoding system is complicated by the need to handle both
8-bit and 16-bit encodings, and hard to read because of the extensive
use of macros to avoid code duplication.  None the less it is a
powerful and effective means of rendering input into a manageable
form.  It is relatively easy to add further built-in encodings should
the need ever arise, particularly 8-bit encodings; just define a few
tables and the translation functions to UTF-8 and UTF-16.

---

## Footnotes

<a name="stdvtable">1</a>: `STANDARD_VTABLE` fills in fields that only
exist when the compiler symbol `XML_MIN_SIZE` is defined.  It is not
clear to me exactly what this is supposed to do, or even whether the
library compiles with that symbol defined.  I would have guessed that
is was for minimising the library's memory footprint, but that doesn't
appear to be right.

<a name="ns">2</a>: Again, I haven't investigated exactly what
`XML_NS` does in any detail yet.  I think it allows you to change the
character used to mark an XML namespace from a colon to something
else.  I'm not quite sure why this would be a good idea...

&mdash;Rhodri James, 6th February 2018
