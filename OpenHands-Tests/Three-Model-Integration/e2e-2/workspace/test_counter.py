import threading
from counter import ThreadSafeCounter

def test_concurrent_access():
    c = ThreadSafeCounter()
    threads = []
    for _ in range(10):
        t1 = threading.Thread(target=lambda: [c.increment() for _ in range(500)])
        t2 = threading.Thread(target=lambda: [c.decrement() for _ in range(500)])
        threads.extend([t1, t2])
    for t in threads: t.start()
    for t in threads: t.join()
    assert c.get_value() == 0, f'Race condition detected! Final val={c.get_value()}'
