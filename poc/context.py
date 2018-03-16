"""Provide context for Proof of Concept Scripts to access telecortex package"""

import sys
import os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
import telecortex
