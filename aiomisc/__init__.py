#!/usr/bin/env python
# encoding: utf-8

try:
    from .version import __version__, version_info
except ImportError:
    version_info = (0, 0, 0, 0, 'x')
    __version__ = '{}.{}.{}.{}+{}'.format(*version_info)


authors = (
    ('Dmitry Orlov', 'orlov@edadeal.ru'),
)

# TODO: Use mailing list instead
authors_email = ", ".join(
    '{}'.format(email) for _, email in authors
)

__license__ = 'MIT',
__author__ = ", ".join(
    '{} <{}>'.format(name, email) for name, email in authors
)

package_info = 'Useful utils for asyncio'

# It's same persons right now
__maintainer__ = __author__

__all__ = (
    '__author__', '__author__', '__license__',
    '__maintainer__', '__version__',
    'version_info',
)
