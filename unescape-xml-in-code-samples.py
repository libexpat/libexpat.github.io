#! /usr/bin/env python3
# Copyright (C) 2019 Sebastian Pipping <sebastian@pipping.org>
# Licensed under the MIT license

import argparse
import re


def process_file(filename):
    with open(filename, 'r') as f:
        content = f.read()

    chunks = []
    prev_end = 0
    inside_pre = False

    for match in re.finditer(
            '(?P<open_pre><pre>)'
            '|(?P<close_pre></pre>)'

            '|(?P<lt1>&amp;lt;)'
            '|(?P<lt2>&amp;</span>lt<span class="p">;)'
            '|(?P<lt3>&amp;</span><span class="n">lt</span><span class="p">;)'

            '|(?P<gt1>&amp;gt;)'
            '|(?P<gt2>&amp;</span>gt<span class="p">;)'
            '|(?P<gt3>&amp;</span><span class="n">gt</span><span class="p">;)'

            '|(?P<amp1>&amp;amp;)'
            '|(?P<amp2>&amp;</span><span class="n">amp</span><span class="p">;)'
            , content):
        gap = content[prev_end:match.start()]
        chunks.append(gap)

        if inside_pre:
            if match.group('lt1') or match.group('lt2') or match.group('lt3'):
                text = '&lt;'
            elif match.group('gt1') or match.group('gt2') or match.group('gt3'):
                text = '&gt;'
            elif match.group('amp1') or match.group('amp2'):
                text = '&amp;'
            else:
                if match.group('close_pre'):
                    inside_pre = False
                text = match.group()
        else:
            if match.group('open_pre'):
                inside_pre = True
            text = match.group()

        chunks.append(text)

        prev_end = match.end()

    chunks.append(content[prev_end:])

    with open(filename, 'w') as f:
        f.write(''.join(chunks))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='+')
    config = parser.parse_args()

    for filename in config.filenames:
        process_file(filename)
