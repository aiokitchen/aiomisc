from setuptools import setup


def version_scheme(version):
    """Custom version: MAJOR.MINOR.COMMITS_SINCE_TAG"""
    if version.exact:
        return f"{version.tag}.0"
    return f"{version.tag}.{version.distance}"


def local_scheme(version):
    """No local version component."""
    return ""


setup(
    use_scm_version={
        "version_scheme": version_scheme,
        "local_scheme": local_scheme,
        "tag_regex": r"^v(?P<version>\d+\.\d+)$",
        "write_to": "aiomisc/version.py",
    }
)
