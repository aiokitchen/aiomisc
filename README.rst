aiomisc - miscellaneous utils for asyncio
=========================================

.. image:: https://coveralls.io/repos/github/aiokitchen/aiomisc/badge.svg?branch=master
   :target: https://coveralls.io/github/aiokitchen/aiomisc
   :alt: Coveralls

.. image:: https://github.com/aiokitchen/aiomisc/workflows/tox/badge.svg
   :target: https://github.com/aiokitchen/aiomisc/actions?query=workflow%3Atox
   :alt: Actions

.. image:: https://img.shields.io/pypi/v/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/
   :alt: Latest Version

.. image:: https://img.shields.io/pypi/wheel/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/pyversions/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/l/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/


Miscellaneous utils for asyncio.

The complete documentation is available in the following languages:

* `English documentation`_
* `Russian documentation`_

.. _English documentation: https://aiomisc.readthedocs.io/en/latest/
.. _Russian documentation: https://aiomisc.readthedocs.io/ru/latest/

.. contents:: Table of contents

Installation
------------

Installing from pypi:

.. code-block:: bash

    pip3 install aiomisc

With uvloop_:

.. code-block:: bash

    pip3 install "aiomisc[uvloop]"


With aiohttp_:

.. code-block:: bash

    pip3 install "aiomisc[aiohttp]"


Installing from github.com:

.. code-block:: bash

    pip3 install git+https://github.com/aiokitchen/aiomisc.git
    pip3 install \
        https://github.com/aiokitchen/aiomisc/archive/refs/heads/master.zip


.. _uvloop: https://pypi.org/project/uvloop
.. _aiohttp: https://pypi.org/project/aiohttp

Versioning
----------

This software follows `Semantic Versioning`_

Summary: it's given a version number MAJOR.MINOR.PATCH, increment the:

* MAJOR version when you make incompatible API changes
* MINOR version when you add functionality in a backwards compatible manner
* PATCH version when you make backwards compatible bug fixes
* Additional labels for pre-release and build metadata are available as
  extensions to the MAJOR.MINOR.PATCH format.

In this case, the package version is assigned automatically with poem-plugins_,
it using on the tag in the repository as a major and minor and the counter,
which takes the number of commits between tag to the head of branch.

.. _poem-plugins: https://pypi.org/project/poem-plugins


How to develop?
---------------

Should be installed:

* `virtualenv`
* GNU Make as `make`
* Python 3.5+ as `python3`


For setting up developer environment just type

    .. code-block::

        # install development dependencies
        $ poetry install

        # Install pre-commit git hook
        $ poetry run pre-commit install


.. _Semantic Versioning: http://semver.org/
