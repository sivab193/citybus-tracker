import sys
from unittest.mock import MagicMock

# Allow imports
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastapi'] = MagicMock()

import pytest
if __name__ == '__main__':
    pytest.main(['tests/'])
