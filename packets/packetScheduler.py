# Este código se encarga de poner listas de prioridad para cada paquete, con el fin de que se
# envíen dependiendo de que tan relevantes sean

from collections import deque
from packets.packetizer import NALUPacket
from config import CRITICAL_VALUES, HIGH_VALUES, NORMAL_VALUES, LOW_VALUES
from packets.priority_classifier import Priority
class PacketScheduler():
    def __init__(self):
        self.criticalQueue : deque[list[NALUPacket]] = deque() 
        self.highQueue : deque[list[NALUPacket]] = deque()
        self.normalQueue : deque[list[NALUPacket]]= deque()
        self.lowQueue : deque[list[NALUPacket]] = deque()

    def enqueue(self, packets: list[NALUPacket]):
        if not packets:
            return
        
        priority = packets[0].priority

        if priority == Priority.CRITICAL:
            self.criticalQueue.append(packets)
        elif priority == Priority.HIGH:
            self.highQueue.append(packets)
        elif priority == Priority.NORMAL:
            self.normalQueue.append(packets)
        elif priority == Priority.LOW:
            self.lowQueue.append(packets)
        else:
            self.normalQueue.append(packets)

    def dequeue(self):
        if self.criticalQueue:
            return self.criticalQueue.popleft()
        elif self.highQueue:
            return self.highQueue.popleft()
        elif self.normalQueue:
            return self.normalQueue.popleft()
        elif self.lowQueue:
            return self.lowQueue.popleft()
        else:
            return None
        
    def has_packets(self):
        if len (self.criticalQueue) > 0:
            return True
        elif len(self.highQueue) > 0:
            return True
        elif len(self.normalQueue)>0:
            return True
        elif len(self.lowQueue) > 0:
            return True
        else:
            return False