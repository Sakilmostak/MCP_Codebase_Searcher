# Project TODOs

## FileScanner Module (`file_scanner.py`)

### 1. Implement Directory Exclusion Logic in `_is_excluded` and `scan_directory` (DONE)
- **File:** `file_scanner.py`
- **Method:** `_is_excluded(self, file_path, root_path)`
- **Lines (approximate for `_is_excluded` definition):** Around line 70
- **Method (usage):** `scan_directory(self, root_path)`
- **Lines (approximate for usage in `scan_directory`):** Around line 60 (within the `os.walk` loop, specifically for `dirnames`)
- **Elaboration:**
    - The `scan_directory` method needs to be modified to filter the `dirnames` list provided by `os.walk` *before* `os.walk` descends into them.
    - For each directory name in `dirnames`, construct its full path.
    - Call `self._is_excluded(full_dir_path, root_path_normalized, is_dir=True)` (Note: we might need to adjust `_is_excluded` signature or add a helper to specify we're checking a directory).
    - If `_is_excluded` returns `True` for a directory, it should be removed from the `dirnames` list (e.g., `dirnames[:] = [d for d in dirnames if not should_exclude_dir(d)]`).
    - The `_is_excluded` method, when checking a directory, should compare `os.path.basename(file_path)` against `self.excluded_dirs`. It should also check the full `file_path` (or its relative path from `root_path`) against `self.custom_exclude_patterns` using `fnmatch` for patterns that might represent directories.

### 2. Implement File Exclusion Logic in `_is_excluded` (DONE)
- **File:** `file_scanner.py`
- **Method:** `_is_excluded(self, file_path, root_path)`
- **Lines (approximate for `_is_excluded` definition):** Around line 70
- **Elaboration:**
    - When `_is_excluded` is called for a file path:
        - It should check `os.path.basename(file_path)` against each pattern in `self.excluded_files` using `fnmatch.fnmatch()`.
        - It should also check the full `file_path` (or its relative path from `root_path`) against each pattern in `self.custom_exclude_patterns` using `fnmatch.fnmatch()`.
        - If any pattern matches, the file is excluded. This will be called from `scan_directory` for each enumerated file.

## Meta / Project Management

### 1. Commit `task3_checklist.txt` (DONE)
- **File:** `task3_checklist.txt`
- **Lines:** N/A
- **Elaboration:** The newly created checklist for Task #3 (`task3_checklist.txt`) needs to be added to version control. 