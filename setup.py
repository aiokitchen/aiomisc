import os

from setuptools import setup, find_packages


from importlib.machinery import SourceFileLoader


module_name = 'aiomisc'

try:
    version = SourceFileLoader(
        module_name,
        os.path.join(module_name, 'version.py')
    ).load_module()

    version_info = version.version_info
except FileNotFoundError:
    version_info = (0, 0, 0)


__version__ = '{}.{}.{}'.format(*version_info)


def load_requirements(fname):
    """ load requirements from a pip requirements file """
    with open(fname) as f:
        line_iter = (line.strip() for line in f.readlines())
        return [line for line in line_iter if line and line[0] != '#']


setup(
    name=module_name,
    version=__version__,
    author='Dmitry Orlov',
    author_email='me@mosquito.su',
    license='MIT',
    description='aiomisc - miscellaneous utils for asyncio',
    long_description=open("README.rst").read(),
    platforms="all",
    classifiers=[
        "Framework :: Pytest",
        'Intended Audience :: Developers',
        'Natural Language :: Russian',
        'Operating System :: MacOS',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    packages=find_packages(exclude=['tests*']),
    package_data={
        "aiomisc": ["py.typed"],
        "aiomisc_log": ["py.typed"],
        "aiomisc_pytest": ["py.typed"],
        "aiomisc_worker": ["py.typed"],
    },
    install_requires=load_requirements('requirements.txt'),
    extras_require={
        'aiohttp': ['aiohttp'],
        'asgi': ['aiohttp-asgi'],
        'carbon': ['aiocarbon~=0.15'],
        'contextvars': ['contextvars~=2.4'],
        'develop': load_requirements('requirements.dev.txt'),
        'raven': ['raven-aiohttp'],
        'uvloop': ['uvloop>=0.14,<1'],
        'cron': ['croniter~=0.3.34'],
        ':python_version < "3.8"': 'typing-extensions',
    },
    entry_points={
        "pytest11": ["aiomisc = aiomisc_pytest.pytest_plugin"]
    },
    url='https://github.com/mosquito/aiomisc'
)
