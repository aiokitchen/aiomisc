all: bump clean sdist test upload

NAME:=$(shell poetry version -n | awk '{print $1}')
VERSION:=$(shell poetry version -n | awk '{print $2}')

clean:
	rm -vrf *.egg-info dist build

bump:
	poetry build


install:
	poetry install


upload: clean sdist
	poetry publish


.venv/bin/python: install
.venv: .venv/bin/python


uml:
	docker run --rm -v $(shell pwd):/mnt -w /mnt hrektts/plantuml \
		java -jar /usr/local/share/java/plantuml.jar \
		-tsvg -o docs/source/_static 'resources/uml/*/**.puml'

sdist: bump uml
	rm -fr dist
	python3 setup.py sdist bdist_wheel


test: .venv
	poetry run pytest -vv


develop: clean
	poetry install
	poetry run pre-commit install


mypy:
	poetry run mypy


reformat:
	poetry run gray aiomisc*


translate: .venv
	make -C docs/ gettext
	sphinx-intl update -p docs/build/gettext -l ru -d docs/source/locale


docs: translate
	make -C docs/ -e BUILDDIR="build/en" html
	make -C docs/ -e SPHINXOPTS="-D language='ru'" -e BUILDDIR="build/ru" html
	python -m webbrowser -t "file://$(shell pwd)/docs/build/en/html/index.html"
	python -m webbrowser -t "file://$(shell pwd)/docs/build/ru/html/index.html"
