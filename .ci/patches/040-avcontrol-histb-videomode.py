"""Install the maintained shared-DRM/native-KMS display integration.

Do not embed a second AVControl implementation here: apply-display.py owns
EDID modes, shared DRM ownership and operation without a framebuffer device.
"""
from pathlib import Path
import subprocess
import sys

packaging = Path(__file__).resolve().parents[2] / 'packaging'
subprocess.run([sys.executable, str(packaging / 'apply-display.py'), '.'], check=True)
