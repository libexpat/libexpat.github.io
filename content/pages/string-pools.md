Title: Expat Internals: String Pools
Date: 19 July 2017
License: MIT
Category: Maintenance
Tags: internal, strings
Author: Rhodri James
Summary: How the parser's string pools work and why to use them

_Written by Rhodri James_


The Expat parser frequently needs to make copies of strings that it
can control the lifetime of.  To do that it uses _string pools_,
flexible structures that are probably best thought of as providing
dynamic memory on demand, byte by byte if need be.  This article
delves into how string pools work, how the parser uses them and why it
would want to.

## What Are String Pools Used For?

String pools provide temporary storage for character strings in the
parser's _internal_ encoding.  Exactly how long the temporary storage
lasts depends on the which string pool is used; some are cleared
frequently while others last for the entire duration of the parse.

A string pool can only construct one string at a time.  Until the
string is "finished" (i.e. fully copied into place, terminated and the
internal pointers updated), it is not possible to start copying
another separate string into place.

The parser structure itself directly contains two string pools,
`tempPool` and `temp2Pool`, which as their names suggest are very
short-term storage.  `tempPool` is cleared once a start or end tag is
processed, and is used for attribute names, substituted values of
entities and the like.  `temp2Pool` is used for extremely short-term
storage of strings (across a few lines of code) when `tempPool`
contains an unfinished string and hence can't be used.

The parser's DTD structure contains two more string pools, `pool` and
`entityValuePool`, which both provide long-term storage for the
lifetime of the parser.  The unhelpfully named `pool` is used to store
element names and entity names, and `entityValuePool` is used to store
the literal value of an entity, i.e. the value exactly as input, with
no substitutions done.

As mentioned above, the strings are stored in _internal_ encoding.  For
many strings this requires conversion from whatever the input encoding
is to internal encoding, and the string pool functions will take care
of that as required.

## How String Pools Work

In this section we will look at the collection of functions and
structures that together make up a string pool, and see how they fit
together.

### Data Structures

    :::c
    typedef struct block {
      struct block *next;
      int size;
      XML_Char s[1];
    } BLOCK;

Every string pool contains a number of `BLOCK` structures, blocks of
memory that contain strings and suitable expansion space.  A block may
contain multiple strings if it has the space, or it may just contain a
single string.  Blocks can be of different sizes, depending on what is
being or has been stored in them.

Blocks are held on
[linked lists](https://en.wikipedia.org/wiki/Linked_list), so each
block starts with a link pointer `next` and a total number of
"character units" of memory available for strings held in `size`.
Note that `size` is _not_ the free space; it indicates the total
number of character units that the block can contain without
reallocation.  How big a character unit is depends the internal
encoding that the parser was compiled for: if `XML_UNICODE` was
defined the internal encoding is UTF-16 and there are two bytes per
character unit, otherwise the internal encoding is UTF-8 and there is
one byte per character unit.  Remember that a character may require
more than one character unit for its representation; UTF-8 can use up
to four bytes for a character, and UTF-16 surrogate pairs are two
character units (four bytes) representing a single Unicode character.

The available memory begins at the single character array `s` and
extends beyond the notional end of the structure.  This is an old
programmers' trick from the days before [flexible array
members](https://en.wikipedia.org/wiki/Flexible_array_member)
became standardised; the presence of `s` in the structure declaration
ensures that memory will be correctly aligned for the `XML_Char` type,
so any additional memory allocated beyond the end of the structure
must also be correctly aligned.

    :::c
    typedef struct {
      BLOCK *blocks;
      BLOCK *freeBlocks;
      const XML_Char *end;
      XML_Char *ptr;
      XML_Char *start;
      const XML_Memory_Handling_Suite *mem;
    } STRING_POOL;

The `STRING_POOL` structure itself maintains two lists of `BLOCKs`.
The first list, hanging<sup>[1](#hanging)</sup> off the pointer
`blocks`, is a list of currently active blocks whose strings are being
used in the parser.  The first block on the list is the _current
block,_ the one to which strings will be added.  The second list,
`freeBlocks`, is as its name suggests a list of blocks whose strings
are not currently in use.  They can be re-used as needed, providing a
small optimisation for the parser; it is quicker to pull a block off
the free list than to go back to the allocation functions and get more
dynamic memory, and it helps to prevent memory fragmentation.

The core of string pool operations are the three pointers `start`,
`ptr` and `end`.  `start` points to the start of the string currently
being assembled in the pool, which is not necessarily at the start of
the current block.  `ptr` points to the character insertion point, the
place to append new characters to the current string.  `end` points to
just past the end of available memory, the point at which either the
block must be extended or a new block started.  These three pieces of
information are most of what is needed to control the string pool.

For example, suppose that a string pool already contains the string
"elt" and we wish to put the string "att" into the pool as well.
After the first two letters have been inserted, the pool pointers will
look like this:

    :::
    +---------------------------...-+
    | 'e' 'l' 't'  0  'a' 't' .     |
    +---------------------------...-+
       ^               ^      ^       ^
       |         start-+      +-ptr   +-end
       + blocks->s

Finally, `mem` is a pointer to the parser's suite of memory allocation
functions.  This allows us to use alternative allocation functions,
for example for debugging, consistently across the whole parser.

### Initialising and Expanding a Pool

String pools are initialised by calling `poolInit()`.  This sets all
the pointers to `NULL` except for `mem`, which points to the memory
allocation suite passed as a parameter.  Obviously this function
should only be used at parser initialisation time; calling it on an
active string pool will leak memory.

Doing almost anything useful with a pool will require it to actually
get some memory.  This is handled by the function `poolGrow()`, which
is the most complicated thing about string pools:

    :::c
    static XML_Bool FASTCALL
    poolGrow(STRING_POOL *pool)
    {

Notice that the pool is not told how much to grow by, just that it
needs to grow.

As it happens `poolGrow()` is only ever called when the current block
is full, i.e. when `pool->ptr == pool->end`.  This isn't an absolute
requirement, but a good deal of the following code makes more sense
when you bear that in mind.

    :::c
      if (pool->freeBlocks) {
        if (pool->start == 0) {
          pool->blocks = pool->freeBlocks;
          pool->freeBlocks = pool->freeBlocks->next;
          pool->blocks->next = NULL;
          pool->start = pool->blocks->s;
          pool->end = pool->start + pool->blocks->size;
          pool->ptr = pool->start;
          return XML_TRUE;
        }

As mentioned above, a pool may have unused blocks
hanging<sup>[1](#hanging)</sup> off its `freeBlocks` pointer.  Let's
assume for the moment that we have free blocks.  The next test checks
to see if we have any currently active blocks; if `start` is NULL, no
block can be hanging off `blocks`.  That makes linking and unlinking
simple.

The pointer-fiddling for `pool->blocks` and `pool->freeBlocks` is
[fairly standard linked-list](http://www.learn-c.org/en/Linked_lists)
stuff.  More interesting is the initialisation of `start` (to the
start of the available memory in the block), `end` (calculated from
the number of characters available) and `ptr` (same as `start`,
obviously).  Since this is all trivially successful, the function just
returns success at this point.

    :::c
        if (pool->end - pool->start < pool->freeBlocks->size) {
          BLOCK *tem = pool->freeBlocks->next;
          pool->freeBlocks->next = pool->blocks;
          pool->blocks = pool->freeBlocks;
          pool->freeBlocks = tem;
          memcpy(pool->blocks->s, pool->start,
                 (pool->end - pool->start) * sizeof(XML_Char));
          pool->ptr = pool->blocks->s + (pool->ptr - pool->start);
          pool->start = pool->blocks->s;
          pool->end = pool->start + pool->blocks->size;
          return XML_TRUE;
        }
      }

If we do have a currently active block, life is a little more tricky.
The block may (and usually will) contain the first part of string that
we were in the process of creating when we noticed we needed more
space.  Unless we want to make more work for the calling function, we
need to copy that partial string into whatever new space we find so
that that caller can just go on adding characters without having to
start from scratch.  In that case, the new space we allocate or find
had better be big enough to hold that partial string and more besides.

As an example, suppose we have a string pool whose current block is
five characters short of being full, and we want to add the string
"ABCDEF" to it.  Initially the pool will look like this:

    :::
    +-...--------------------------+
    | [other contents] 0 . . . . . |
    +-...--------------------------+
      ^                  ^           ^
      + blocks->s        + ptr       + end
                         + start

The characters get added to the pool one at a time until the pool is
full:

    :::
    +-...------------------------------------+
    | [other contents] 0 'A' 'B' 'C' 'D' 'E' |
    +-...------------------------------------+
      ^                   ^                    ^
      + block->s          + start              + end
                                               + ptr

and this is the point at which `poolGrow()` gets called.

The number of characters in the unfinished current string is just the
difference between the `start` and `end` pointers (five in our
example).  As long as that is less than `freeBlocks->size`, the
unfinished string will fit in the free block with at least one
character to spare.  If we didn't need _more_ space than the
unfinished string takes up at the moment, we wouldn't have had to
expand the pool!

Assuming that the unfinished string does fit into the first free
block, we do much the same dance as before unlinking the first free
block and re-linking it as the first active block, but the way we set
the working pointers is much more interesting.

First we copy the unfinished string (still pointed to by
`pool->start`) to the start of the new current block
(`pool->blocks->s`).  Once that is done, we can update the working
pointers; `ptr` must point `end - start` characters into
the new block, then `start` can be updated to the start of the new
block and `end` calculated from `start` and the block size as before.

    :::
    +--------------------------...-+
    | 'A' 'B' 'C' 'D' 'E' . . .    |
    +--------------------------...-+
       ^                  ^          ^
       + start            + ptr      + end
       + block->s

Again we are done, so we just return success.  The calling code will
have space for at least one more character before it overflows the
buffer again, and probably a lot more than that.

If we continue to execute the function past this point, either we have
no blocks on the `freeBlocks` list, or there isn't enough memory in
the first free block to fit the string that caused us to want to
expand the pool and still have space to expand.  In the latter case we
could carry on down the `freeBlocks` list looking for a big enough
block, but the cost of searching the list and unlinking the block
starts to outweigh the cost of going to the allocation functions, so
we don't.  Clearly we will have to allocate more memory one way or
another.

    :::c
      if (pool->blocks && pool->start == pool->blocks->s) {

This condition is true if we have a current block (not true when the
pool is first initialised, for example) _and_ the start pointer is at
the start of the block.  If we have a finished string in the pool,
`start` would have been moved on from the start of the current block
(see the example under _Data Structures_ above and the description of
`poolFinish()` below).  Therefore we have at most one unfinished
string in the pool, the string we are currently working on.  With no
finished strings in the block, there can't be any string pointers in
the rest of the system that point into this block, so we can safely
use `realloc()` to expand the memory; even if it moves the block,
there are no stray pointers that can be confused.

    :::c
        BLOCK *temp;
        int blockSize = (int)((unsigned)(pool->end - pool->start)*2U);
        size_t bytesToAllocate;

        if (blockSize < 0)
          return XML_FALSE;

        bytesToAllocate = poolBytesToAllocateFor(blockSize);
        if (bytesToAllocate == 0)
          return XML_FALSE;

        temp = (BLOCK *)
          pool->mem->realloc_fcn(pool->blocks, (unsigned)bytesToAllocate);
        if (temp == NULL)
          return XML_FALSE;
        pool->blocks = temp;
        pool->blocks->size = blockSize;
        pool->ptr = pool->blocks->s + (pool->ptr - pool->start);
        pool->start = pool->blocks->s;
        pool->end = pool->start + blockSize;
      }

The calculation of the new size of the block is not quite as
straightforward as you might hope.  We are aiming to double the
current allocation, but this could conceivably lead us to sufficiently
enormous numbers that we might overflow an `int`.  The C standard in
its infinite wisdom leaves undefined what happens then, but does
define what happens with _unsigned_ arithmetic and how that relates to
signed values.  The multiple casts in the assignment to `blockSize`
above ensure that no _signed_ overflow ever occurs and the expression
always has a defined result.  Given that we are only doubling, the
result will be negative if a signed overflow would have occurred had we
not been careful.  The convenience function `poolBytesToAllocateFor()`
that converts the character count into a byte count and allows for the
`BLOCK` header does much the same.

Once the potential overflows are out of the way, the reallocation of
the block is straightforward.  Updating the pool fields is then much
like it was for reusing a free block, except that there is no need to
copy the unfinished string (since `realloc()` does that for us).

    :::c
    else {
      BLOCK *tem;
      int blockSize = (int)(pool->end - pool->start);
      size_t bytesToAllocate;

      if (blockSize < 0)
        return XML_FALSE;

      if (blockSize < INIT_BLOCK_SIZE)
        blockSize = INIT_BLOCK_SIZE;
      else {
        /* Detect overflow, avoiding _signed_ overflow undefined behavior */
        if ((int)((unsigned)blockSize * 2U) < 0) {
          return XML_FALSE;
        }
        blockSize *= 2;
      }

      bytesToAllocate = poolBytesToAllocateFor(blockSize);
      if (bytesToAllocate == 0)
        return XML_FALSE;

If the string we are working on is not the only one in the block,
there will be pointers to those strings in other structures in the
program.  That means that we can't use `realloc()` in case it moves
the block, so we have to allocate a new block.  How big a block
depends on the size of the unfinished string.  If it is below the
`INIT_BLOCK_SIZE` threshold, we will allocate `INIT_BLOCK_SIZE`
character units; this will be what happens for a previously unused
string pool.  Otherwise we double the length of the unfinished string,
taking the same trouble as above to ensure that we don't have any
undefined behaviour with signed integer overflows.

Attentive readers may notice that this is much the same decision logic
as is used for extending the
[hash tables](../expat-internals-the-hash-tables/), for much the same
reason.  We wish to avoid calling the allocation functions more often
than we have to, and this exponential growth strategy is a good
compromise between wasting memory and wasting time.

    :::c
        tem = (BLOCK *)pool->mem->malloc_fcn(bytesToAllocate);
        if (!tem)
          return XML_FALSE;
        tem->size = blockSize;
        tem->next = pool->blocks;
        pool->blocks = tem;
        if (pool->ptr != pool->start)
          memcpy(tem->s, pool->start,
                 (pool->ptr - pool->start) * sizeof(XML_Char));
        pool->ptr = tem->s + (pool->ptr - pool->start);
        pool->start = tem->s;
        pool->end = tem->s + blockSize;
      }
      return XML_TRUE;
    }

Once we know how big our `BLOCK` will be, the rest is straightforward.
After allocating it and linking it onto the front of the active block
list, we copy the unfinished string (if there is one) from the
previous block (still pointed to by `pool->start`) to the start of our
new block. Then we set up our working pointers exactly as we did when
we used the free block above.

At the end of this function, either we return 0 for failure or all the
pointers are set up and ready for the pool access functions and macros
to use.

### Building Strings From XML_Chars

There are several ways to assemble a string in a string pool.  The
simplest is to build it character by character using the
`poolAppendChar()` macro.

    :::c
    #define poolAppendChar(pool, c) \
      (((pool)->ptr == (pool)->end && !poolGrow(pool)) \
      ? 0 \
      : ((*((pool)->ptr)++ = c), 1))

This is a macro for efficiency reasons (it is used frequently), and as
such can be confusing to read.  It's easiest to describe as if it were
a function returning a boolean:

    :::c
    static int poolAppendChar(STRING_POOL *pool, XML_Char c)
    {
      if (pool->ptr == pool->end && !poolGrow(pool))
        return 0;
      *(pool->ptr)++ = c;
      return 1;
    }

If the pool isn't full (i.e. `pool->ptr != pool->end`), we copy the
character into place, increment `ptr` and return 1 for success.  If
the pool is full, we try to expand it using `poolGrow()`; if that
fails we return 0, otherwise we insert the character into our now
longer pool as before.

Once the string is complete, including its terminator, a pointer to it
can be obtained using the `poolStart()` macro (which returns the
`start` field of the pool).  The pool is made ready for the next
string by the `poolFinish()` macro, which moves the `start` pointer up
to `ptr` &mdash; this is what I have been referring to when I talked
about "finishing" strings.  Alternatively the string can be discarded
by calling the `poolDiscard()` macro, which moves the `ptr` pointer
back to `start`.

For example, suppose we have added the string "ABCDEF" to the pool but
not yet finished it:

    :::
    +----------------------------------------------...-+
    | [other contents] 'A' 'B' 'C' 'D' 'E' 'F' 0 . ... |
    +----------------------------------------------...-+
                        ^                        ^       ^
                        + start                  + ptr   + end

Calling `poolStart()` returns the pointer `start`, i.e. a pointer to
the start of the string "ABCDEF".  After calling `poolFinish()` we
have:

    :::
    +----------------------------------------------...-+
    | [other contents] 'A' 'B' 'C' 'D' 'E' 'F' 0 . ... |
    +----------------------------------------------...-+
                                                 ^       ^
                                                 + ptr   + end
                                                 + start

leaving the pool ready to build another string.  If instead we had
called `poolDiscard()`, we would get:

    :::
    +----------------------------------------------...-+
    | [other contents] 'A' 'B' 'C' 'D' 'E' 'F' 0 . ... |
    +----------------------------------------------...-+
                        ^                                ^
                        + start                          + end
                        + ptr

and the next characters we add to the pool will overwrite the string
"ABCDEF" that we have now discarded.

In the simple case of copying an existing internally-encoded string,
the function `poolCopyString()` wraps all of the preceding into one
convenient function:

    :::c
    static const XML_Char * FASTCALL
    poolCopyString(STRING_POOL *pool, const XML_Char *s)
    {
      do {
        if (!poolAppendChar(pool, *s))
          return NULL;
      } while (*s++);
      s = pool->start;
      poolFinish(pool);
      return s;
    }

It returns `NULL` (and leaves the pool full of an unfinished string)
if it fails (usually because it has run out of memory), and otherwise
returns a pointer to the copied string.  It can be thought of as
roughly equivalent to `strdup()`.  A similar function,
`poolCopyStringN()` copies a given number of characters from the
source string, which may leave the copied string unterminated.  It is
roughly equivalent to a version of `strndup()` that does not stop when
it reaches a terminator.

The function `poolAppendString()` does almost the same as
`poolCopyString()`, except that it does not copy the final string
terminator and does not "finish" the string with `poolFinish()`.  This
can lead to some confusion; based on the names, one might think that
`poolCopyString()` and `poolAppendString()` can be chained together
like `strcpy()` and `strcat()`.  This is not quite true.  With the
standard library string functions, you join strings by starting with
`strcpy()` and then call `strcat()` for each of the remaining strings.
With the pool functions, you have to call `poolAppendString()` for
each string other than the last one you wish to join, which you add
with `poolCopyString()`.  In other words, the following code snippets
are equivalent (assuming `XML_Char` is the same as `char` for
convenience):

    :::c
    char buffer[10];
    strcpy(buffer, "ABC");
    strcat(buffer, "DEF");
    strcat(buffer, "GHI");
    printf("string = %s\n", buffer);


    STRING_POOL pool;
    XML_Char *string;
    poolInit(&pool);
    poolAppendString(&pool, "ABC");
    poolAppendString(&pool, "DEF");
    string = poolCopyString(&pool, "GHI");
    printf("string = %s\n", string);

### Building Strings From Chars

Sometimes the parser wants to copy part of the input character stream.
`poolAppend()` fulfils this need.  It uses start and end pointers
into the input source since it is unlikely that there will be a
convenient terminator.  To avoid confusion, `poolAppend()` always
converts the input to use the internal character encoding, which makes
the process somewhat more involved.

    :::c
    static XML_Char *
    poolAppend(STRING_POOL *pool, const ENCODING *enc,
               const char *ptr, const char *end)
    {
      if (!pool->ptr && !poolGrow(pool))
        return NULL;

First we check to see if we have a current block at all (i.e. if
`pool->ptr` is not `NULL`), and if not we call `poolGrow()` to get
ourselves one.

    :::c
      for (;;) {
        const enum XML_Convert_Result convert_res =
          XmlConvert(enc, &ptr, end,
                     (ICHAR **)&(pool->ptr),
                     (ICHAR *)pool->end);

        if ((convert_res == XML_CONVERT_COMPLETED) ||
            (convert_res == XML_CONVERT_INPUT_INCOMPLETE))
          break;
        if (!poolGrow(pool))
          return NULL;
      }

I've taken the liberty of respacing the code above to make it more
legible.  The call to `XmlConvert()`, as you may recall from
the [first walkthrough](../expat-internals-a-simple-parse), translates
the input characters from `ptr` to `end` from the input encoding `enc`
to the internal encoding (UTF-8 or UTF-16 depending on how the library
was compiled).  The results are placed into the output buffer starting
at `pool->ptr`, stopping if `pool->end` is reached to allow the output
buffer to be expanded.  Both `ptr` and `pool->ptr` will be updated
when the function returns to point to the next input and output
characters respectively, so that conversion can continue easily.

The use of `ICHAR` rather than `XML_Char` is an unfortunate
wart<sup>[2](#wart)</sup> here; it's trying to draw a distinction that
doesn't really exist between the internal character encoding and what is
presented by the library to user-defined handler functions.

If `XmlConvert()` converts the whole of the input into the string pool
buffer, it will return `XML_CONVERT_COMPLETED` and we will break out
of the loop.  If it converts all of the input that can be converted,
leaving behind only incomplete multi-byte characters, it returns
`XML_CONVERT_INPUT_INCOMPLETE` instead.  This should never happen in
practice; early stages of the parse will filter out incomplete
characters like that, so by the time we want to record strings they
shouldn't occur.  We still break out of the loop because there is
nothing more we can usefully do.  Otherwise we must have run out of
output buffer, so we call `poolGrow()` to get ourselves some more and
loop back to try again.

    :::c
      return pool->start;
    }

By the time we break out of the loop, the `ptr` field will have been
updated to point to the next character insertion point.  We don't
"finish" the string here; we are appending, and there is a good chance
that we will want to append some more input data to the string.
Instead we simply return a pointer to the start of the string and let
the caller call `poolFinish()` if it really wants to.

`poolStoreString()` is very similar to `poolAppend()`, taking
characters from the input stream and converting them into the internal
encoding in a string pool.  The only difference is that
`poolStoreString()` ensures that the string has a `NUL` terminator.
It does _not_ finish the string; as we will see below, it is often the
case that we only want the string copied briefly, and can discard the
copy shortly afterwards.

## How And Why String Pools Are Used

As I mentioned earlier, there are four string pools that the parser
uses; `tempPool` and `temp2Pool` in the parser structure itself, and
`pool` and `entityValuePool` in the DTD structure.  The two pairs of
pools have rather different patterns of use.

The temporary pools are almost exclusively used in a simple manner
that preserves the strings for a relatively short period.  The
processing of `XML_TOK_EMPTY_ELEMENT_WITH_ATTS` is a good example of
this.

    :::c
    name.str = poolStoreString(&tempPool, enc, rawName,
                               rawName + XmlNameLength(enc, rawName));
    if (!name.str)
      return XML_ERROR_NO_MEMORY;
    poolFinish(&tempPool);
    /* ... do stuff ... */
    poolClear(&tempPool);

The code makes a working copy of the tag name using
`poolStoreString()`, which you'll recall does not finish the string so
it has to do that for itself.  It uses this copy for lookup (but not
insertion) in the element hash table and for passing to any start
element handler, end element handler or default handler that may be
defined.  During this processing, `tempPool` is used to hold various
other strings such as attribute names, often to have the implicit
conversion of the input string to internal encoding.  Once it is all
done, the call to `poolClear()` invalidates all of the strings in one
go.  The memory the strings occupy is _not_ freed, but will likely be
re-used in the near future for other strings.

The more permanent pools only ever get `poolClear()` called on them
when the parser is being reset.  They are used in a variety of ways.
First and most obviously they are used to hold the strings passed to
the parser through the function API.  At present that is just the base
URI passed through `XML_SetBase()`; `XML_SetEncoding()` uses a
different mechanism as its semantics are complicated by the parser's
reset behaviour.

A second usage pattern comes from using the string pool as a buffer
for converting the input stream, purely to get a temporary
internally-encoded string.  For example, substituting an entity
reference involves the following code:

    :::c
    name = poolStoreString(&dtd->pool, enc,
                            s + enc->minBytesPerChar,
                            next - enc->minBytesPerChar);
    if (!name)
      return XML_ERROR_NO_MEMORY;
    entity = (ENTITY *)lookup(parser, &dtd->generalEntities, name, 0);
    poolDiscard(&dtd->pool);

Again `poolStoreString()` is used to get an "unfinished" string
converted from the input stream to internal encoding, which is used to
lookup (but not insert) the entity name in the `generalEntities` table
and immediately discarded.

Finally, the DTD string pools are used for permanent storage (for the
lifetime of the parse, at least) of converted input strings, when it
is needed.  A reasonably self-contained example occurs at the start of
`getAttributeId()`, though with a twist:

    :::c
    if (!poolAppendChar(&dtd->pool, XML_T('\0')))
      return NULL;
    name = poolStoreString(&dtd->pool, enc, start, end);
    if (!name)
      return NULL;
    /* skip quotation mark - its storage will be re-used (like in name[-1]) */
    ++name;
    id = (ATTRIBUTE_ID *)lookup(parser, &dtd->attributeIds, name, sizeof(ATTRIBUTE_ID));
    if (!id)
      return NULL;
    if (id->name != name)
      poolDiscard(&dtd->pool);
    else {
      poolFinish(&dtd->pool);

The twist I mentioned is the first `poolAppendChar()`.  The code
cunningly<sup>[3](#cunning)</sup> inserts a spare `XML_Char` at the
start of an attribute ID to track its state.  Exactly what that means
will be the subject of a future article; suffice to say that
namespaces cause us more work than you might at first imagine.  The
subsequent comment, "skip quotation mark", is slightly misleading; the
quotation mark is not part of the copied string, it is the cunningly
inserted leading `NUL` that is being skipped.

That aside, we use `dtd->pool` in a fairly straightforward manner.  We
call `poolStoreString()` to copy the attribute ID into the pool without
"finishing" it, just as we did before, and then use that to look up
the ID in the DTD's hash table of attributes.  `lookup()` will create
a new entry if we had not previously seen this attribute, and will
need a permanently stored name to do that with.  We can tell if this
happened, because then the name returned in `id->name` will be the
same pointer as the `name` we just created with `poolStoreString()`.
If that happens, we call `poolFinish()` to store our string
permanently; otherwise we call `poolDiscard()` to get rid of the
duplicate.

## Conclusions

String pools are one of the more confusing of the parser's internal
features.  When using them, you need to be aware of how your chosen
string pool is being used elsewhere; if you are careless in your
choice of pool, your strings might unexpectedly disappear from under
your feet.  Worse, they might appear to be perfectly intact until
something legitimately overwrites them.

This is the reason why strings passed to handlers must be copied if
the handler wants to keep them for future use.  The strings are
provided through the temporary string pools, and will be cleared once
the parser itself has no more need of them.

Used carefully and correctly, string pools save a lot of time and
effort allocating, converting and freeing input strings.  It is worth
taking the time to understand what you can and cannot do with each
pool, as they can be an invaluable help for marshalling text data in
the right encoding.

## Footnotes

<a name="hanging">1</a>: a common image of a linked list is as a
chain, with each link in the chain being an element of the list.  If
you think of the list head pointer as a loop bolted to the wall, the
rest of the chain hangs down from that loop.  Linked lists (and other
structures) are therefore sometimes said to "hang off" their head
pointers.

<a name="wart">2</a>: "Wart" is used as a term for an unfortunate and
ugly feature in a program, language or similar.  A wart is not
necessarily a bug, it may simply make certain types of development or
usage patterns unnecessarily hard, as in this case.

<a name="cunning">3</a>: something is described as cunning if it is
very clever, often deceitful.  In recent years it has come to have
sarcastic overtones, thanks to
[Blackadder](http://www.bbc.co.uk/programmes/b006xxw3); Baldrick's cry
of "I have a cunning plan, milord" generally introduced a bizarre,
complicated and very stupid suggestion.

&mdash;Rhodri James, 19 July 2017
