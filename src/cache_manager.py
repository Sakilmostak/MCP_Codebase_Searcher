import diskcache
import os
import hashlib
import json
import sys
import logging

DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/mcp_codebase_searcher")
DEFAULT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days
DEFAULT_CACHE_SIZE_LIMIT_MB = 100 # 100 MB

class CacheManager:
    def __init__(self, cache_dir=None, expiry_seconds=None, cache_size_limit_mb=None, size_limit_bytes=None, cull_limit=None):
        self.cache_dir = cache_dir if cache_dir else DEFAULT_CACHE_DIR
        self.expiry_seconds = expiry_seconds if expiry_seconds is not None else DEFAULT_EXPIRY_SECONDS
        
        if size_limit_bytes is not None:
            self.cache_size_limit_bytes = size_limit_bytes
        elif cache_size_limit_mb is not None:
            self.cache_size_limit_bytes = cache_size_limit_mb * 1024 * 1024
        else:
            self.cache_size_limit_bytes = DEFAULT_CACHE_SIZE_LIMIT_MB * 1024 * 1024

        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Prepare arguments for diskcache.Cache
        cache_args = {
            'size_limit': self.cache_size_limit_bytes
        }
        if cull_limit is not None:
            cache_args['cull_limit'] = cull_limit

        self.cache = diskcache.Cache(
            self.cache_dir,
            **cache_args
        )
        # Note: diskcache handles expiry on a per-item basis when set,
        # or globally via its own mechanisms if items are added without explicit expiry.
        # self.expiry_seconds will be used as the default for .set() calls.

    def _generate_key(self, components_tuple):
        # Ensure consistent serialization for hashing
        processed_components = []
        for component in components_tuple:
            if isinstance(component, list) and component: # Check if it's a non-empty list
                # Heuristically check if it looks like a list of (path, timestamp) tuples
                is_file_data_list = True
                for item in component:
                    if not (isinstance(item, tuple) and len(item) == 2):
                        is_file_data_list = False
                        break
                
                if is_file_data_list:
                    # Convert list of (path, timestamp) tuples to a dict for stable serialization
                    # Paths should be unique, so direct dict conversion is fine.
                    try:
                        file_timestamps_dict = {path: ts for path, ts in component}
                        processed_components.append(file_timestamps_dict)
                    except (TypeError, ValueError) as e:
                        # Should not happen if is_file_data_list check is robust
                        print(f"Warning: Error converting file data component to dict: {e}. Using original list.", file=sys.stderr)
                        processed_components.append(component) # Fallback to original component
                else:
                    processed_components.append(component) # Not a file_data_list, keep as is
            else:
                processed_components.append(component) # Not a list, keep as is

        try:
            # Using json.dumps with sort_keys=True for dictionaries within the tuple
            # and handling common types.
            serialized_components = json.dumps(tuple(processed_components), sort_keys=True, default=str)
        except TypeError as e:
            # Fallback for complex/unserializable types, though inputs should be simple.
            # This is a basic fallback; robust serialization might need more handling.
            print(f"Warning: Could not serialize cache key components with JSON: {e}. Using repr().")
            serialized_components = repr(components_tuple)
            
        return hashlib.sha256(serialized_components.encode('utf-8')).hexdigest()

    def get(self, key_components):
        cache_key = self._generate_key(key_components)
        # print(f"DEBUG: Cache GET attempt for key: {cache_key} (from components: {key_components})")
        try:
            value = self.cache.get(cache_key)
            if value is not None:
                if isinstance(key_components, tuple) and key_components:
                    logging.info(f"Cache hit for operation: '{key_components[0]}'. Key digest: {cache_key[:8]}...")
                else:
                    logging.info(f"Cache hit. Key digest: {cache_key[:8]}...")
                # For more detailed debug logging of the key if needed:
                # logging.debug(f"Cache hit for key derived from components: {key_components}")
            else:
                if isinstance(key_components, tuple) and key_components:
                    logging.info(f"Cache miss for operation: '{key_components[0]}'. Key digest: {cache_key[:8]}...")
                else:
                    logging.info(f"Cache miss. Key digest: {cache_key[:8]}...")
                # For more detailed debug logging of the key if needed:
                # logging.debug(f"Cache miss for key derived from components: {key_components}")
            return value
        except Exception as e:
            logging.warning(f"Cache GET operation failed for key digest '{cache_key[:8]}...'. Error: {e}")
            # print(f"Warning: Cache GET operation failed for key '{cache_key}'. Error: {e}", file=sys.stderr) # Original print
            return None

    def set(self, key_components, value, expire=None):
        cache_key = self._generate_key(key_components)
        effective_expire = expire if expire is not None else self.expiry_seconds
        # print(f"DEBUG: Cache SET for key: {cache_key} (from components: {key_components}), expiry: {effective_expire}s")
        try:
            self.cache.set(cache_key, value, expire=effective_expire)
        except Exception as e:
            logging.warning(f"Cache SET operation failed for key digest '{cache_key[:8]}...'. Error: {e}")
            # print(f"Warning: Cache SET operation failed for key '{cache_key}'. Error: {e}", file=sys.stderr) # Original print

    def delete(self, key_components):
        cache_key = self._generate_key(key_components)
        # print(f"DEBUG: Cache DELETE for key: {cache_key} (from components: {key_components})")
        try:
            return self.cache.delete(cache_key) # Returns number of keys deleted (0 or 1)
        except Exception as e:
            logging.warning(f"Cache DELETE operation failed for key digest '{cache_key[:8]}...'. Error: {e}")
            # print(f"Warning: Cache DELETE operation failed for key '{cache_key}'. Error: {e}", file=sys.stderr) # Original print
            return 0 # Indicate no keys were deleted in case of error

    def clear_all(self):
        logging.info(f"Attempting to clear all cache from directory: {self.cache_dir}")
        # print(f"DEBUG: Clearing all cache from {self.cache_dir}")
        try:
            count = self.cache.clear()
            logging.info(f"Successfully cleared {count} items from cache at {self.cache_dir}.")
            # print(f"DEBUG: Cleared {count} items.")
            return count
        except Exception as e:
            logging.warning(f"Cache CLEAR_ALL operation failed for directory '{self.cache_dir}'. Error: {e}")
            # print(f"Warning: Cache CLEAR_ALL operation failed for directory '{self.cache_dir}'. Error: {e}", file=sys.stderr) # Original print
            return 0 # Indicate no items were cleared

    def close(self):
        # print(f"DEBUG: Closing cache at {self.cache_dir}")
        self.cache.close()

if __name__ == '__main__':
    # Example Usage (for testing during development)
    print("CacheManager module direct execution (for testing during dev)")
    
    # Test with default settings
    print("\n--- Test 1: Default Cache ---")
    manager1 = CacheManager()
    print(f"Cache directory: {manager1.cache_dir}")
    print(f"Default expiry: {manager1.expiry_seconds}s")
    print(f"Size limit: {manager1.cache_size_limit_bytes / (1024*1024)} MB")

    key_tuple1 = ("search", "my_query", "/path/to/code", True)
    manager1.set(key_tuple1, {"results": ["result1", "result2"]}, expire=60) # 1 minute
    retrieved1 = manager1.get(key_tuple1)
    print(f"Retrieved for key1: {retrieved1}")
    
    key_tuple2 = ("elaborate", "finding_hash_abc", 15)
    manager1.set(key_tuple2, "This is an elaboration.") # Uses default expiry
    retrieved2 = manager1.get(key_tuple2)
    print(f"Retrieved for key2: {retrieved2}")

    manager1.delete(key_tuple1)
    print(f"Retrieved for key1 after delete: {manager1.get(key_tuple1)}")
    
    # Test with custom settings
    print("\n--- Test 2: Custom Cache ---")
    custom_dir = os.path.expanduser("~/.cache/mcp_codebase_searcher_custom_test")
    manager2 = CacheManager(cache_dir=custom_dir, expiry_seconds=300, cache_size_limit_mb=50)
    print(f"Custom cache directory: {manager2.cache_dir}")
    print(f"Custom expiry: {manager2.expiry_seconds}s")
    print(f"Custom size limit: {manager2.cache_size_limit_bytes / (1024*1024)} MB")
    
    manager2.set(("test_key", 123), "custom_value")
    print(f"Retrieved from custom cache: {manager2.get(('test_key', 123))}")
    
    print(f"\nClearing all items from manager1 ({manager1.cache_dir})...")
    cleared_count1 = manager1.clear_all()
    print(f"Cleared {cleared_count1} items from default cache.")
    print(f"Retrieved for key2 after clear: {manager1.get(key_tuple2)}")

    print(f"\nClearing all items from manager2 ({manager2.cache_dir})...")
    cleared_count2 = manager2.clear_all()
    print(f"Cleared {cleared_count2} items from custom cache.")

    manager1.close()
    manager2.close()
    
    # Clean up custom test directory
    import shutil
    if os.path.exists(custom_dir):
        try:
            shutil.rmtree(custom_dir)
            print(f"Cleaned up custom test directory: {custom_dir}")
        except Exception as e:
            print(f"Error cleaning up custom test directory {custom_dir}: {e}")
            
    print("\nCacheManager test complete.") 