all: bump clean sdist test upload

NAME:=$(shell python3 setup.py --name)
VERSION:=$(shell python3 setup.py --version | sed 's/+/-/g')

bump:
	python3 bump.py aiomisc/version.py

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
