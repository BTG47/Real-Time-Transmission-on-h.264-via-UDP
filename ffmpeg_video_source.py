# EL objetivo de este código es obtener el flujo de bytes
# Y con este flujo pasarlo a chunks comprobados
import subprocess
from config import LECTURE_SIZE
from nalu_parser import extract_nalus_chunk

cmd = [
    'ffmpeg', '-hide_banner',
    '-f', 'v4l2',
    '-i', '/dev/video0',
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-f', 'h264',
    'pipe:1'
]

class FfmpegVideoSource():
    def __init__(self):
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.stream_buffer = bytearray()
        self.remain_buffer = 0
        self.stdout = None

    # Nota, esta función se va a estar ejecutando dentro de un while en el código capture
    def read_chunk(self):
        if self.stdout is None:
            self.stdout = self.process.stdout
            if self.stdout is None:
                raise RuntimeError("Failed to open process stdout")

        chunk = self.stdout.read(LECTURE_SIZE)
        if not chunk:
            print("No hay chunk")
            return None
        
        return chunk
    
    def obtain_nalus_from_chunk(self, chunk):
        if chunk is None:
            return None
        # process chunk (append to buffer)
        self.stream_buffer.extend(chunk)
        nalus, remain_buffer = extract_nalus_chunk(self.stream_buffer)
        # Obtener el resto del buffer cortando la lista hasta la última posible nalu
        self.stream_buffer = self.stream_buffer[-remain_buffer:]
        
        return nalus
    
    def close(self):
        self.process.terminate