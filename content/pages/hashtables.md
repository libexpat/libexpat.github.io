Title: Expat Internals: The Hash Tables
Date: 29 June 2017
License: MIT
Category: Maintenance
Tags: internal, hashing
Author: Rhodri James
Summary: How the parser's hash tables work

_Written by Rhodri James_


In the [first walkthrough](../expat-internals-a-simple-parse/), I
mentioned the parser's hash tables without giving much detail.  In
this article I'm going to give you some of that detail.  I'm not going
to look too closely at the hashing algorithm itself
(it's [SipHash](https://131002.net/siphash/siphash.pdf) for the
curious), but I will look at how it is used to implement tables in
Expat.

## Absolute Basics

For the benefit of those who haven't heard this a million times before
in Computer Science lectures,
a [_hash table_](https://en.wikipedia.org/wiki/Hash_table) is a data
structure that associates a piece of data with a "key", as distinct
from an [_array_](https://en.wikipedia.org/wiki/Array_data_structure)
which associates a piece of data with an integer index.  It is a
common data structure in high level languages such as Perl or Python,
but in a lower level language like C<sup>[1](#C)</sup> we need to
implement our own version.

In our case the key is a text string in the parser's internal encoding
(UTF-8 or UTF-16 depending on the compile-time flag `XML_UNICODE`).
The key is passed through the hashing algorithm and converted into an
index into the hash table's internal array, where the associated data
will be found.  Of course it's not quite that simple, or we wouldn't
need a whole article to examine them.

## Expat's Hash Tables

The parser uses hash tables for the things it will need to look up by
name.
[Elements](https://www.w3.org/TR/2008/REC-xml-20081126/#dt-element)
and [element type
declarations](https://www.w3.org/TR/2008/REC-xml-20081126/#elemdecls) are
held in a hash table, for instance, as are
[general entities](https://www.w3.org/TR/2008/REC-xml-20081126/#gen-entity),
[parameter entities](https://www.w3.org/TR/2008/REC-xml-20081126/#dt-PE),
[namespace prefixes](https://www.w3.org/TR/xml-names/#dt-prefix) and
so on.  These tables all use a single common set of data structures:

    :::c
    typedef const XML_Char *KEY;

    typedef struct {
      KEY name;
    } NAMED;

    typedef struct {
      NAMED **v;
      unsigned char power;
      size_t size;
      size_t used;
      const XML_Memory_Handling_Suite *mem;
    } HASH_TABLE;

The important field here is `v`; this is the actual table, implemented
as an array of pointers to `NAMED` structures, which are themselves
pointers to the key for each entry.  There is heavy use of pointers
here for several reasons; it allows the table to be dynamically
resized when we add more entries, and does not need to know the size
of keys or table entries in advance.  The last reason there may look
like it's unnecessary &mdash; surely we know the size of `NAMED` at
compile time? &mdash; but we will see later why we want the
flexibility.

Hash tables are initialised using the function `hashTableInit()`
unsurprisingly.  This starts us off with a `NULL` pointer in the `v`
field, `mem` pointing to the suite of memory allocation functions
being used by the parser, and all other fields set to zero.  A
completely empty table, in other words, taking up minimal space.

## Inserting The First Entry

If you recall from the [previous
walkthrough](../expat-internals-a-simple-parse/), the Expat library
mostly interacts with hash tables using the `lookup()` function, both
to find entries as you might expect and to add new ones.  Let's walk
through what the code does when we call `lookup()` asking it to insert
a new entry.

    :::c
    static NAMED *
    lookup(XML_Parser parser, HASH_TABLE *table, KEY name, size_t createSize)
    {
      size_t i;
      if (table->size == 0) {
        size_t tsize;
        if (!createSize)
          return NULL;

Let's assume that we have "foo" as a key (i.e. `name == "foo"`, and
let's also assume that our internal representation is UTF-8 for
simplicity), and we want 20 bytes for our data (i.e. `createSize ==
20`).  Entering `lookup()`, we first check to see if we have a table
allocated at all by checking the `size` field, the number of slots
allocated in the table.  For our empty table this is zero, so we next
check if we are being asked to create a new entry, i.e. whether
`createSize` is non-zero.  If we were just trying to look something up
in an empty table, we would return `NULL` at this point.

    :::c
        table->power = INIT_POWER;
        /* table->size is a power of 2 */
        table->size = (size_t)1 << INIT_POWER;
        tsize = table->size * sizeof(NAMED *);
        table->v = (NAMED **)table->mem->malloc_fcn(tsize);
        if (!table->v) {
          table->size = 0;
          return NULL;
        }
        memset(table->v, 0, tsize);

Having decided we need a new table, we create it.  As the comment in
the code says, our table size is always a power of two for general
convenience later on.  To help with that, as well as keeping the
number of entries in the `size` field, we keep the power of two in the
`power` field and take some pains to ensure that `table->size` is
always the same as `(size_t)1 << table->power`.  We start off with 64
(2<sup>6</sup>) entries, enough for a modest-sized table that will fit
small parses without wasting too much memory.

We then allocate enough memory for `size` pointers to `NAMED`
structures using the memory allocation functions held in the table,
tidying up and returning `NULL` if we failed.  This new memory is set
to all zero, giving us a table of `NULL` pointers.

    :::c
        i = hash(parser, name) & ((unsigned long)table->size - 1);
      }

Our last act when creating a new table is to pass the key "foo" to the
hashing algorithm, which will convert it into an `unsigned long`.
That value then gets turned into an index by taking the remainder of
dividing it by the number of entries in the table, something that can
be done quickly and easily with a bitwise and since we made our table
size a power of two (2<sup>n</sup>-1 will always have the least
significant _n_ bits set to one and the rest zeroes,
e.g. 2<sup>6</sup>-1 is `0b111111` (63)).  The resulting index `i` is
the table entry we will pick.

    :::c
      table->v[i] = (NAMED *)table->mem->malloc_fcn(createSize);
      if (!table->v[i])
        return NULL;
      memset(table->v[i], 0, createSize);
      table->v[i]->name = name;
      (table->used)++;
      return table->v[i];
    }

Finally we create the entry, allocating the requested number of bytes
and returning `NULL` if we fail to get them.  We clear the allocated
memory and then pretend that we have allocated a `NAMED` structure.
This is an old programmers' trick for storing an arbitrary data
structure, which unlike many old programmers' tricks still works
today.  If you recall, `NAMED` just contains a pointer to a `KEY`, and
we copy the pointer `name` we have for the key into place.  Notice
here that we don't copy the key itself, just the pointer; the key we
were given must exist for the whole lifetime of the hash table.  That
is why the parser often copies names it wishes to look up into string
pools, to ensure the name will persist.

The other implication here is that all the structures that are stored
in hash tables must begin with a `const XML_Char *` field that is the
entry's key, whether or not they intend to use it.  The contents of
that field _must not change_, nor should the pointer itself be
changed; it is highly likely that you would break the table and lose
the entry if you did change it.

Finally we keep a count of the number of entries in the table in the
field `used`, so we increment it now.  We could simply walk through
the table counting up the non-`NULL` entries whenever we needed to
know, but that would get expensive and tedious for big tables.

## Collisions

Well, you might think, that was easy.  What's all the fuss about?  We
just call the hash function, allocate the memory and stick it in the
relevant slot.  What's hard about that?

Problems arise, of course, because our hash function may give us the
same slot index for different keys.  What happens then?  Let's run
through `lookup()` again to insert the key "bar", and assume that by
some horrible mischance<sup>[2](#mischance)</sup> it hashes to the
same table entry as "foo" did.

    :::c
    static NAMED *
    lookup(XML_Parser parser, HASH_TABLE *table, KEY name, size_t createSize)
    {
      size_t i;
      if (table->size == 0) {
        /* ... */
      }
      else {
        unsigned long h = hash(parser, name);
        unsigned long mask = (unsigned long)table->size - 1;
        unsigned char step = 0;
        i = h & mask;
        while (table->v[i]) {
          if (keyeq(name, table->v[i]->name))
            return table->v[i];
          if (!step)
            step = PROBE_STEP(h, mask, table->power);
          i < step ? (i += table->size - step) : (i -= step);
        }
        if (!createSize)
          return NULL;

We start off by creating our candidate index `i` as before, hashing
the key and masking it down to the size of the table.  If this gives
us a slot in the table that already has an entry, we check to see if
it has the same key as the one we want to insert.  In this case "bar"
is not the same as "foo", so `keyeq()` (a character-by-character
comparison function) returns false.  If it had been the same key, we
would have returned the table entry without further ado.

Since we do have a different table entry, we have to figure out where
in the table to look next.  We do this by stepping backwards through
the table by an amount determined by the original hash value and the
table size, wrapping around and continuing until we find either an
empty slot or the key we are looking for.  For reasons we will see
later, this will always terminate.

The `PROBE_STEP` macro is defined as follows:

    :::c
    #define SECOND_HASH(hash, mask, power) \
      ((((hash) & ~(mask)) >> ((power) - 1)) & ((mask) >> 2))
    #define PROBE_STEP(hash, mask, power) \
      ((unsigned char)((SECOND_HASH(hash, mask, power)) | 1))

Remember that our original index calculation was to take the least
significant `table->power` bits of the hash value.  `SECOND_HASH()`
takes the next `table->power - 3` bits of the hash
value<sup>[3](#hashcalc)</sup>, which has a good chance of being
different from the step we might calculate if a third key collided
with "foo" in the future.  This improves our chances of getting the
right entry within a couple of steps; the fewer steps we have to take,
the faster our parser will be.

`PROBE_STEP()` then ensures that our step is an odd number.  This will
always be [co-prime](https://en.wikipedia.org/wiki/Coprime_integers)
with the size of the table (a power of two, remember), so we guarantee
to be able to step through every slot in the table.  As long as we
haven't completely filled our table, we will find a slot for our key
eventually.

## Extending the Table

    :::c
        /* check for overflow (table is half full) */
        if (table->used >> (table->power - 1)) {
          unsigned char newPower = table->power + 1;
          size_t newSize = (size_t)1 << newPower;
          unsigned long newMask = (unsigned long)newSize - 1;
          size_t tsize = newSize * sizeof(NAMED *);
          NAMED **newV = (NAMED **)table->mem->malloc_fcn(tsize);
          if (!newV)
            return NULL;
          memset(newV, 0, tsize);

"Eventually", of course, could be a very long time in a large
almost-full table.  To increase our chances of finding an empty slot
quickly, we make sure that the table never gets more than half full.
This is only a little wasteful of space &mdash; pointers don't take up
that much memory &mdash; but saves a lot of time on average.

When we hit the half-full point, you might expect the code to simply
`realloc()` more table and just carry on.  Recall, however, that our
index calculations depended on the table size; if we just extended the
table, we would start looking for old keys in the wrong slot.  Instead
we have to allocate ourselves a whole new table `newV` and re-hash our
old entries into their new places.  This is an expensive operation, so
we don't want to do it too often during a parse!  Ensuring the table
size is always a power of two gives us exponential growth, which helps
keep the number of expansions down.

    :::c
          for (i = 0; i < table->size; i++)
            if (table->v[i]) {
              unsigned long newHash = hash(parser, table->v[i]->name);
              size_t j = newHash & newMask;
              step = 0;
              while (newV[j]) {
                if (!step)
                 step = PROBE_STEP(newHash, newMask, newPower);
                j < step ? (j += newSize - step) : (j -= step);
              }
              newV[j] = table->v[i];
            }
          table->mem->free_fcn(table->v);
          table->v = newV;
          table->power = newPower;
          table->size = newSize;

This looks almost exactly like the hash-mask-and-step routine we just
saw, mostly because it is exactly the same routine.  It may result in
different keys getting their preferred index slot as opposed to having
to step to other slots, but that simply evens up the average access
time.

Once the new table is populated, we free the old table and update the
relevant fields of the main `HASH_TABLE` structure.  At this point we
have a consistent hash table again, but we haven't yet inserted our
new entry.

    :::c
          i = h & newMask;
          step = 0;
          while (table->v[i]) {
            if (!step)
              step = PROBE_STEP(h, newMask, newPower);
            i < step ? (i += newSize - step) : (i -= step);
          }

One more time around the hash-mask-and-step routine, this time using
the hash value for our new key (calculated early on in the function)
and the new table size.  As before, this will eventually lead us to an
empty slot to put an entry for "bar" in.

Whether or not we needed to extend the table, `i` will now contain the
index of the slot we want.  We add the new entry to the table exactly
as we did the first time.

## Iterating Through Tables

We've seen how lookups and insertions in hash tables work, and you can
take it from the fact I haven't mentioned them before that there are
no deletions from these tables!  That's most of the interactions that
the library has with hash tables, but not quite all.  Sometimes the
code needs to loop through all entries in a hash table for some
reason.  To do this, it uses a `HASH_TABLE_ITER` structure and the
functions `hashTableIterInit()` and `hashTableIterNext()`.

    :::c
    typedef struct {
      NAMED **p;
      NAMED **end;
    } HASH_TABLE_ITER;

A hash table iterator is a simple beast.  All it contains is a
"current pointer" `p` into the table and an "end pointer" `end` to
tell it where to stop.  The functions are similarly simple:

    :::c
    static void FASTCALL
    hashTableIterInit(HASH_TABLE_ITER *iter, const HASH_TABLE *table)
    {
      iter->p = table->v;
      iter->end = iter->p + table->size;
    }

You initialise an iterator by setting its current pointer to the start
of the table and its end pointer to just past the end of the table.

    :::c
    static NAMED * FASTCALL
    hashTableIterNext(HASH_TABLE_ITER *iter)
    {
      while (iter->p != iter->end) {
        NAMED *tem = *(iter->p)++;
        if (tem)
          return tem;
      }
      return NULL;
    }

You get the next entry out of your iterator by returning the contents
of the first non-empty slot you come across, leaving the "current
pointer" pointing to the next possibility.  Once you run off the end
of the table, return `NULL`.  Simples.<sup>[4](#simples)</sup>

The code to run through a hash table is then just:

    :::c
    HASH_TABLE_ITER foo_iter;
    hashTableIterInit(&foo_iter, &foo_table);
    for (;;) {
      FOO_ENTRY *foo = (FOO_ENTRY *)hashTableIterNext(&foo_iter);
      if (!foo)
        break;
      do_something_with(foo);
    }

## Final Notes

In general, hash tables as the Expat library uses them are not such
fearsome beasts.  The most confusing thing about them is that the
function `lookup()` is used for both lookup and insertion, something
that can catch even experienced programmers by surprise.

They do have one big "gotcha"; the key you look up _must_ persist in
memory for as long as the hash table, and mustn't be altered in any
way once it has been inserted.  This may make sense of some of the
twisty paths the parser code goes through on what looks like it should
be a simple table look-up.

That's almost everything you need to know about hash tables in Expat.
There is one last little efficiency saving that the parser makes that
usually isn't relevant, but does affect some of the test suite for the
library.  If you reset a parser (with `XML_ParserReset()`) to clear it
for re-use, this does not fully delete the parser's hash tables.  All
of the entries are removed and their memory freed, but the table
itself, the `v` field, is not freed.  This saves a little time; if the
input that the parser is about to be fed is similar to the one it
finished with earlier, hopefully we will have the right size of table
pre-allocated and not have to do the expensive table expansion again.

## Footnotes

<a id="C">1</a>: the best description I've heard of C is "it's an
excellent macro-assembler."  C language constructs map to a relatively
small number of assembler language instructions on most
microprocessors.  As a result, it's not at all uncommon for embedded C
programmers to take careful note of the assembly language output of
their compilers.

<a id="mischance">2</a>: bad luck.

<a id="hashcalc">3</a>: the calculation in `SECOND_HASH()` is a bit
confusing (I misread it the first time I studied it!), so let's lay it
out here.  Assume that `power` is 6 (and `mask` is therefore
`0b111111`), and suppose that our hash is `0b1111111111111111` to make
the masking stand out (and because I can't be bothered to type more
than 16 bits).  Therefore:

    :::
    hash & ~mask                                = 0b1111111111000000

    (hash & ~mask) >> (power-1)                 = 0b0000011111111110

    ((hash & ~mask) >> (power-1)) & (mask >> 2) = 0b0000000000001110

So we use the next three (`power-3`) bits of the hash, shifted left
one bit.  The least significant bit will then be set to one by
`PROBE_STEP()`, so no information is wasted.

<a id="simples">4</a>: I'm sorry, I appear to have become infested
with [meerkats](https://en.wikipedia.org/wiki/Compare_the_Meerkat).

&mdash;Rhodri James, 29th June 2017
