import os
import fnmatch
import sys

# Default exclusion patterns and extensions
DEFAULT_EXCLUDED_DIRS = ['.git', '__pycache__', 'venv', 'node_modules', '.hg', '.svn']
DEFAULT_EXCLUDED_FILES = ['*.log', '*.tmp', '*.swp', '*.bak']
DEFAULT_BINARY_EXTENSIONS = [
    # Compiled code
    '.pyc', '.pyo', '.o', '.so', '.obj', '.dll', '.exe', '.class', '.jar',
    # Archives
    '.zip', '.tar', '.gz', '.bz2', '.rar', '.7z', '.iso',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.ico',
    # Audio/Video
    '.mp3', '.wav', '.ogg', '.mp4', '.avi', '.mov', '.flv', '.mkv',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt',
    # Other
    '.db', '.sqlite', '.dat'
]

class FileScanner:
    """Scans a directory for files, applying exclusion rules and detecting binary files."""

    def __init__(self, excluded_dirs=None, excluded_files=None, binary_extensions=None, 
                 custom_exclude_patterns=None, exclude_dot_items=True):
        """
        Initializes the FileScanner with exclusion configurations.

        Args:
            excluded_dirs (list, optional): List of directory names to exclude.
                                            Defaults to DEFAULT_EXCLUDED_DIRS.
            excluded_files (list, optional): List of file name patterns (globs) to exclude.
                                             Defaults to DEFAULT_EXCLUDED_FILES.
            binary_extensions (list, optional): List of file extensions to treat as binary.
                                                Defaults to DEFAULT_BINARY_EXTENSIONS.
            custom_exclude_patterns (list, optional): Additional custom glob patterns for exclusion (files or dirs).
            exclude_dot_items (bool, optional): If True (default), generally exclude files/dirs starting with '.'.
        """
        self.excluded_dirs = set(excluded_dirs if excluded_dirs is not None else DEFAULT_EXCLUDED_DIRS)
        self.excluded_files = list(excluded_files if excluded_files is not None else DEFAULT_EXCLUDED_FILES)
        self.binary_extensions = set(binary_extensions if binary_extensions is not None else DEFAULT_BINARY_EXTENSIONS)
        self.custom_exclude_patterns = list(custom_exclude_patterns if custom_exclude_patterns is not None else [])
        self.exclude_dot_items = exclude_dot_items

    def scan_directory(self, root_path):
        """
        Scans the given directory and returns a list of non-excluded, non-binary files.
        (Initially, this will just collect all files; filtering will be added later)

        Args:
            root_path (str): The root directory path to start scanning from.

        Returns:
            list: A list of absolute paths to files found.
        """
        collected_files = []
        normalized_root_path = os.path.abspath(os.path.expanduser(root_path))

        if not os.path.isdir(normalized_root_path):
            print(f"Error: Root path '{normalized_root_path}' is not a valid directory.", file=sys.stderr)
            return []

        for dirpath, dirnames, filenames in os.walk(normalized_root_path):
            # Filter out excluded directories before descending
            original_dirnames = list(dirnames) # Iterate over a copy for safe modification
            dirnames[:] = [] # Clear original list to rebuild
            for dirname in original_dirnames:
                current_dir_abs_path = os.path.join(dirpath, dirname)
                if not self._is_excluded(current_dir_abs_path, normalized_root_path, is_dir=True):
                    dirnames.append(dirname)
            
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                is_excluded_flag = self._is_excluded(file_path, normalized_root_path, is_dir=False)
                is_binary_flag = self._is_binary(file_path)

                if not is_excluded_flag and not is_binary_flag:
                    collected_files.append(file_path)
        
        return collected_files

    def _is_excluded(self, path_to_check, scan_root_path, is_dir=False):
        """
        Checks if a given file or directory path should be excluded based on configuration.

        Args:
            path_to_check (str): The absolute path to the file or directory.
            scan_root_path (str): The absolute path to the root of the scan.
            is_dir (bool): True if path_to_check is a directory, False if it's a file.

        Returns:
            bool: True if the path should be excluded, False otherwise.
        """
        basename = os.path.basename(path_to_check)
        normalized_path = os.path.normpath(path_to_check)
        # Ensure scan_root_path is absolute and expanded for relpath calculation
        normalized_scan_root_path = os.path.abspath(os.path.expanduser(scan_root_path))
        relative_path = os.path.relpath(normalized_path, normalized_scan_root_path)

        # General check for dot items if enabled
        if self.exclude_dot_items and basename.startswith('.'):
            # However, allow if it's the scan root itself (e.g. scanning ".")
            if normalized_path == normalized_scan_root_path and basename == ".": # an edge case, scanning "." itself
                pass # Do not exclude the scan root itself if it's "."
            elif normalized_path == normalized_scan_root_path and is_dir: # If path_to_check is the scan root dir
                pass # Don't exclude the root dir itself based on its name, allow descent
            else:
                return True

        if is_dir:
            if basename in self.excluded_dirs:
                return True
            
            for pattern in self.custom_exclude_patterns:
                # Option 1: Pattern explicitly targets a directory with a trailing slash (e.g., "build/")
                if pattern.endswith(os.sep) or pattern.endswith('/'):
                    if fnmatch.fnmatch(relative_path + os.sep, pattern) or \
                       fnmatch.fnmatch(basename, pattern.rstrip(os.sep + '/')):
                        return True
                # Option 2: Pattern implies a directory and its contents (e.g., "build/*")
                elif pattern.endswith('/*') and not pattern.endswith('//*'):
                    pattern_base = pattern[:-2]  # Extracts "build" from "build/*"
                    
                    if basename == pattern_base or relative_path == pattern_base:
                        return True
                # Option 3: General glob match on basename or relative_path for other patterns
                # that are not explicitly file patterns (don't contain typical file extensions)
                # This is heuristic; specific file patterns are handled in the 'else' block
                elif not any(ext in pattern for ext in ['.', '*']) and (fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(relative_path, pattern)):
                    # If pattern looks like a dir name (no typical file wildcards/extensions) and matches
                    return True
        else: # This is a file
            # Check against default excluded file patterns (globs on basename)
            for pattern in self.excluded_files:
                if fnmatch.fnmatch(basename, pattern):
                    return True
            
            # Check against custom exclude patterns (globs on basename and relative path)
            for pattern in self.custom_exclude_patterns:
                # If pattern ends with /, it's a directory pattern, skip for files
                if pattern.endswith(os.sep) or pattern.endswith('/'):
                    continue
                if fnmatch.fnmatch(basename, pattern):
                    return True
                if fnmatch.fnmatch(relative_path, pattern):
                    return True

        return False # Default to not excluded if no rules matched

    def _is_binary(self, file_path):
        """Check if a file is likely binary. Extends checks beyond just extensions."""
        # First, check by extension (common binary types)
        _, ext = os.path.splitext(file_path)
        if ext.lower() in self.binary_extensions:
            return True

        # Second, try to read a chunk and check for null bytes or too many non-text chars
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024) # Read the first 1KB
            if not chunk: # Empty file is not considered binary for our purposes
                return False
            
            # Heuristic 1: Presence of null byte
            if b'\0' in chunk:
                return True

            # Heuristic 2: High proportion of non-text characters
            # This is a more complex heuristic and might need adjustment.
            # For simplicity, we can check the proportion of non-printable ASCII or non-UTF8 decodable bytes.
            # Using a simple check for common text characters for now.
            text_characters = "".join(map(chr, range(32, 127))) + "\n\r\t\b"
            non_text_chars = 0
            for byte in chunk:
                if chr(byte) not in text_characters:
                    non_text_chars += 1
            
            # If more than, say, 30% of the chunk are non-text characters, assume binary.
            # This threshold is arbitrary and might need tuning.
            if non_text_chars / len(chunk) > 0.30:
                return True
                
        except IOError as e:
            # If we can't read the file for binary check (e.g., permission denied, or file disappeared)
            # print a warning and default to not treating it as binary to be safe.
            print(f"Warning: Could not read file {file_path} to check if binary: {e}. Assuming non-binary.", file=sys.stderr)
            return False # Default to False if read fails
        except Exception as e:
            # Catch any other unexpected error during binary check
            print(f"Warning: Unexpected error checking if file {file_path} is binary: {e}. Assuming non-binary.", file=sys.stderr)
            return False

        return False

if __name__ == '__main__':
    # This block is now primarily for potential standalone execution or basic checks,
    # comprehensive tests are in test_file_scanner.py
    print("FileScanner class defined. To run tests, execute test_file_scanner.py")
    
    # Example of how to use FileScanner if run directly (optional):
    # scanner = FileScanner()
    # files = scanner.scan_directory('.') # Scan current directory
    # print(f"Scanned files in current directory: {len(files)}")
    # for f in files[:5]: # Print first 5 found
    #     print(f"  {f}")