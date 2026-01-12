import platform

import pytest

unix_only = pytest.mark.skipif(platform.system() == "Windows", reason="No unix")
