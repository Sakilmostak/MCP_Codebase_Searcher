import os
from dotenv import load_dotenv
import json
import sys

def load_api_key():
    """
    Loads the Google API key, trying .env first, then environment variables.
    Returns the API key string or None if not found.
    Prints a warning if .env is used but the key isn't in it or if not found at all.
    """
    dotenv_path = os.path.join(os.getcwd(), '.env')
    # print(f"DEBUG: [config.py] Current working directory: {os.getcwd()}", file=sys.stderr)
    # print(f"DEBUG: [config.py] Expected .env path: {dotenv_path}", file=sys.stderr)

    key_loaded_from_dotenv_successfully = False
    dotenv_file_found = os.path.exists(dotenv_path)

    if dotenv_file_found:
        # print(f"DEBUG: [config.py] .env file found at {dotenv_path}", file=sys.stderr)
        try:
            # load_dotenv returns True if it found and loaded a file.
            if load_dotenv(dotenv_path=dotenv_path, override=True, verbose=False):
                if os.getenv('GOOGLE_API_KEY'):
                    key_loaded_from_dotenv_successfully = True
                    # print("DEBUG: [config.py] GOOGLE_API_KEY loaded into os.environ by load_dotenv.", file=sys.stderr)
                # else:
                    # print("DEBUG: [config.py] load_dotenv loaded a .env file, but GOOGLE_API_KEY was not set.", file=sys.stderr)
            # else:
                # print(f"DEBUG: [config.py] load_dotenv({dotenv_path}) returned False (file not loaded, or empty, or only comments).", file=sys.stderr)
        except Exception as e:
            # print(f"DEBUG: [config.py] Exception during load_dotenv: {e}", file=sys.stderr)
            pass # Silently ignore exceptions from load_dotenv itself, will rely on os.getenv check below
    # else:
        # print(f"DEBUG: [config.py] .env file NOT found at {dotenv_path}", file=sys.stderr)

    api_key = os.getenv('GOOGLE_API_KEY')

    if api_key:
        # if key_loaded_from_dotenv_successfully:
            # print("DEBUG: [config.py] API Key found, and it was sourced from .env file loaded by this call.", file=sys.stderr)
        # elif dotenv_file_found: # .env found, but key wasn't successfully loaded from it by this call, must be pre-existing env var
            # print("DEBUG: [config.py] API Key found; .env exists but key was likely from pre-existing environment variables.", file=sys.stderr)
        # else: # .env not found, key must be from pre-existing env var
            # print("DEBUG: [config.py] API Key found, sourced from pre-existing environment variables (.env not found by this call).", file=sys.stderr)
        return api_key
    else:
        # print("DEBUG: [config.py] GOOGLE_API_KEY is NOT in os.environ after all attempts within load_api_key.", file=sys.stderr)
        if dotenv_file_found and not key_loaded_from_dotenv_successfully:
            print(f"Warning: GOOGLE_API_KEY not found. An .env file was found at '{dotenv_path}', but the key was not successfully loaded from it. Also not in pre-existing environment variables.", file=sys.stderr)
        elif not dotenv_file_found:
            print(f"Warning: GOOGLE_API_KEY not found. No .env file was found at '{dotenv_path}'. Also not in pre-existing environment variables.", file=sys.stderr)
        else: # Should ideally not be reached if logic is correct; means key_loaded_from_dotenv_successfully was true but api_key is None.
            print(f"Warning: GOOGLE_API_KEY logic error. Processed .env from '{dotenv_path}' but key not found. Check environment variables.", file=sys.stderr)
        return None

def load_api_key_from_file(file_path):
    """
    Loads the Google API key from a specified JSON configuration file.

    Args:
        file_path (str): Path to the JSON config file.

    Returns:
        str: The API key string or None if not found or file is invalid.
    """
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)
        api_key = config_data.get('GOOGLE_API_KEY')
        if not api_key:
            print(f"Warning: GOOGLE_API_KEY not found in config file: {file_path}", file=sys.stderr)
            return None
        return api_key
    except FileNotFoundError:
        print(f"Warning: Config file not found: {file_path}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in config file: {file_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Error loading config file {file_path}: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    # Example usage:
    key = load_api_key()
    if key:
        print(f"Successfully loaded API key (first 5 chars): {key[:5]}...")
    else:
        print("API key not loaded. Please check your .env file for GOOGLE_API_KEY.") 