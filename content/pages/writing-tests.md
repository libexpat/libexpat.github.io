Title: Writing New Tests for Expat
Date: 3 June 2018
License: MIT
Category: Maintenance
Tags: testing
Author: Rhodri James
Summary: How to manage and extend Expat's coverage tests

_Written by Rhodri James_


Expat has an extensive suite of tests designed to ensure that its
functionality is correct, and to cover as much of the large code base
as is possible.  Whenever new functionality is added or old bugs are
discovered and fixed, there will be a need for a test to ensure that
the resulting code is correct and any bugs do not recur.  This
document is intended for contributors to Expat, to help them write
such tests and balance them with the existing test suite.


## Finding the Test Code

The test code can be found in the `expat/tests` directory of the
repository.  The tests can be compiled and run by typing

    :::console
    $ make check

at a command line, after the usual configuration.  This builds two
applications, `runtests` and `runtestspp`, which are compiled as C and
C++ respectively.  The two applications will be run automatically and
should both report passes.  This is all managed by libtool, which
while very slick goes to some effort to bury the detailed information
you are likely to need for debugging.  The actual output of the
applications can be found in the files `expat/tests/runtests.log` and
`expat/tests/runtestspp.log` respectively.

The test _suite_ is arranged as a set of five _test cases_, each of
which consists of many _tests_.  The source code for the individual
tests can be found in `runtests.c`, which is by now a rather large
file.  Unfortunately it is not easy to split it into more manageable
chunks, though that would make a worthy project for some brave soul.
The remaining source files supply the infrastructure for running
tests, capturing results and comparing them with expected values.

Test cases are distinguished from each other in how they initialise
and finalise individual tests.  The five current test cases are:

1.  _Basic:_ Basic tests are supplied with a fresh parser created with
    `XML_ParserCreate()`, which will be destroyed when the test
    finishes.  The parser itself is held in the static variable
    `parser`.

    There is a strong argument that this test case should be broken
    down thematically into a number of more manageable test cases.

1.  _XML Namespaces:_  Namespace tests are supplied with a fresh
    parser created with `XML_ParserCreateNS()`, which will again be
    destroyed when the test finished and is held in the static
    variable `parser`.  Namespace tests check elements of XML
    namespace parsing and processing.

1.  _Miscellaneous:_  Misc tests do not have a parser created for
    them.  They are intended to test issues surrouding the creation of
    parsers, or which do not directly involve parsers.  If a test
    creates a parser and places a pointer to it in the static variable
    `parser`, the parser will be destroyed when the test exits.

1.  _Allocation:_  Allocation tests are supplied with a fresh parser
    created with `XML_ParserCreate_MM()` and passed customised
    allocation functions which can be freely reconfigured to fail on
    command.  Again the static variable `parser` is used, and the
    allocated parser will be destroyed when the test completes.

1.  _NS Allocation:_  Namespace Allocation tests combine the features
    of XML Namespace tests and allocation tests.  They are intended to
    allow testing of allocation failure paths while processing
    namespaces.

Unless there is a particular need for a customised parser, most tests
fit into the Basic test case.


## Structure of a Test

Individual tests are functions, but they must be defined using the
`START_TEST` and `END_TEST` macros:

    :::c
    START_TEST(my_test)
    {
      do_some_testing();
    }
    END_TEST

`START_TEST` defines the function as taking no parameters and
returning void.  It also sets a number of static variables that make
error reporting easier by stashing the real function name and location
in the file of the test.  These can be a little clumsy to use, so a
number of utility functions and macros exist to simplify things.

To abort a test prematurely, call the `fail` macro.  This will record
the test as a failure and output a message, but will still perform the
standard tidying up for the test case (i.e. the parser will still be
destroyed).  It will return immediately from the test function
(actually longjumping out to the test case control loop).  It does not
affect any future tests, which will still be run as normal.

    :::c
    START_TEST(my_test)
    {
      if (!try_foo())
      {
        fail("No foo!");
      }
      if (!try_bar())
      {
        fail("No bar!");
      }
    }
    END_TEST

This will print an error message of the form `"ERROR: No foo!"` if the
function `try_foo()` returns false, and will then exit the test without
even attempting to call `try_bar()`.  If `try_foo()` succeeds, then
`try_bar()` will be called, and may or may not report a failure
instead.  Currently the functions underlying the `fail` macro have the
file name and line number where the failure was raised, but do not
make use of them.

Notice that no particular effort needs to be made to report success;
simply not calling `fail` is sufficient!

If the parser may contain useful information about a failure, call the
`xml_failure` macro instead of `fail`.  This will include the parser
error code and string and the line and column number in the parsed
text where the error occured in the error report.

    :::c
    START_TEST(my_test)
    {
      enum XML_Status result;
      result = XML_Parse(parser, my_text, strlen(my_text), 1);
      if (result != XML_STATUS_OK)
          xml_failure(parser);
    }
    END_TEST

Notice that `xml_failure` needs to be told which parser to get the
failure information from.  This will usually be the static variable
`parser`, the default set up by most of the test cases, but it is
useful to be able to specify an external entity parser when those are
being tested.

Often you will need to write tests to provoke specific errors.  The
`expect_failure` macro provides support for this.  It takes the string
to parse, the expected error code (as from `XML_GetErrorCode`), and an
error message to fail with if the parser does _not_ signal an error.

    :::c
    START_TEST(my_test)
    {
        expect_failure(duff_text, xml_error_code,
                       "Didn't fail on duff text");
    }
    END_TEST

## Support Macros and Functions

### Byte-by-Byte Parsing

In order to exercise as many code paths as possible within the parser,
most tests don't call `XML_Parse()` directly to do the whole parse in
one go.  Instead they call the wrapper function
`_XML_Parse_SINGLE_BYTES()` which takes the same parameters
but feeds the input file to `XML_Parse()` one byte at a time.  This
ensures that the code paths for incomplete characters and tokens are
regularly run through.

Unless you have a specific reason for testing "all-in-one" parsing,
you should use `_XML_Parse_SINGLE_BYTES()` in preference to
`XML_Parse()` in future tests.

### Dummy Handlers

It is often necessary to register handler functions to trigger particular
bugs or exercise particular code paths in the library.  Usually these
handlers don't need to do anything more than exist.

A number of dummy handler functions are defined for these situations.
Rather than do nothing at all, they set a bit in the static variable
`dummy_handler_flags` so that a test can verify that the handler has
in fact been called.  (This is currently not universally true, which
is a historical accident.  An easy introduction to the test system
might be to add flags for the handlers that don't currently set one,
and write or alter a test to check they gets set appropriately.)

For example:

    :::c
    START_TEST(check_start_elt_handler)
    {
        const char *text = "<doc>Hello world</doc>";
        dummy_handler_flags = 0;
        XML_SetStartElementHandler(parser, dummy_start_element);
        if (_XML_Parse_SINGLE_BYTES(parser, text, strlen(text),
                                    XML_TRUE) == XML_STATUS_ERROR)
            xml_failure(parsr);
        if (dummy_handler_flags != DUMMY_START_ELEMENT_HANDLER_FLAG)
            fail("Did not invoke start element handler");
    }
    END_TEST

### Wide Character Support

The test suite is intended to be run on both "narrow" (the default)
and "wide" (compiled with `XML_UNICODE` defined) versions of the Expat
library.  More specifically, the test suite must cope with the
internal representation of text being either (8-bit) `char` or
(16-bit) `wchar`.  This matters because handler functions, for
example, are passed internal representations rather than simple (byte)
strings.

The library helpfully supplies the `XML_Char` type for internal
character strings.  However tests will need to define string literals
of the appropriate type and use the correct comparison functions, and
even the correct format codes in `printf()` calls.  To do this, the
test suite defines the following macros:

*  `XCS(s)` (eXpat Character String) turns a string literal into the
   appropriate type for the internal representation.  `XCS("foo")`
   will become `L"foo"` for wide builds and just `"foo"` otherwise.
*  `xcstrlen(s)` returns the length (in characters) of an XML_Char
   string.
*  `xcstrcmp(s, t)` compares two XML_Char strings, as per `strcmp` or
   `wcscmp`.
*  `xcstrncmp(s, t, n)` compares at most `n` characters of two
   XML_Char strings.
*  `XML_FMT_CHAR` provides the correct format code to `printf` a
   single XML_Char character.
*  `XML_FMT_STR` provides the correct format code to `printf` an
   XML_Char string.

So for example an unknown encoding handler (which is passed the name
of the encoding to use as an XML_Char string) begins with:

    :::c
    if (xcstrcmp(encoding, XCS("unsupported-encoding")) == 0) {
      ...

### Character Data Accumulation

As is often noted, character data handlers are not guaranteed to be
called by the library with the whole of the text they need to process
at once.  If we wish to verify in a test that the whole of a cdata
section is what we expect (for example to show that a general entity
has been correctly substituted), we must accumulate the characters in
a buffer and only check them once the cdata section is finished.

To do this, we use the functions and types found in `chardata.c` and
`chardata.h`.  There are three steps:

1.  Initialise a `CharData` structure to buffer the data, using
    `CharData_Init()`.
1.  Add characters to the buffer using `CharData_AppendXMLChars()`.
    Notice that this only deals in XML_Char strings, which is almost
    always what is wanted.
1.  Test the final result is what we expect with
    `CharData_CheckXMLChars()`.

If a test needs to be repeated, the `CharData` structure can be
reinitialised and reused normally.  Any XML_Char data can be
accumulated this way, not just cdata sections.

For the common case of testing that the data passed to a character
data handler is correct, the test suite supplies the macro
`run_character_check()`.  This performs the entire test in one go,
checking that the `text` parameter it is passed results in the
XML_Char string `expected` being accumulated in a character data
handler, and failing the test (using `xml_failure`) if not.

Be careful when writing such tests to remember that the expected
results will differ depending on whether the internal representation
is UTF-8 or UTF-16.  For example, `test_french_utf8()` which tests
that an e-acute character (U+00E9, or 0xc3 0xa9 in UTF-8) is correctly
parsed, reads as follows:

    :::c
    START_TEST(test_french_utf8)
    {
        const char *text =
            "<?xml version='1.0' encoding='utf-8'?>\n"
            "<doc>\xC3\xA9</doc>";
    #ifdef XML_UNICODE
        const XML_Char *expected = XCS("\x00e9");
    #else
        const XML_Char *expected = XCS("\xC3\xA9");
    #endif
        run_character_check(text, expected);
    }
    END_TEST

There is also a macro helper for the less common case of checking that
XML attributes are correctly passed to a start element handler.
`run_attribute_check()` parses the text it is passed and checks that
the attribute _values_ are as expected.  This should only be used with
single attributes in each tag, as the order in which attributes are
presented to the start handler is not guaranteed.

    :::c
    START_TEST(test_example)
    {
        const char *text = "<doc foo='bar'>Hi</doc>";
        const XML_Char *expected = XCS("bar");
        run_attribute_check(text, expected);
    }
    END_TEST

If you need to test multiple attributes, a more capable accumulator
will be needed.

### Structured Data Accumulation

As a variation on the `CharData` accumulator, the functions and types
in `structdata.c` and `structdata.h` allow for storing three integer
values as well as an `XML_Char` string.  It is marginally more
complicated to use since the strings are copied to dynamically
allocated buffers rather than a single fixed buffer, and the table of
entries is also dynamically allocated.

1.  Initialise a `StructData` structure with `StructData_Init()`.
1.  Add entries (a string and three integers) using
    `StructData_AddItem()`.  Each call to this function adds a single
    "entry" to the `StructData`.
1.  Check the results with `StructData_CheckItems()`, which takes an
    array of entries (`StructDataEntry` structures) to compare against
    the entries in the `StructData`.  If the check fails, all the
    dynamically allocated memory in the `StructData` will be freed.
1.  Tidy up the `StructData` by calling `StructData_Dispose()`.

Thus far this mechanism is only used for checking row and column
numbers are accurately tracked in handler functions, but it could be
generalised for other uses.

### Testing External Entities

A great number of tests involve the use of external entity parsers.
Unfortunately there is little coherence in the mechanisms used by
these tests; many were created on an ad-hoc basis for individual tests
with little thought to re-use.

If you need to write a test involving external entity parsing, it is
worth looking through the existing tests to see if any of them can be
modified for your purpose.  The external entity handlers all have
names of the form `external_entity_XXXer()` (where XXX isn't
necessarily a helpful description of what the handler does).  It would
be a fruitful use of someone's time to rationalise the handlers and
produce a more flexible set.

Failing finding something that you can subvert, follow these steps:

1.  Define a structure that can hold the parameters you need to pass
    to the external entity handler and results you need back from it
    (if any).
1.  Write an external entity handler that assumes that structure is
    the main parser's user data.  Remember to `XML_ParserFree()` the
    external entity parser if you create one.
1.  Write a test which sets the structure as the parser's user data
    and sets the handler you have just written as the external entity
    handler.

The macro `run_ext_character_check()` and its associated functions
gives a simple example of this sort of approach.

### Debug Memory Allocators

Tests in the _Allocation_ and _NS Allocation_ test cases, as well as a
few other _Miscellaneous_ tests, use a pair of custom allocators to
control memory allocation in the parser.  By default,
`duff_allocator()` and `duff_reallocator` behave exactly as `malloc()`
and `realloc()` do.

If the static variable `allocation_count` is set to a value other than
`ALLOC_ALWAYS_SUCCEED` (-1), `duff_allocator()` will return an error
(i.e. `NULL`) after that many more calls.  In other words if
`allocation_count` is set to zero, `duff_allocator()` will fail next
time it is called and all calls thereafter; if `allocation_count` is
one, `duff_allocator()` will succeed once and then fail on the second
and subsequent calls, and so on.  The static variable
`reallocation_count` controls when `duff_reallocator()` will fail in
exactly the same way.

The tests that use these allocators are generally attempting to check
failure paths within the library.
Because [string pools](../expat-internals-string-pools/) effectively
cache memory allocations, simply looping around incrementing the
initial setting of `allocation_count` or `reallocation_count` will not
catch all of the failure cases.  The only robust way to do that is to
free the existing parser and create a new one each time around the
loop.  Fortunately there are already functions that will do that for
us, the functions that are used to tear down and set up each test in
the test cases: `alloc_teardown()` and `alloc_setup()` or
`nsalloc_teardown()` and `nsalloc_setup()` as appropriate.

## Conclusions

Expat's test suite is something of a hodge-podge, as one might expect
of a system that has been worked on in short bursts by many hands.
Adding to it is relatively straightforward process once you know the
structure and support macros, but it could do with some
rationalisation.

&mdash; Rhodri James, 3rd June 2018
