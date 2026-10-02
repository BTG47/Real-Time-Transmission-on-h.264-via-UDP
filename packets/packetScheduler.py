# Este código se encarga de poner listas de prioridad para cada paquete, con el fin de que se
# envíen dependiendo de que tan relevantes sean. Las colas son acotadas: cuando una cola
# supera su capacidad o un grupo lleva demasiado tiempo en ella, se descarta el grupo de
# NALU más antiguo de esa misma prioridad (eviction FIFO).

from collections import deque
from packets.packetizer import NALUPacket
from config import SCHEDULER_MAX_ENTRIES_PER_QUEUE, SCHEDULER_MAX_AGE_MS
from packets.priority_classifier import Priority
import time

class PacketScheduler():
    def __init__(self, max_entries=None, max_age_ms=None, now_fn=time.monotonic_ns):
        self.criticalQueue : deque[list[NALUPacket]] = deque() 
        self.highQueue : deque[list[NALUPacket]] = deque()
        self.normalQueue : deque[list[NALUPacket]]= deque()
        self.lowQueue : deque[list[NALUPacket]] = deque()

        self.max_entries = (max_entries if max_entries is not None
                            else SCHEDULER_MAX_ENTRIES_PER_QUEUE)
        max_age = max_age_ms if max_age_ms is not None else SCHEDULER_MAX_AGE_MS
        self.max_age_ns = max_age * 1_000_000
        self._now = now_fn

        self.dropped = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 0,
            Priority.NORMAL: 0,
            Priority.LOW: 0,
        }

    def _queue_for(self, priority) -> deque:
        if priority == Priority.CRITICAL:
            return self.criticalQueue
        elif priority == Priority.HIGH:
            return self.highQueue
        elif priority == Priority.NORMAL:
            return self.normalQueue
        elif priority == Priority.LOW:
            return self.lowQueue
        else:
            return self.normalQueue

    def _is_stale(self, entry: list[NALUPacket]) -> bool:
        age_ns = self._now() - entry[0].timestamp_ns
        return age_ns > self.max_age_ns

    def _drop(self, queue: deque, priority: Priority):
        queue.popleft()
        self.dropped[priority] += 1

    def enqueue(self, packets: list[NALUPacket]):
        if not packets:
            return

        priority = packets[0].priority
        queue = self._queue_for(priority)

        if self.max_entries <= 0:
            self.dropped[priority] += 1
            return

        while queue and self._is_stale(queue[0]):
            self._drop(queue, priority)

        while len(queue) >= self.max_entries:
            self._drop(queue, priority)

        queue.append(packets)

    def dequeue(self):
        for queue in (self.criticalQueue, self.highQueue,
                      self.normalQueue, self.lowQueue):
            while queue and self._is_stale(queue[0]):
                self._drop(queue, queue[0][0].priority)
            if queue:
                return queue.popleft()
        return None

    def has_packets(self):
        return (len(self.criticalQueue) > 0 or len(self.highQueue) > 0
                or len(self.normalQueue) > 0 or len(self.lowQueue) > 0)

    def dropped_count(self):
        return sum(self.dropped.values())