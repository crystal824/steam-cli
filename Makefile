.PHONY: changelog changelog-all test build build-skill release-check

changelog:
	git-cliff -o CHANGELOG.md

changelog-all:
	git-cliff --unreleased -o CHANGELOG.md

test:
	PYTHONPATH=src python3 -m pytest -q

build:
	python -m build --outdir dist/python

build-skill:
	python scripts/build_skill.py --output-dir dist/skill

release-check: build build-skill
	python -m twine check dist/python/*
