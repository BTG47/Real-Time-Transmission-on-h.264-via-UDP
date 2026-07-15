from abc import ABC, abstractmethod
from packetizer import NALUPacket

class Transport(ABC):

    @abstractmethod
    def send_packet(self, packet:NALUPacket) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


