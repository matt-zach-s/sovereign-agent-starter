import os
import sys

# Make `import integrations...` and `import main` work when running pytest
# from src/app/ (mirrors PYTHONPATH=/opt/deps + app root at runtime).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
