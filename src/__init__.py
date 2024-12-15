"""
Project initialization module.
Handles package-level imports and configurations.
"""

# Import key modules to make them easily accessible
from .llama_model import LLAMAModel
from .server import start_server

# Optional: Package-level configurations
__version__ = "0.1.0"
__all__ = [
    "LLAMAModel",
    "start_server"
]

# Optional: Logging configuration
import logging

# Configure package-level logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)