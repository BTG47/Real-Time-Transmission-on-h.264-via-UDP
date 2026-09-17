try:
    import zmq
except ImportError:
    zmq = None
from transport.transport import Transport
from transport.datagram import build_datagram
from radio.pmt_codec import encode_u8vector_pdu
from radio.config_radio import ZMQ_TX_ENDPOINT, ZMQ_TX_BIND
from packets.packetizer import NALUPacket

class ZMQPduTransport(Transport):
    def __init__(self, endpoint=None, context=None, socket=None, bind=None):
        self._owns_socket = socket is None
        self._owns_context = context is None
        self._context = context if context is not None else zmq.Context()
        self._socket = socket
        self.endpoint = endpoint if endpoint is not None else ZMQ_TX_ENDPOINT
        if self._socket is None:
            self._socket = self._context.socket(zmq.PUSH)
            if bind if bind is not None else ZMQ_TX_BIND:
                self._socket.bind(self.endpoint)
            else:
                self._socket.connect(self.endpoint)

    def send_packet(self, packet: NALUPacket) -> int:
        datagram = build_datagram(packet)
        frame = encode_u8vector_pdu(datagram)
        self._socket.send(frame)
        return len(datagram)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close(0)
            self._socket = None
        if self._owns_context and self._context is not None:
            self._context.term()
            self._context = None