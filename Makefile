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

clean:
	rm -fr *.egg-info .tox dist build

develop: clean
	virtualenv -p python3 env
	env/bin/pip install -Ue '.'
	env/bin/pip install -Ue '.[develop]'
