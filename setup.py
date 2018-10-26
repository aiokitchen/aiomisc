import os

from setuptools import setup, find_packages


from importlib.machinery import SourceFileLoader


module_name = 'aiomisc'

module = SourceFileLoader(
    module_name,
    os.path.join(module_name, '__init__.py')
).load_module()


def load_requirements(fname):
    """ load requirements from a pip requirements file """
    with open(fname) as f:
        line_iter = (line.strip() for line in f.readlines())
        return [line for line in line_iter if line and line[0] != '#']


setup(
    name=module_name.replace('_', '-'),
    version=module.__version__,
    author=module.__author__,
    author_email=module.authors_email,
    license=module.__license__,
    description=module.package_info,
    long_description=open("README.rst").read(),
    platforms="all",
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: Russian',
        'Operating System :: MacOS',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    packages=find_packages(exclude=['tests']),
    install_requires=load_requirements('requirements.txt'),
    extras_require={
        'develop': load_requirements('requirements.dev.txt'),
        'aiohttp': ['aiohttp'],
        'raven': ['raven-aiohttp'],
        'carbon': ['aiocarbon'],
    },
    url='https://github.com/mosquito/aiomisc'
)
