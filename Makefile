all: bump clean sdist test upload

NAME:=$(shell python3 setup.py --name)
VERSION:=$(shell python3 setup.py --version | sed 's/+/-/g')

bump:
	python3 bump.py aiomisc/version.py

uml:
	docker run --rm -v $(shell pwd):/mnt hrektts/plantuml \
		/usr/bin/java -jar /usr/local/share/java/plantuml.jar \
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
	python3 -m venv env
	env/bin/pip install -Ue '.'
	env/bin/pip install -Ue '.[develop]'

mypy:
	mypy aiomisc/thread_pool.py

translate:
	make -C docs/ gettext
	sphinx-intl update -p docs/build/gettext -l ru -d docs/source/locale
