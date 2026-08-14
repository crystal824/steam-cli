.PHONY: changelog changelog-all test

changelog:
	git-cliff -o CHANGELOG.md

changelog-all:
	git-cliff --unreleased -o CHANGELOG.md

test:
	PYTHONPATH=src python3 -m pytest -q
