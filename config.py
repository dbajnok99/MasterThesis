import os
from dotenv import load_dotenv

load_dotenv()

MODEL           = os.environ.get("MAS_MODEL", "gpt-4o")
MAX_TOKENS      = 4096
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SANDBOX_DIR     = os.path.join(os.path.dirname(__file__), "sandbox")
