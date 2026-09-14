.PHONY: changelog changelog-all test build build-skill release-check

PYTHON ?= python

changelog:
	git-cliff -o CHANGELOG.md

changelog-all:
	git-cliff --unreleased -o CHANGELOG.md

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

build:
	$(PYTHON) -m build --outdir dist/python

build-skill:
	$(PYTHON) scripts/build_skill.py --output-dir dist/skill

release-check: build build-skill
	$(PYTHON) -m twine check dist/python/*
