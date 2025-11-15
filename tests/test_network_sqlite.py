# -*- coding: utf-8 -*-
"""
Network SQLite Stress Test
Tests concurrent database access from multiple processes
Python 2.7/3+ compatible
"""

import os
import sys
import time
import multiprocessing
from multiprocessing import Process, Queue

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from db_manager import DatabaseManager


def worker_read(db_path, worker_id, result_queue, num_operations=50):
    """Worker process that performs read operations."""
    db = DatabaseManager(db_path)
    success_count = 0
    error_count = 0
    
    for i in range(num_operations):
        try:
            stacks = db.get_all_stacks()
            success_count += 1
            time.sleep(0.01)  # Simulate work
        except Exception as e:
            error_count += 1
            print("[Worker {}] Read error: {}".format(worker_id, str(e)))
    
    result_queue.put({
        'worker_id': worker_id,
        'type': 'read',
        'success': success_count,
        'errors': error_count
    })


def worker_write(db_path, worker_id, result_queue, num_operations=20):
    """Worker process that performs write operations."""
    db = DatabaseManager(db_path)
    success_count = 0
    error_count = 0
    
    for i in range(num_operations):
        try:
            # Create a stack
            stack_name = "TestStack_W{}_{}".format(worker_id, i)
            stack_path = "/test/stack_w{}_{}".format(worker_id, i)
            db.create_stack(stack_name, stack_path)
            success_count += 1
            time.sleep(0.02)  # Simulate work
        except Exception as e:
            error_count += 1
            print("[Worker {}] Write error: {}".format(worker_id, str(e)))
    
    result_queue.put({
        'worker_id': worker_id,
        'type': 'write',
        'success': success_count,
        'errors': error_count
    })


def worker_mixed(db_path, worker_id, result_queue, num_operations=30):
    """Worker process that performs mixed read/write operations."""
    db = DatabaseManager(db_path)
    success_count = 0
    error_count = 0
    
    for i in range(num_operations):
        try:
            # Alternate between read and write
            if i % 2 == 0:
                # Read operation
                stacks = db.get_all_stacks()
            else:
                # Write operation
                stack_name = "MixedStack_W{}_{}".format(worker_id, i)
                stack_path = "/test/mixed_w{}_{}".format(worker_id, i)
                try:
                    db.create_stack(stack_name, stack_path)
                except:
                    # Stack may already exist, ignore
                    pass
            
            success_count += 1
            time.sleep(0.015)  # Simulate work
        except Exception as e:
            error_count += 1
            print("[Worker {}] Mixed error: {}".format(worker_id, str(e)))
    
    result_queue.put({
        'worker_id': worker_id,
        'type': 'mixed',
        'success': success_count,
        'errors': error_count
    })


def run_stress_test(db_path, num_readers=5, num_writers=3, num_mixed=4):
    """
    Run concurrent stress test on database.
    
    Args:
        db_path (str): Path to test database
        num_readers (int): Number of reader processes
        num_writers (int): Number of writer processes
        num_mixed (int): Number of mixed processes
    """
    print("="*60)
    print("Network SQLite Stress Test")
    print("="*60)
    print("Database: {}".format(db_path))
    print("Readers: {} | Writers: {} | Mixed: {}".format(num_readers, num_writers, num_mixed))
    print("="*60)
    
    # Create test database
    db = DatabaseManager(db_path)
    
    # Pre-populate with some data
    print("Pre-populating database...")
    for i in range(10):
        try:
            db.create_stack("InitStack_{}".format(i), "/init/stack_{}".format(i))
        except:
            pass  # May already exist
    
    # Result queue
    result_queue = Queue()
    
    # Create worker processes
    processes = []
    
    print("\nStarting {} reader processes...".format(num_readers))
    for i in range(num_readers):
        p = Process(target=worker_read, args=(db_path, i, result_queue))
        processes.append(p)
    
    print("Starting {} writer processes...".format(num_writers))
    for i in range(num_writers):
        p = Process(target=worker_write, args=(db_path, num_readers + i, result_queue))
        processes.append(p)
    
    print("Starting {} mixed processes...".format(num_mixed))
    for i in range(num_mixed):
        p = Process(target=worker_mixed, args=(db_path, num_readers + num_writers + i, result_queue))
        processes.append(p)
    
    # Start all processes
    start_time = time.time()
    for p in processes:
        p.start()
    
    # Wait for all processes to complete
    for p in processes:
        p.join()
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Collect results
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())
    
    # Print results
    print("\n" + "="*60)
    print("Test Results")
    print("="*60)
    print("Duration: {:.2f} seconds".format(duration))
    print("\nPer-Worker Results:")
    print("-"*60)
    
    total_success = 0
    total_errors = 0
    
    for result in sorted(results, key=lambda x: x['worker_id']):
        print("Worker {worker_id} ({type}): {success} success, {errors} errors".format(**result))
        total_success += result['success']
        total_errors += result['errors']
    
    print("-"*60)
    print("Total Operations: {}".format(total_success + total_errors))
    print("Total Success: {}".format(total_success))
    print("Total Errors: {}".format(total_errors))
    print("Success Rate: {:.2f}%".format((total_success / float(total_success + total_errors)) * 100 if (total_success + total_errors) > 0 else 0))
    print("Operations/Second: {:.2f}".format((total_success + total_errors) / duration))
    print("="*60)
    
    # Cleanup
    print("\nCleaning up test database...")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        print("Test database removed.")
    except Exception as e:
        print("Failed to remove test database: {}".format(str(e)))


if __name__ == '__main__':
    import tempfile
    
    # Create temporary database for testing
    test_db = os.path.join(tempfile.gettempdir(), 'vah_stress_test.db')
    
    # Remove if exists
    if os.path.exists(test_db):
        os.remove(test_db)
    
    # Run stress test
    try:
        run_stress_test(
            db_path=test_db,
            num_readers=8,
            num_writers=4,
            num_mixed=6
        )
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print("\n\nTest failed with error: {}".format(str(e)))
        import traceback
        traceback.print_exc()
