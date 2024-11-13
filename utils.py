import os
from exa_py import Exa
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def initialize_exa():
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        raise ValueError('API key must be provided as argument or in EXA_API_KEY environment variable')
    return Exa(api_key)