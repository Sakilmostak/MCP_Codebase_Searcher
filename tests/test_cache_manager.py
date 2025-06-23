import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import shutil
import io
import time
import tempfile

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

        # Patch 'logging.warning' in the cache_manager module for error handling tests
        # This will be done per-test method where needed, e.g.:
        # @patch('src.cache_manager.logging.warning')
        # def test_get_error_handling(self, mock_logging_warning):

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

    @patch('src.cache_manager.logging.warning')
    def test_get_error_handling(self, mock_logging_warning):
        with patch.object(self.manager.cache, 'get', side_effect=Exception("Disk Read Error")):
            key_components = ("error_key_get",)
            key_digest_short = self.manager._generate_key(key_components)[:8]
            result = self.manager.get(key_components)
            self.assertIsNone(result)
            
            expected_log = f"Cache GET operation failed for key digest '{key_digest_short}...'. Error: Disk Read Error"
            found_call = any(expected_log in call_args[0][0] for call_args in mock_logging_warning.call_args_list)
            self.assertTrue(found_call, f"Expected log for GET error not found. Logs: {mock_logging_warning.call_args_list}")

    @patch('src.cache_manager.logging.warning')
    def test_set_error_handling(self, mock_logging_warning):
        with patch.object(self.manager.cache, 'set', side_effect=Exception("Disk Write Error")):
            key_components = ("error_key_set",)
            key_digest_short = self.manager._generate_key(key_components)[:8]
            self.manager.set(key_components, "value")
            
            expected_log = f"Cache SET operation failed for key digest '{key_digest_short}...'. Error: Disk Write Error"
            found_call = any(expected_log in call_args[0][0] for call_args in mock_logging_warning.call_args_list)
            self.assertTrue(found_call, f"Expected log for SET error not found. Logs: {mock_logging_warning.call_args_list}")

    @patch('src.cache_manager.logging.warning')
    def test_delete_error_handling(self, mock_logging_warning):
        with patch.object(self.manager.cache, 'delete', side_effect=Exception("Disk Delete Error")):
            key_components = ("error_key_delete",)
            key_digest_short = self.manager._generate_key(key_components)[:8]
            result = self.manager.delete(key_components)
            self.assertEqual(result, 0)
            
            expected_log = f"Cache DELETE operation failed for key digest '{key_digest_short}...'. Error: Disk Delete Error"
            found_call = any(expected_log in call_args[0][0] for call_args in mock_logging_warning.call_args_list)
            self.assertTrue(found_call, f"Expected log for DELETE error not found. Logs: {mock_logging_warning.call_args_list}")
            
    @patch('src.cache_manager.logging.warning')
    def test_clear_all_error_handling(self, mock_logging_warning):
        with patch.object(self.manager.cache, 'clear', side_effect=Exception("Disk Clear Error")):
            result = self.manager.clear_all()
            self.assertEqual(result, 0)
            
            expected_log = f"Cache CLEAR_ALL operation failed for directory '{self.manager.cache_dir}'. Error: Disk Clear Error"
            found_call = any(expected_log in call_args[0][0] for call_args in mock_logging_warning.call_args_list)
            self.assertTrue(found_call, f"Expected log for CLEAR_ALL error not found. Logs: {mock_logging_warning.call_args_list}")

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

class TestCacheEviction(unittest.TestCase):
    def setUp(self):
        # Create a unique temporary directory for each test method to ensure isolation
        self.test_cache_dir = tempfile.mkdtemp(prefix="eviction_test_cache_")
        # Intentionally small size_limit for testing eviction
        # size_limit should be greater than disk_min_file_size (default 32KB if not overridden)
        # For this test, we'll add many small items, so the SQLite DB size will be the main factor initially.
        # Let's set a size_limit that is reasonably small, e.g., 64KB (64 * 1024 bytes)
        self.size_limit_bytes = 64 * 1024 
        self.cache_manager = CacheManager(cache_dir=self.test_cache_dir, size_limit_bytes=self.size_limit_bytes, cull_limit=1) # cull_limit=1 for more aggressive culling

    def tearDown(self):
        if self.cache_manager:
            self.cache_manager.close()
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir, ignore_errors=True)

    def test_automatic_eviction_on_size_limit(self):
        # Add items to exceed the cache size limit and trigger automatic culling.
        # Each item is small, but adding many should eventually hit the size_limit.
        # The exact number of items depends on internal SQLite overhead and item storage.
        num_items_to_add = 5000 # A sufficiently large number of small items
        item_size_approx = 100  # Approx bytes per item (key + value + overhead)

        for i in range(num_items_to_add):
            key = f"key_{i}"
            value = os.urandom(item_size_approx // 2) # small random value
            self.cache_manager.set(key, value, expire=3600)
            # It's hard to predict the exact volume due to SQLite behavior and file system block sizes.
            # We are primarily testing that the cache *does not* grow indefinitely far beyond the limit.

        final_volume = self.cache_manager.cache.volume()
        # Check that the final volume is not excessively larger than the size_limit.
        # Allow some leeway for SQLite overhead and the fact that culling might not bring it *exactly* to the limit.
        # A common observation is that it might slightly exceed the limit before culling brings it down.
        # And culling might not remove enough to go *below* the limit if remaining items are large or cull_limit is small.
        # With cull_limit=1, it should try to remove one item at a time once the limit is hit.
        # We expect the final volume to be *around* size_limit, not drastically larger.
        # Let's assert it's not more than, say, 2 * size_limit as a loose check that culling is active.
        # A tighter bound might be possible but depends heavily on diskcache internals.
        self.assertLessEqual(final_volume, self.size_limit_bytes * 2, 
                             f"Cache volume {final_volume} greatly exceeded size_limit {self.size_limit_bytes} despite culling.")

        # A more robust check might involve seeing if *some* items were indeed evicted.
        # This requires knowing which items *should* be there if no eviction happened.
        # For now, the volume check is a good first step.
        # To verify eviction happened, we can count the items. It should be less than num_items_to_add if eviction occurred.
        # However, len(self.cache_manager.cache) includes expired items until .expire() or .cull() is called.
        # .cull() is called internally by .set() if cull_limit > 0 and size_limit is reached.
        # So, the number of items should be less than num_items_to_add *if* eviction happened.
        
        # Call expire() to remove any expired items to get a cleaner count for non-expired items.
        # This is not strictly necessary for testing size-based eviction, but good practice.
        self.cache_manager.cache.expire() 
        final_item_count = len(self.cache_manager.cache)
        
        # If the total size of all items (num_items_to_add * item_size_approx) is much larger than size_limit,
        # then final_item_count should be significantly less than num_items_to_add.
        estimated_total_data_size = num_items_to_add * item_size_approx
        if estimated_total_data_size > self.size_limit_bytes * 1.5: # If we expect significant eviction
            self.assertLess(final_item_count, num_items_to_add, 
                              f"Expected item count ({final_item_count}) to be less than added items ({num_items_to_add}) if eviction occurred.")
        
        # print(f"TestCacheEviction: Initial size_limit: {self.size_limit_bytes}, Final volume: {final_volume}, Final item count: {final_item_count}")


if __name__ == '__main__':
    unittest.main() 