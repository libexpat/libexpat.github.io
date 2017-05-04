# Copyright (C) 2017 Sebastian Pipping <sebastian@pipping.org>
# Licensed under the MIT license

PELICAN = pelican

GENERATED = '*.html' doc/ theme/

.PHONY: all
all:
	$(PELICAN) -o . -s pelicanconf.py content 

.PHONY: clean
clean:
	git checkout HEAD -- $(GENERATED)

.PHONY: require-clean-git
require-clean-git:
	git diff --quiet
	git diff --cached --quiet

.PHONY: sync
sync:
	$(MAKE) clean require-clean-git all
	git add -- $(GENERATED)
	git commit \
		-m 'Sync generated files ("make sync")'
