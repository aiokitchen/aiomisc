all: bump clean sdist test upload

NAME:=$(shell poetry version -n | awk '{print $1}')
VERSION:=$(shell poetry version -n | awk '{print $2}')

bump:
	poetry build

uml:
	docker run --rm -v $(shell pwd):/mnt hrektts/plantuml \
		java -jar /usr/local/share/java/plantuml.jar \
		-tsvg -o /mnt/docs/source/_static '/mnt/resources/uml/*/**.puml'

sdist: bump uml
	rm -fr dist
	python3 setup.py sdist bdist_wheel

upload: clean sdist
	twine upload dist/*

test:
	tox

test-docker:
	docker run --rm -i -v $(shell pwd):/mnt -w /mnt \
	    snakepacker/python:all tox --workdir /tmp

clean:
	rm -fr *.egg-info .tox dist build

develop: clean
	python3 -m venv .venv
	.venv/bin/pip install pre-commit gray pylava
	.venv/bin/pre-commit install
	.venv/bin/pip install -Ue '.'
	.venv/bin/pip install -Ue '.[develop]'

mypy:
	mypy aiomisc aiomisc_log aiomisc_worker

translate: bump
	make -C docs/ gettext
	sphinx-intl update -p docs/build/gettext -l ru -d docs/source/locale

docs: translate
	make -C docs/ -e BUILDDIR="build/en" html
	make -C docs/ -e SPHINXOPTS="-D language='ru'" -e BUILDDIR="build/ru" html
	python -m webbrowser -t "file://$(shell pwd)/docs/build/en/html/index.html"
	python -m webbrowser -t "file://$(shell pwd)/docs/build/ru/html/index.html"

gray:
	gray aiomisc*
