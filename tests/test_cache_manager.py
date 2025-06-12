import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import shutil
import io
import time

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Attempt to import the module and class to be tested
try:
    from src.cache_manager import CacheManager, DEFAULT_CACHE_DIR, DEFAULT_EXPIRY_SECONDS, DEFAULT_CACHE_SIZE_LIMIT_MB
    import diskcache # To check instance type
    CACHE_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"Test Setup Error: Failed to import CacheManager or diskcache: {e}", file=sys.stderr)
    CacheManager = None 
    diskcache = None
    CACHE_MANAGER_AVAILABLE = False

@unittest.skipIf(not CACHE_MANAGER_AVAILABLE, "CacheManager module not available for testing.")
class TestCacheManagerStructure(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for cache testing if needed by some tests,
        # though these structural tests might not write to disk.
        self.test_cache_dir_base = "temp_test_cache_manager_struct"
        os.makedirs(self.test_cache_dir_base, exist_ok=True)
        self.custom_cache_dir = os.path.join(self.test_cache_dir_base, "custom_cache")

        # Suppress "Warning: Could not serialize cache key components with JSON..." from _generate_key
        # if any test inadvertently calls it with complex types, though these tests shouldn't.
        self.patcher_print = patch('builtins.print')
        self.mock_print = self.patcher_print.start()
        self.addCleanup(self.patcher_print.stop)


    def tearDown(self):
        # Clean up the base temporary directory
        if os.path.exists(self.test_cache_dir_base):
            # Close any open cache instances before attempting to remove the directory
            # This is a precaution; specific tests creating CacheManager instances should close them.
            # Forcing a close here might be risky if tests are not isolated.
            # It's better if tests manage their own CacheManager.close() calls.
            shutil.rmtree(self.test_cache_dir_base, ignore_errors=True) # ignore_errors for robustness in cleanup

    def test_cache_manager_instantiation_defaults(self):
        """Test CacheManager can be instantiated with default parameters."""
        try:
            manager = CacheManager()
            self.assertIsNotNone(manager, "CacheManager instance should not be None.")
            self.assertIsInstance(manager.cache, diskcache.Cache, "manager.cache should be a diskcache.Cache instance.")
            self.assertEqual(manager.cache_dir, DEFAULT_CACHE_DIR)
            self.assertEqual(manager.expiry_seconds, DEFAULT_EXPIRY_SECONDS)
            self.assertEqual(manager.cache_size_limit_bytes, DEFAULT_CACHE_SIZE_LIMIT_MB * 1024 * 1024)
            manager.close() # Important to close the cache
        except Exception as e:
            self.fail(f"CacheManager instantiation with defaults failed: {e}")

    def test_cache_manager_instantiation_custom_params(self):
        """Test CacheManager can be instantiated with custom parameters."""
        custom_expiry = 3600  # 1 hour
        custom_limit_mb = 50
        try:
            manager = CacheManager(
                cache_dir=self.custom_cache_dir,
                expiry_seconds=custom_expiry,
                cache_size_limit_mb=custom_limit_mb
            )
            self.assertIsNotNone(manager)
            self.assertIsInstance(manager.cache, diskcache.Cache)
            self.assertEqual(manager.cache_dir, self.custom_cache_dir)
            self.assertEqual(manager.expiry_seconds, custom_expiry)
            self.assertEqual(manager.cache_size_limit_bytes, custom_limit_mb * 1024 * 1024)
            manager.close()
        except Exception as e:
            self.fail(f"CacheManager instantiation with custom params failed: {e}")

    def test_cache_manager_has_required_methods(self):
        """Test CacheManager instance has all the required methods."""
        manager = CacheManager(cache_dir=os.path.join(self.custom_cache_dir, "methods_test"))
        methods = [
            '_generate_key',
            'get',
            'set',
            'delete',
            'clear_all',
            'close'
        ]
        for method_name in methods:
            self.assertTrue(hasattr(manager, method_name), f"CacheManager should have method '{method_name}'.")
            self.assertTrue(callable(getattr(manager, method_name)), f"'{method_name}' should be callable.")
        manager.close()

@unittest.skipIf(not CACHE_MANAGER_AVAILABLE, "CacheManager module not available for testing.")
class TestCacheManagerFunctionality(unittest.TestCase):
    def setUp(self):
        self.test_cache_dir_base = "temp_test_cache_manager_func"
        os.makedirs(self.test_cache_dir_base, exist_ok=True)
        self.cache_dir = os.path.join(self.test_cache_dir_base, "functional_cache")
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
        os.makedirs(self.cache_dir)

        self.manager = CacheManager(cache_dir=self.cache_dir, expiry_seconds=2)

        # Patch 'print' in the cache_manager module to check calls to it for warnings
        self.patcher_cache_manager_print = patch('src.cache_manager.print')
        self.mock_cache_manager_print = self.patcher_cache_manager_print.start()
        self.addCleanup(self.patcher_cache_manager_print.stop)
        
        # Keep patching builtins.print as well to suppress other potential prints if necessary,
        # or if some prints in cache_manager are not going to sys.stderr explicitly.
        self.patcher_builtins_print = patch('builtins.print')
        self.mock_builtins_print = self.patcher_builtins_print.start()
        self.addCleanup(self.patcher_builtins_print.stop)

    def tearDown(self):
        if hasattr(self, 'manager') and self.manager:
            self.manager.close()
        if os.path.exists(self.test_cache_dir_base):
            shutil.rmtree(self.test_cache_dir_base, ignore_errors=True)

    def test_set_and_get(self):
        key_components = ("test_item", 1)
        value = {"data": "my_value"}
        self.manager.set(key_components, value)
        retrieved_value = self.manager.get(key_components)
        self.assertEqual(retrieved_value, value)

    def test_get_non_existent_key(self):
        key_components = ("non_existent", "key")
        retrieved_value = self.manager.get(key_components)
        self.assertIsNone(retrieved_value)

    def test_set_with_explicit_expiry_and_item_expires(self):
        key_components = ("expiring_item", "data")
        value = "this will expire"
        # Set with very short expiry (e.g., 1 second for diskcache, though diskcache's precision might vary)
        # self.manager.expiry_seconds is 2 by default in setUp
        self.manager.set(key_components, value, expire=1) 
        
        retrieved_value_immediately = self.manager.get(key_components)
        self.assertEqual(retrieved_value_immediately, value, "Item should be retrievable immediately after set.")

        # Wait for longer than the expiry time
        # Note: diskcache expiry is checked on get, not actively purged in background by default.
        # We need to ensure enough time passes. Diskcache checks on access.
        time.sleep(1.5) # Wait for 1.5 seconds, expiry was 1s

        retrieved_value_after_expiry = self.manager.get(key_components)
        self.assertIsNone(retrieved_value_after_expiry, "Item should be None after expiry time.")

    def test_delete_item(self):
        key_components = ("to_delete", "item")
        value = "delete_me"
        self.manager.set(key_components, value)
        self.assertIsNotNone(self.manager.get(key_components), "Item should exist before delete.")
        
        delete_result = self.manager.delete(key_components)
        self.assertEqual(delete_result, 1, "Delete should return 1 for a successful deletion.")
        self.assertIsNone(self.manager.get(key_components), "Item should not exist after delete.")
        
        delete_non_existent = self.manager.delete(("non_existent_for_delete",))
        self.assertEqual(delete_non_existent, 0, "Delete should return 0 if key does not exist.")


    def test_clear_all_items(self):
        self.manager.set(("item1",), "value1")
        self.manager.set(("item2",), "value2")
        self.assertIsNotNone(self.manager.get(("item1",)), "Item1 should exist before clear.")
        self.assertIsNotNone(self.manager.get(("item2",)), "Item2 should exist before clear.")
        
        cleared_count = self.manager.clear_all()
        # The number of items cleared can be tricky to assert precisely if other tests ran
        # in parallel and wrote to the same default cache, but here we control the cache_dir.
        # However, diskcache.clear() returns the number of items *removed*.
        self.assertGreaterEqual(cleared_count, 2, "Should clear at least the two items set.")
        
        self.assertIsNone(self.manager.get(("item1",)), "Item1 should not exist after clear_all.")
        self.assertIsNone(self.manager.get(("item2",)), "Item2 should not exist after clear_all.")

    def test_get_error_handling(self):
        with patch.object(self.manager.cache, 'get', side_effect=Exception("Disk Read Error")):
            result = self.manager.get(("error_key",))
            self.assertIsNone(result)
            # Check if print was called with the warning and file=sys.stderr
            found_call = False
            for call_args in self.mock_cache_manager_print.call_args_list:
                args, kwargs = call_args
                if args and "Warning: Cache GET operation failed" in args[0] and kwargs.get('file') == sys.stderr:
                    found_call = True
                    break
            self.assertTrue(found_call, "Warning for GET error not printed to sys.stderr via src.cache_manager.print")
        self.mock_cache_manager_print.reset_mock() # Reset for other tests

    def test_set_error_handling(self):
        with patch.object(self.manager.cache, 'set', side_effect=Exception("Disk Write Error")):
            self.manager.set(("error_key",), "value")
            found_call = False
            for call_args in self.mock_cache_manager_print.call_args_list:
                args, kwargs = call_args
                if args and "Warning: Cache SET operation failed" in args[0] and kwargs.get('file') == sys.stderr:
                    found_call = True
                    break
            self.assertTrue(found_call, "Warning for SET error not printed to sys.stderr via src.cache_manager.print")
        self.mock_cache_manager_print.reset_mock()

    def test_delete_error_handling(self):
        with patch.object(self.manager.cache, 'delete', side_effect=Exception("Disk Delete Error")):
            result = self.manager.delete(("error_key",))
            self.assertEqual(result, 0)
            found_call = False
            for call_args in self.mock_cache_manager_print.call_args_list:
                args, kwargs = call_args
                if args and "Warning: Cache DELETE operation failed" in args[0] and kwargs.get('file') == sys.stderr:
                    found_call = True
                    break
            self.assertTrue(found_call, "Warning for DELETE error not printed to sys.stderr via src.cache_manager.print")
        self.mock_cache_manager_print.reset_mock()
            
    def test_clear_all_error_handling(self):
        with patch.object(self.manager.cache, 'clear', side_effect=Exception("Disk Clear Error")):
            result = self.manager.clear_all()
            self.assertEqual(result, 0)
            found_call = False
            for call_args in self.mock_cache_manager_print.call_args_list:
                args, kwargs = call_args
                if args and "Warning: Cache CLEAR_ALL operation failed" in args[0] and kwargs.get('file') == sys.stderr:
                    found_call = True
                    break
            self.assertTrue(found_call, "Warning for CLEAR_ALL error not printed to sys.stderr via src.cache_manager.print")
        self.mock_cache_manager_print.reset_mock()

    def test_generate_key_functionality(self):
        """Comprehensive tests for _generate_key method."""
        manager = self.manager

        # Basic consistent hashing
        key_components1 = ("search", "query1", ["/path/a"], False)
        key_components2 = ("search", "query1", ["/path/a"], False)
        self.assertEqual(manager._generate_key(key_components1), manager._generate_key(key_components2))

        # Different components, different keys
        key_components3 = ("search", "query2", ["/path/a"], False)
        self.assertNotEqual(manager._generate_key(key_components1), manager._generate_key(key_components3))

        # Various data types
        key_data_types1 = ("string", 123, 3.14, True, None, [1, 2], (3, 4), {"a": 1, "b": 2})
        key_data_types2 = ("string", 123, 3.14, True, None, [1, 2], (3, 4), {"b": 2, "a": 1})
        self.assertEqual(manager._generate_key(key_data_types1), manager._generate_key(key_data_types2),
                         "Keys with differently ordered but equivalent dicts should match due to sort_keys=True.")

        key_list_order_diff1 = ([1,2,3],)
        key_list_order_diff2 = ([3,2,1],)
        self.assertNotEqual(manager._generate_key(key_list_order_diff1), manager._generate_key(key_list_order_diff2),
                            "Keys with lists of different order should NOT match.")
        
        nested_key1 = ({"outer_key": ["val1", {"inner_key": (1, True)}]},)
        nested_key2 = ({"outer_key": ["val1", {"inner_key": (1, True)}]},)
        nested_key3 = ({"outer_key": ["val1", {"inner_key": (1, False)}]},)
        self.assertEqual(manager._generate_key(nested_key1), manager._generate_key(nested_key2))
        self.assertNotEqual(manager._generate_key(nested_key1), manager._generate_key(nested_key3))

        # Test with non-JSON serializable objects (hypothetical, as default=str handles them via repr)
        class NonSerializable:
            def __init__(self, x):
                self.x = x
            def __repr__(self):
                return f"NonSerializable(x={self.x})"

        obj1 = NonSerializable(10)
        obj2 = NonSerializable(10) # Another instance with same repr
        obj3 = NonSerializable(20)
        
        key_non_serializable1 = (obj1,)
        key_non_serializable2 = (obj2,)
        key_non_serializable3 = (obj3,)

        hash_ns1 = manager._generate_key(key_non_serializable1)
        hash_ns2 = manager._generate_key(key_non_serializable2)
        hash_ns3 = manager._generate_key(key_non_serializable3)

        # The warning print check is removed as json.dumps(default=str) will use repr() without TypeError.
        # self.mock_cache_manager_print.reset_mock() # No longer needed here if not checking print

        # If NonSerializable has __eq__ and was hashable, JSON might use it if default=str didn't catch it first.
        # Here, default=str will try to convert via NonSerializable.__str__ (if exists) or repr. JSON can't serialize it directly.
        # The fallback `repr()` will be `NonSerializable(x=10)` for both obj1 and obj2 IF the class definition is simple.
        # For the one above, it should be.
        self.assertEqual(hash_ns1, hash_ns2, "Keys with identical non-JSON-serializable (via repr) objects should match if repr is identical.")
        self.assertNotEqual(hash_ns1, hash_ns3, "Keys with different non-JSON-serializable (via repr) objects should differ.")

if __name__ == '__main__':
    unittest.main() 