# 潮鳴りの密室 (SFC command adventure) and 夜鳴き鐘 (SFC sound novel).  Run python3 tools/bootstrap.py first
# (add --with-emulator for the tests).
.DEFAULT_GOAL := all
PYTHON ?= python3
CA65 ?= tools/vendor/cc65-2.19/bin/ca65
LD65 ?= tools/vendor/cc65-2.19/bin/ld65
.PHONY: all test clean FORCE

all: adv yonaki
test: adv-test yonaki-test
clean: adv-clean yonaki-clean

FORCE:

# ---- 潮鳴りの密室: SFC command adventure (build/adv/shionari.sfc -> dist/shionari.sfc) ----
.PHONY: adv adv-test adv-release adv-clean
ADV_SRC := src/adv/shionari.s src/adv/adv.cfg $(wildcard src/adv/*.inc)

adv: build/adv/shionari.sfc

build/adv/data.inc: FORCE
	$(PYTHON) -I tools/adv/build.py

build/adv/shionari.o: build/adv/data.inc $(ADV_SRC) FORCE
	$(CA65) -g -I . src/adv/shionari.s -o $@ -l build/adv/shionari.lst

build/adv/shionari.sfc: build/adv/shionari.o FORCE
	$(LD65) -C src/adv/adv.cfg build/adv/shionari.o -o $@ -m build/adv/shionari.map -Ln build/adv/labels.txt
	$(PYTHON) -I tools/adv/romfix.py $@

# pad-only tests on the unmodified Snes9x 1.63 libretro core (build/adv/tests.json), the lip-sync tests
# (build/adv/lipsync/RESULTS.json), the speech-blip tests on the native PCM (build/adv/speech/RESULTS.json),
# then the same pad traces and battery images replayed on the pinned
# bsnes 115 core (build/adv/bsnes/RESULTS.json)
adv-test: adv
	$(PYTHON) -I tests/adv/run.py
	$(PYTHON) -I tests/adv/lipsync.py
	$(PYTHON) -I tests/adv/speech.py
	$(PYTHON) -I tests/adv/bsnes.py

# tested ROM + byte-identical clean rebuild (build/adv-clean) -> dist/shionari.sfc
adv-release: adv-test
	$(PYTHON) -I tools/adv/release.py

adv-clean:
	rm -rf build/adv build/adv-clean

# ---- 夜鳴き鐘: SFC sound novel (build/yonaki/yonaki.sfc -> dist/yonaki.sfc) ----
# YONAKI_FLAGS: extra build.py options (--scenario DIR, --allow-missing-art, --strict, ...)
.PHONY: yonaki yonaki-test yonaki-release yonaki-clean
YONAKI_SRC := src/yonaki/yonaki.s $(wildcard src/yonaki/*.inc)
YONAKI_FLAGS ?=

yonaki: build/yonaki/yonaki.sfc

build/yonaki/data.inc: FORCE
	$(PYTHON) -I tools/yonaki/build.py $(YONAKI_FLAGS)

build/yonaki/yonaki.o: build/yonaki/data.inc $(YONAKI_SRC) FORCE
	$(CA65) -g -I . -I build/yonaki src/yonaki/yonaki.s -o $@ -l build/yonaki/yonaki.lst

build/yonaki/yonaki.sfc: build/yonaki/yonaki.o FORCE
	$(LD65) -C build/yonaki/yonaki.cfg build/yonaki/yonaki.o -o $@ -m build/yonaki/yonaki.map -Ln build/yonaki/labels.txt
	$(PYTHON) -I tools/yonaki/romfix.py $@

# pad-only tests on the unmodified Snes9x 1.63 libretro core with the fixture scenario (tests/yonaki/fixture ->
# build/yonaki-test/), the real scenario played to every ending (--real), then the same pad traces and battery
# images replayed on the pinned bsnes 115 core (build/yonaki-test/bsnes/RESULTS.json)
yonaki-test: yonaki
	$(PYTHON) -I tests/yonaki/run.py --real
	$(PYTHON) -I tests/yonaki/bsnes.py

# tested ROM -> dist/yonaki.sfc
yonaki-release: yonaki-test
	cp build/yonaki/yonaki.sfc dist/yonaki.sfc
	cd dist && shasum -a 256 yonaki.sfc > yonaki.sfc.sha256

yonaki-clean:
	rm -rf build/yonaki build/yonaki-test
