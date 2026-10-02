from typing import Optional
from transport.video_header import VideoHeader

class Reassembler:
    def __init__(self):
        self.pending_nalus = {}

    @property
    def pending_count(self) -> int:
        return len(self.pending_nalus)

    def feed(self, header: VideoHeader, payload: bytes) -> Optional[bytes]:
        nalu_id = header.nalu_id
        index = header.fragment_index
        count = header.fragment_count

        if count <= 0:
            return None
        if not 0 <= index < count:
            return None
        if header.payload_size != len(payload):
            return None

        entry = self.pending_nalus.get(nalu_id)
        if entry is None:
            entry = {"fragment_count": count, "fragments": {}}
            self.pending_nalus[nalu_id] = entry
        elif entry["fragment_count"] != count:
            return None

        entry["fragments"][index] = payload

        if len(entry["fragments"]) == entry["fragment_count"]:
            final_nalu = b"".join(entry["fragments"][i] for i in range(entry["fragment_count"]))
            del self.pending_nalus[nalu_id]
            return final_nalu
        return None