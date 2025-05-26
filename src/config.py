import os
from dotenv import load_dotenv

def load_api_key():
    """Loads the Google API key from the .env file."""
    load_dotenv()  # Load environment variables from .env file
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Warning: GOOGLE_API_KEY not found in .env file or environment variables.")
        # Depending on strictness, you might want to raise an error here
        # raise ValueError("GOOGLE_API_KEY not found. Please ensure it is set in your .env file.")
    return api_key

if __name__ == '__main__':
    # Example usage:
    key = load_api_key()
    if key:
        print(f"Successfully loaded API key (first 5 chars): {key[:5]}...")
    else:
        print("API key not loaded. Please check your .env file for GOOGLE_API_KEY.") 