import os
import platform

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


requirements = ["colorlog"]

if platform.system() == "Linux":
    requirements.append("logging-journald~=0.6.2")


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
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    packages=find_packages(exclude=['tests*']),
    package_data={
        "aiomisc": ["py.typed"],
        "aiomisc_log": ["py.typed"],
        "aiomisc_pytest": ["py.typed"],
        "aiomisc_worker": ["py.typed"],
    },
    install_requires=requirements,
    extras_require={
        'aiohttp': ['aiohttp'],
        'asgi': ['aiohttp-asgi'],
        'carbon': ['aiocarbon~=0.15'],
        'develop': load_requirements('requirements.dev.txt'),
        'raven': ['raven-aiohttp'],
        'uvloop': ['uvloop>=0.14,<1'],
        'cron': ['croniter~=0.3.34'],
    },
    entry_points={
        "pytest11": ["aiomisc = aiomisc_pytest.pytest_plugin"]
    },
    python_requires=">=3.7, <4",
    url='https://github.com/aiokitchen/aiomisc',
    project_urls={
        "Source": "https://github.com/aiokitchen/aiomisc",
        "Tracker": "https://github.com/aiokitchen/aiomisc/issues",
        "Changelog": (
            "https://github.com/aiokitchen/aiomisc/blob/master/CHANGELOG.md"
        ),
        "Documentation": "https://aiomisc.readthedocs.io/en/latest/",
    },
)
