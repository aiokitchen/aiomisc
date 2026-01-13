all: clean build

NAME:=$(shell uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['name'])")
VERSION:=$(shell uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

clean:
	rm -vrf *.egg-info dist build

build:
	uv build

install:
	uv sync --group dev

upload: clean build
	uv publish

uml:
	docker run --rm -v $(shell pwd):/mnt -w /mnt hrektts/plantuml \
		java -jar /usr/local/share/java/plantuml.jar \
		-tsvg -o docs/source/_static 'resources/uml/*/**.puml'

test:
	uv run pytest -vv

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

develop: clean
	uv sync --group dev
	uv run pre-commit install

mypy:
	uv run mypy

translate:
	make -C docs/ gettext
	uv run sphinx-intl update -p docs/build/gettext -l ru -d docs/source/locale

build-docs: translate
	make -C docs/ -e BUILDDIR="build/en" html
	make -C docs/ -e SPHINXOPTS="-D language='ru'" -e BUILDDIR="build/ru" html

docs: build-docs
	python -m webbrowser -t "file://$(shell pwd)/docs/build/en/html/index.html"
	python -m webbrowser -t "file://$(shell pwd)/docs/build/ru/html/index.html"
