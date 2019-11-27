all: bump clean sdist test upload

NAME:=$(shell python3 setup.py --name)
VERSION:=$(shell python3 setup.py --version | sed 's/+/-/g')

UML_FILES=$(shell find resources -iname '*.puml')

bump:
	python3 bump.py aiomisc/version.py

define make_svg_uml
	cat $(1) | docker  run --rm -i think/plantuml -tsvg > $(2)
endef

define make_png_uml
	cat $(1) | docker run --rm -i think/plantuml -tpng > $(2)
endef

uml:
	mkdir -p resources/build/uml/circuit-breaker
	$(call make_svg_uml,\
	       resources/source/uml/circuit-breaker/flow.puml,\
	       resources/build/uml/circuit-breaker/flow.svg\
	)

	$(call make_svg_uml,\
	       resources/source/uml/circuit-breaker/states.puml,\
	       resources/build/uml/circuit-breaker/states.svg\
	)

	$(call make_png_uml,\
	       resources/source/uml/circuit-breaker/flow.puml,\
	       resources/build/uml/circuit-breaker/flow.png\
	)
	$(call make_png_uml,\
	       resources/source/uml/circuit-breaker/states.puml,\
	       resources/build/uml/circuit-breaker/states.png\
	)

sdist: bump
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
