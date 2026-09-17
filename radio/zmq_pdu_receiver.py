import subprocess
try:
    import zmq
except ImportError:
    zmq = None
from typing import Callable, Optional
from packets.reassembler import Reassembler
from transport.datagram import parse_datagram
from radio.pmt_codec import decode_pdu_data
from radio.config_radio import ZMQ_RX_ENDPOINT, ZMQ_RX_CONNECT, ZMQ_RCVTIMEO_MS

TIMEOUT_EXCEPTION = getattr(zmq, "Again", TimeoutError)

class ZMQPduReceiver:
    def __init__(self, endpoint=None, context=None, socket=None, connect=None, rcvtimeo_ms=None):
        self._owns_socket = socket is None
        self._owns_context = context is None
        self._context = context if context is not None else zmq.Context()
        self._socket = socket
        self.endpoint = endpoint if endpoint is not None else ZMQ_RX_ENDPOINT
        if self._socket is None:
            self._socket = self._context.socket(zmq.PULL)
            if connect if connect is not None else ZMQ_RX_CONNECT:
                self._socket.connect(self.endpoint)
            else:
                self._socket.bind(self.endpoint)
            self._socket.setsockopt(zmq.RCVTIMEO, rcvtimeo_ms if rcvtimeo_ms is not None else ZMQ_RCVTIMEO_MS)

    def recv_timeout(self) -> Optional[bytes]:
        try:
            frame = self._socket.recv()
        except TIMEOUT_EXCEPTION:
            return None
        return decode_pdu_data(frame)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close(0)
            self._socket = None
        if self._owns_context and self._context is not None:
            self._context.term()
            self._context = None

def run_recv_loop(rx, reassembler, on_nalu: Callable[[bytes], None], on_timeout: Callable[[], bool]) -> None:
    while True:
        datagram = rx.recv_timeout()
        if datagram is None:
            if on_timeout():
                return
            continue
        header, payload = parse_datagram(datagram)
        final_nalu = reassembler.feed(header, payload)
        if final_nalu is not None:
            on_nalu(final_nalu)

def main() -> None:
    cmd = [
        "ffplay", "-fflags", "nobuffer", "-flags", "low_delay",
        "-framedrop", "-f", "h264", "-",
    ]
    video = []
    ffplay_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def on_nalu(nalu_bytes: bytes) -> None:
        video.append(nalu_bytes)
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.write(b"\x00\x00\x00\x01" + nalu_bytes)
            ffplay_process.stdin.flush()

    def on_timeout() -> bool:
        print("Tiempo de espera agotado, fin de recepción")
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.close()
        ffplay_process.terminate()
        with open("reconstructed_rf", "wb") as f:
            for nalu in video:
                f.write(b"\x00\x00\x00\x01" + nalu)
        return True

    rx = ZMQPduReceiver()
    try:
        run_recv_loop(rx, Reassembler(), on_nalu, on_timeout)
    finally:
        rx.close()