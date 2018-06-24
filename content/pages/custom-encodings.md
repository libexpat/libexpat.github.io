Title: Writing A Custom Encoding
Date: 21 October 2017
License: MIT
Category: Maintenance
Tags: encodings
Author: Rhodri James
Summary: How to cope with alternative character encodings
Slug: writing-a-custom-encoding

_Written by Rhodri James_


This article is an expansion of the comments in `expat.h` surrounding
the `XML_Encoding` structure and the `XML_UnknownEncodingHandler`
type.  I will explain how an unknown encoding handler can be used to
allow Expat to decode some oddly-coded text files into its internal
encoding, and give an example of a handler that deals with a particular
encoding.

## What Is A Custom Encoding?

A _character encoding_ in Expat is a combination of tables and
functions that translates a sequence of bytes into [Unicode
codepoints](http://unicode.org/glossary/#code_point) and from there to
UTF-8 or UTF-16 (as configured at compile time) for the library's
internal use.  Expat natively understands several encodings: UTF-8,
ASCII, Latin-1 (aka ISO/IEC 8859-1) and UTF-16 (big- and little-endian).

A _user-defined encoding_ or _custom encoding_ supplied by an unknown
encoding handler addresses only the first part of that definition; it
translates sequences of bytes into Unicode codepoints.  The library
will translate the codepoints into whichever encoding is being used
internally.

Custom encodings are limited in their scope.  The description in
`expat.h` lists four limitations:

1. > Every ASCII character that can appear in a well-formed XML
    document, other than the characters "$@\^`{}~", must be represented
    by a single byte, and that byte must be the same byte that
    represents that character in ASCII.

    In particular this means that you cannot write a custom encoding
    to handle EBCDIC input, or any other exotic encoding that is not
    based on ASCII.  It also forbids the (ab)use of encodings for
    dealing with cryptographically encoded input.  This is a
    consequence of the XML standard's insistence on [ISO/IEC
    10646](https://en.wikipedia.org/wiki/Universal_Coded_Character_Set)
    for character sets (Unicode, for all practical purposes), and does
    allow for a number of simplifying assumptions in the library code.

    It also forbids custom encodings for variant 16-bit or 32-bit
    input.  This is slightly unfortunate, but very unlikely to be an
    issue.

2. > No character may require more than 4 bytes to encode.

    This is a consequence of the representation of "byte types" inside
    the library, a categorising of input bytes to simplify the initial
    stages of parsing.  There are byte types to indicate the start of
    2-, 3- and 4-byte sequences, but no more than that.

3. > All characters encoded must have Unicode scalar values <= 0xFFFF,
    (i.e., characters that would be encoded by surrogates in UTF-16
    are not allowed).  Note that this restriction doesn't apply to the
    built-in support for UTF-8 and UTF-16.

    This restriction could be lifted with some work to the library,
    but there doesn't seem to be any call for it.  It makes a few
    parts of the library marginally more efficient, but not by much.

4. > No Unicode character may be encoded by more than one distinct
    sequence of bytes.

    While this is listed as a limitation and is in general a sensible
    idea, it is not enforced in any way by the library.


## Custom Encoding Components

Custom encodings are created when an unknown encoding handler fills in
the `XML_Encoding` structure passed to it and returns `XML_STATUS_OK`.

    :::c
    typedef struct {
      int map[256];
      void *data;
      int (XMLCALL *convert)(void *data, const char *s);
      void (XMLCALL *release)(void *data);
    } XML_Encoding;

The heart of the `XML_Encoding` structure is the `map` array.  This
table defines what an individual byte of an encoding means.

* A positive number indicates that the input byte translates to that
  Unicode codepoint; so for instance if `map[0x80]` is `0x1001`, an
  input byte of `0x80` translates to U+1001, MYANMAR LETTER KHA.
* A value of -1 indicates that no valid byte sequence starts with
  this value, so the byte should be considered malformed.
* A value of -2, -3 or -4 indicates that the byte starts a 2-, 3- or
  4-byte sequence respectively.
* Any other value is illegal and will cause the encoding to be
  rejected.

The conversion of multi-byte sequences to codepoints is done by the
function pointed to by `convert`.  This function pointer can be NULL
if there are no multi-byte sequences in the encoding (i.e. no -2 to -4
entries in `map`).  Omitting the convert function when it is required
will cause the encoding to be rejected.

The convert function will be passed the `XML_Encoding` structure's
`data` pointer as its first parameter.  This allows the converter to
retain state between conversions, if necessary.  It returns the
Unicode codepoint represented by the sequence of bytes passed as the
second parameter, or -1 if the byte sequence is malformed.

Finally, the `release` function pointer, if not NULL, points to a
function called when the parser is released.  This can tidy up after
the convert function, free any allocated memory and so on.  The
convert function will not be called after the release function has
been.


## Simple Example: RISC OS

Character encodings are best shown by example, so we will start with a
simple one.  In 1987, Acorn Computers defined an [extended version of
ASCII](https://en.wikipedia.org/wiki/RISC_OS_character_set) for its
[RISC OS](https://www.riscosopen.org/content/) computers.  Like
Latin-1 it only uses a single byte to encode any character in the
character set, so there is no need for any conversion function. This
makes defining the encoding simple.  There are however a number of
characters that do not have an equivalent in Unicode, and must
therefore be marked as invalid.

The encoding meets the four requirements straightforwardly:

1. The first half of the character set is ASCII.
2. All characters are encoded in one byte.
3. All Unicode codepoints involved are in the range U+0000 to U+FFFF.
4. There are no repeated characters

We will write an unknown encoding handler that sets up this encoding
when it is asked for the encoding named `risc-os`.

    :::c
    static int XMLCALL
    risc_os_encoding_handler(void *data,
                             const XML_Char *encoding,
                             XML_Encoding *info)
    {
        int i;

        if (strcmp(encoding, "risc-os"))
            return XML_STATUS_ERROR;

The first thing to do is to check which encoding name the parser has
been presented with.  We are only dealing with the `risc-os` encoding,
so we just do a simple string comparison<sup>[1](#xmlunicode)</sup>
and return an error if it is the wrong one.  There is no reason why an
unknown encoding handler cannot deal with many possible encodings,
just filling in the `info` structure appropriately for each one.

Since this encoding is exactly the same as ASCII for the first 128
values, we can set the first half of the map easily:

    :::c
    for (i = 0; i < 128; i++)
        info->map[i] = i;

A lot of encodings look like this.  The next part of the map cannot be
done so algorithmically.  In practise this is probably best done as a
constant array that we can `memcpy` into place, but we'll do it the
hard way here.

    :::c
    info->map[0x80] = 0x20AC;   /* € */
    info->map[0x81] = 0x0174;   /* Ŵ */
    info->map[0x82] = 0x0175;   /* ŵ */
    info->map[0x83] = -1;       /* Resize icon, invalid */
    info->map[0x84] = -1;       /* Close icon, invalid */
    info->map[0x85] = 0x0176;   /* Ŷ */
    info->map[0x86] = 0x0177;   /* ŷ */
    info->map[0x87] = -1;       /* "87" */
    info->map[0x88] = -1;       /* Left arrow icon, invalid */
    info->map[0x89] = -1;       /* Right arrow icon, invalid */
    info->map[0x8A] = -1;       /* Up arrow icon, invalid */
    info->map[0x8B] = -1;       /* Down arrow icon, invalid */
    info->map[0x8C] = 0x2026;   /* … */
    info->map[0x8D] = 0x2122;   /* ™ */
    info->map[0x8E] = 0x2030;   /* ‰ */
    info->map[0x8F] = 0x2022;   /* • (Bullet) */
    info->map[0x90] = 0x2018;   /* ‘ */
    info->map[0x91] = 0x2019;   /* ’ */
    info->map[0x92] = 0x2039;   /* ‹ */
    info->map[0x93] = 0x203A;   /* › */
    info->map[0x94] = 0x201C;   /* “ */
    info->map[0x95] = 0x201D;   /* ” */
    info->map[0x96] = 0x201E;   /* „ */
    info->map[0x97] = 0x2013;   /* – (n-dash) */
    info->map[0x98] = 0x2014;   /* — (m-dash) */
    info->map[0x99] = 0x2212;   /* − (minus) */
    info->map[0x9A] = 0x0152;   /* Œ */
    info->map[0x9B] = 0x0153;   /* œ */
    info->map[0x9C] = 0x2020;   /* † */
    info->map[0x9D] = 0x2021;   /* ‡ */
    info->map[0x9E] = 0xFB01;   /* ﬁ */
    info->map[0x9F] = 0xFB02;   /* ﬂ */

As it happens, the rest of the encoding is the same as Latin-1, so in
the interests of brevity we will take the obvious short-cut:

    :::c
    for (i = 160; i < 256; i++)
        info->map[i] = i;

Finally, we don't have a convert function, so we don't need user data
and we don't need a release function either:

    :::c
        info->data = NULL;
        info->convert = NULL;
        info->release = NULL;
        return XML_STATUS_OK;
    }

That's it.  All we have to do to implement this or any other ISO 8859
variant is to fill `info->map` in with the right values and we're
away.


## Multi-Byte Example: Shift JIS

[Shift JIS](https://en.wikipedia.org/wiki/Shift_JIS) is an encoding
for the Japanese language in which each character is encoded in one or
two bytes.  It meets most of the criteria for being implemented as a
custom encoding:

1. The first 128 characters map directly to ASCII except that
   backslash (`\`) is replaced with a yen sign (`¥`) and tilde (`~`)
   with an overline (`‾`).  Those are both characters it is permitted
   to change.
2. All characters are encoded in one or two bytes.
3. All of the Unicode codepoints involved are in the range U+0000 to
   U+FFFF; this takes a little work to verify, but is true.
4. Unfortunately it is not even remotely true that no Unicode
   codepoint is encoded by more than one byte sequence.  All of the
   ASCII alphanumeric characters and many of the symbols have both
   single byte and double byte encodings.  However this condition is
   not enforced, so for the sake of the example we will ignore it.

This time we will use tables of constants to initialise the
top-bit-set half of our `map`:

    :::c
    const int first_byte_hi[128] = {
        -1, -2, -2, -2, -2, -2, -2, -2,  /* 0x80 */
        -2, -2, -2, -2, -2, -2, -2, -2,  /* 0x88 */
        -2, -2, -2, -2, -2, -2, -2, -2,  /* 0x90 */
        -2, -2, -2, -2, -2, -2, -2, -2,  /* 0x98 */
        -1,     0xFF61, 0xFF62, 0xFF63,  /* 0xA0 */
        0xFF64, 0xFF65, 0xFF66, 0xFF67,  /* 0xA4 */
        0xFF68, 0xFF69, 0xFF6A, 0xFF6B,  /* 0xA8 */
        0xFF6C, 0xFF6D, 0xFF6E, 0xFF6F,  /* 0xAC */
        0xFF70, 0xFF71, 0xFF72, 0xFF73,  /* 0xB0 */
        0xFF74, 0xFF75, 0xFF76, 0xFF77,  /* 0xB4 */
        0xFF78, 0xFF79, 0xFF7A, 0xFF7B,  /* 0xB8 */
        0xFF7C, 0xFF7D, 0xFF7E, 0xFF7F,  /* 0xBC */
        0xFF80, 0xFF81, 0xFF82, 0xFF83,  /* 0xC0 */
        0xFF84, 0xFF85, 0xFF86, 0xFF87,  /* 0xC4 */
        0xFF88, 0xFF89, 0xFF8A, 0xFF8B,  /* 0xC8 */
        0xFF8C, 0xFF8D, 0xFF8E, 0xFF8F,  /* 0xCC */
        0xFF90, 0xFF91, 0xFF92, 0xFF93,  /* 0xD0 */
        0xFF94, 0xFF95, 0xFF96, 0xFF97,  /* 0xD4 */
        0xFF98, 0xFF99, 0xFF9A, 0xFF9B,  /* 0xD8 */
        0xFF9C, 0xFF9D, 0xFF9E, 0xFF9F,  /* 0xDC */
        -2, -2, -2, -2, -2, -2, -2, -2,  /* 0xE0 */
        -2, -2, -2, -2, -2, -2, -2, -2,  /* 0xE8 */
        -1, -1, -1, -1, -1, -1, -1, -1,  /* 0xF0 */
        -1, -1, -1, -1, -1, -1, -1, -1   /* 0xF8 */
    };

As you can see, there are a lot of invalid bytes (-1) and two byte
sequences (-2) alongside the
[katakana](https://en.wikipedia.org/wiki/Katakana).  A _lot_ of two
byte sequences.  The logical way to cope with them is with tables.
Looking at the definition of
[Shift JIS](https://en.wikipedia.org/wiki/Shift_JIS), you may notice
that in every two-byte sequence, the second byte is always 0x40 or
greater.  We will save a little space in our tables by missing out the
first 0x40 values and adjust our indices appropriately.

In the interests of brevity we won't show most of the actual values in
the tables here:

    :::c
    const int following_81[192] = {
        0x3000, 0x3001, 0x3002, 0x002C, /* 0x40 */
        /* Followed by many more lines of codepoints
         * and the occasional -1 for an invalid character.
         */
    };

    /* ...and the other tables... */

    const int *second_byte_lo[31] = {
        following_81,
        following_82,
        /* ... */
        following_9F
    };

    const int *second_byte_hi[16] = {
        following_E0,
        following_E1,
        /* ... */
        following_EF
    };

The conversion function is then just a simple table lookup,
complicated only by the fragmentary nature of the table:

    :::c
    static int XMLCALL
    convert_jis(void *data, const char *s)
    {
        const int *table;

        /* 's' will always be a two byte string, because that's
         * all that is in the map.  s[0] must either lie in the range
         * 0x81 to 0x9F or 0xE0 to 0xEF, according to the map.
         */
        if (s[0] <= 0x9F) {
            table = second_byte_lo[s[0] - 0x81];
        } else {
            table = second_byte_hi[s[0] - 0xE0];
        }
        /* There are no legal two-byte sequences with s[1] < 0x40 */
        if (s[1] < 0x40)
            return -1;
        return table[s[1] - 0x40];
    }

Optimising this to remove the sparseness of some of the subtables is
left as an exercise for the reader.<sup>[2](#lazy)</sup>  That leaves
us just having to write the unknown encoding handler, which is frankly
trivial in comparison:

    :::c
    static int XMLCALL
    shift_jis_encoding_handler(void *data,
                               const XML_Char *encoding,
                               XML_Encoding *info)
    {
        int i;

        if (strcmp(encoding, "shift-jis"))
            return XML_STATUS_ERROR;
        for (i = 0; i < 128; i++)
            info->map[i] = i;
        info->map[92] = 0x00A5; /* Replace Backslash with Yen */
        info->map[126] = 0x203E; /* Replace Tilde with Overline */
        /* Copy in the table for the upper half of map */
        memcpy(&info->map[128], first_byte_hi, 128*sizeof(int));
        info->data = NULL;
        info->convert = convert_jis;
        info->release = NULL;
        return XML_STATUS_OK;
    }

While larger and more tedious that the RISC OS encoding example,
encoding Shift JIS is not actually a great deal more complicated.  We
need the conversion function to deal with our two-byte sequences, but
it is all just a matter of looking up values in tables.  For our final
example we will do something quite different.


## Complex Example: Page And Offset

For this example we will invent a simple-looking encoding that will
offer us a chance to exercise more of the features of custom
encodings.  It's not a particularly useful or efficient encoding, and
I wouldn't expect to encounter anything like it in real life.

* We map the bytes 0x00 to 0x7F to the codepoints U+0000 to U+007F
  (i.e. we will leave ASCII alone).
* 0x80 is the first byte of a three-byte sequence `s`:<br/>
  ```
  codepoint = s[1] * 256 + s[2]
  ```
  <br/>`s[1]` is remembered as the _page_ for 0x81 sequences (below).
* 0x81 is the first byte of a two-byte sequence `s`:<br/>
  ```
  codepoint = page * 256 + s[1]
  ```
  <br/>If no page has yet been set (by an 0x80 sequence), it defaults
  to 0.
* 0x82 is the first byte of a two-byte sequence, the codepoint of
  which is the value of the second byte.  This makes codepoints in the
  range U+0080 to U+00FF less painful to represent.
* All bytes in the range 0x83 to 0xFF are illegal (for no particular
  reason).

Again, this satisfies all the custom encoding criteria except for
number 4; there are at least two encodings for every codepoint from
U+0000 to U+FFFF, four for some of them.  Since this condition isn't
enforced, we will ignore it for our example.

The important thing about this encoding is that it keeps state; the
last page set by an 0x80 sequence must be kept so that 0x81 sequences
can use it.  This means that for once our convert function is going to
need some user data, i.e. `info->data` will not be NULL.  We could
make the page a static variable, but then multiple parsers using our
encoding would interfere with each other.  To avoid that we will
allocate a new variable for each encoding, which we will want to free
once the encoding is no longer in use.  That in turn means that we
finally have a use for the release function.

You might wonder if we could define a byte sequence that simply set
the current page without producing any more output, unlike 0x80
sequences.  Unfortunately you can't; all byte sequences must either
return a codepoint or an error.  There is no option to return "This
sequence is valid but does not return a codepoint", nor does any
realistic encoding require such a thing.

Let's write the unknown encoding handler first this time:

    :::c
    typedef struct {
        XML_Parser parser;
        unsigned int page;
    } PageEncodingData;

    static int XMLCALL
    page_encoding_handler(void *data,
                          const XML_Char *encoding,
                          XML_Encoding *info)
    {
        int i;
        PageEncodingData *page_data;
        XML_Parser parser = (XML_Parser)data;

This first bit is a departure from the usual for our encodings.  This
time we actually use the `data` parameter to pass user-level
information into the encoding handler.  We expect to be given the
parser structure; I'll explain why in a moment.

    :::c
        if (strcmp(encoding, "page-and-offset"))
            return XML_STATUS_ERROR;

This rejects anything that isn't our new encoding, which we've
arbitrarily called `page-and-offset`.  Now we allocate space for our
recorded page:

    :::c
        page_data = XML_MemMalloc(parser, sizeof(PageEncodingData));
        if (page_data == NULL)
            return XML_STATUS_ERROR;
        page_data->parser = parser;
        page_data->page = 0;

The reason I wanted the parser structure is so that we can allocate
memory using `XML_MemMalloc()`.  This will use the same allocation
functions as the parser itself, which may be helpful in some
circumstances.  It's not obligatory, but it is polite and may even be
some help in debugging.

Returning `XML_STATUS_ERROR` if the allocator fails is a little
problematic.  We normally return `XML_STATUS_ERROR` to mean "we don't
recognise this encoding name", and that is how it will be reported to
the user.  This time we would like to report that we are out of
memory, but unfortunately there is no other way of reporting an
error.

    :::c
        for (i = 0; i < 128; i++)
            info->map[i] = i;
        info->map[0x80] = -3;
        info->map[0x81] = -2;
        info->map[0x82] = -2;
        for (i = 0x83; i < 256; i++)
            info->map[i] = -1;

Setting up the map is pretty simple; we have ASCII, one three-byte
sequence, two two-byte sequences, and everything else is invalid.  In
fact that last loop setting the invalid bytes of the map to -1 is
unnecessary.  The map is pre-initialised to have all entries -1 before
our unknown encoding handler is called, so we never need to explicitly
set invalid entries.  Doing so makes what is going on a good deal
clearer, however, and the processing cost is negligible.

    :::c
        info->data = page_data;
        info->convert = page_convert;
        info->release = page_release;
        return XML_STATUS_OK;
    }

Finally we fill in the pointers, happy that for once they aren't a
collection of NULLs.  All we have to do now is write the functions.

Let's take the release function first.  Since we allocated the user
memory with `XML_MemMalloc()`, we should release it with
`XML_MemFree()`.  That's why we have a pointer to the parser structure
in our user-defined data structure `PageEncodingData`.

    :::c
    static void XMLCALL
    page_release(void *data)
    {
        PageEncodingData *page_data = (PageEncodingData *)data;
        XML_MemFree(page_data->parser, data);
    }

All very straightforward.  So, surprisingly, is the convert function:

    :::c
    static int XMLCALL
    page_convert(void *data, const char *s)
    {
        PageEncodingData *page_data = (PageEncodingData *)data;

        switch (s[0]) {
        case 0x80:
            /* This is a three byte sequence: (0x80, page, offset) */
            page_data->page = (s[1] & 0xff) << 8;
            return page_data->page | (s[2] & 0xff);

        case 0x81:
            /* This is a two byte sequence: (0x81, offset) */
            return page_data->page | (s[1] & 0xff);

        case 0x82:
            /* This is a two bytes sequence: (0x82, value) */
            return s[1] & 0xff;

        default:
            /* This should never happen */
            return -1;
        }
    }

The only remotely complicated thing here is the amount of masking with
`0xff` that goes on, which avoids potential problems with sign
extension if `char` is a signed integer type in your compiler.

Because we want to pass the parser structure into the handler, we need
to register it in a slightly different way to normal:

    :::c
    XML_SetUnknownEncodingHandler(parser,
                                  page_encoding_handler,
                                  (void *)parser);

That's it.  It takes surprisingly little work to implement quite
complex encodings; rather more complex than the XML standard really
allows.


## Conclusions

Expat's custom encoding mechanism allows a great deal of scope for
dealing with unusual encodings.  It does have limitations &mdash; you
cannot change the decoding of a single byte according to internal
state, for instance &mdash; but these do not interfere with the
handling of real-world encodings.  They can't be used for exotic
purposes such as inserting a security translation layer, which is
probably just as well.

----

## Footnotes

<a name="xmlunicode">1:</a> for simplicity, we are assuming that the
library has been compiled to use UTF-8 internally.  If it has been
compiled for UTF-16 (generally on Windows), we would have to use the
wide string comparison function `wcscmp()` and a wide string literal.
A properly paranoid program would use macros defined conditionally on
`XML_UNICODE`, but that is more work that I want to do for an example.

<a name="lazy">2:</a> in other words, I can't be bothered to do it.


&mdash; Rhodri James, 30 August 2017
