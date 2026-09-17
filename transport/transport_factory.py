from transport.udp_transport import UdpTransport

def get_transport():
    from config import TRANSPORT
    if TRANSPORT == "radio":
        try:
            from radio.zmq_pdu_transport import ZMQPduTransport
        except ImportError as exc:
            raise RuntimeError(
                "pyzmq no está instalado: ejecuta 'pip install -r requirements-radio.txt'"
            ) from exc
        return ZMQPduTransport()
    return UdpTransport()