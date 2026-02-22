import logging
import queue
import threading
from typing import Type

try:
    from http_parser.parser import HttpParser
except ImportError:
    from http_parser.pyparser import HttpParser

from gateway import WSGI

logger = logging.getLogger(__name__)

class Worker:
    is_stopped = False

    def __init__(self):
        self.config = None
        self.queue = None
        self.gateway = None
        self.kill_pill = None

    def setup(self, config):
        self.config = config
        self.queue = queue.Queue(maxsize=config.get('concurrency', 10))
        self.gateway = WSGI(config)
        self.kill_pill = threading.Event()

        threads = [RequestProcessorThread(name=f'RequestProcessor {i}', queue=self.queue, kill_pill=self.kill_pill, gateway=self.gateway) for i in range(config.get('concurrency', 10))] 
        for t in threads:
            t.start()
    
    def run(self, listener):
        logger.info("Accepting connections now")
        while not self.is_stopped:
            sock, _= listener.accept()
            self.submit(sock)

    def submit(self, sock):
        try:
            self.queue.put(sock, timeout=self.config.get('timeout', 5))
        except queue.Full:
            pass
    
    def shutdown(self):
        self.is_stopped = True
        self.kill_pill.set()

class RequestProcessorThread(threading.Thread):

    def __init__(self, group=None, target=None, name=None, queue:queue.Queue=None, kill_pill=None, gateway=None,args=(), kwargs=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs)
        self.queue: Type[queue.Queue] = queue
        self.kill_pill = kill_pill
        self.gateway = gateway
    
    def run(self) -> None:
        logger.info(f"Running thread {self.name}")
        while not self.kill_pill.is_set():
            try:
                socket = self.queue.get(block=True, timeout=1)
                self.process(socket)
            except queue.Empty:
                continue
    
    def process(self, sock):
        p = HttpParser()
        body = []
        raw_chunks = []
        while True:
            data = sock.recv(1024)
            if not data:
                return

            raw_chunks.append(data)
            p.execute(data, len(data))

            if p.is_partial_body():
                body.append(p.recv_body())

            if p.is_message_complete():
                break
        
        def write(data):
            sock.send(data)

        self.gateway.process(p, write)
        sock.close()
