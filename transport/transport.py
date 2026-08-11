from abc import ABC, abstractmethod
from packets.packetizer import NALUPacket

class Transport(ABC):

    @abstractmethod
    def send_packet(self, packet:NALUPacket) -> int:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


