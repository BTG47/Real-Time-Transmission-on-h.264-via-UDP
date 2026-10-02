import unittest
from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from packets.packetScheduler import PacketScheduler

NS_PER_MS = 1_000_000


def make_packet(ts_ns, priority=Priority.NORMAL, nalu_id=1, fragment_index=0, fragment_count=1):
    return NALUPacket(packet_sequence=nalu_id, nalu_id=nalu_id,
                      fragment_index=fragment_index, fragment_count=fragment_count,
                      nal_type=1, priority=priority, timestamp_ns=ts_ns, payload=b"X")


def make_group(ts_ns, priority=Priority.NORMAL, nalu_id=1, n_fragments=1):
    return [make_packet(ts_ns, priority, nalu_id, i, n_fragments)
            for i in range(n_fragments)]


class FakeClock:
    def __init__(self, now=None):
        self.now = now if now is not None else 0

    def set(self, now):
        self.now = now

    def __call__(self):
        return self.now


class TestPacketSchedulerEviction(unittest.TestCase):
    def test_al_superar_capacidad_evicta_el_mas_antiguo_de_esa_prioridad(self):
        clock = FakeClock(now=10 * NS_PER_MS)
        sched = PacketScheduler(max_entries=3, max_age_ms=10_000, now_fn=clock)

        for i, ts in enumerate([2000, 3000, 4000]):
            sched.enqueue(make_group(ts * NS_PER_MS, Priority.NORMAL, nalu_id=i))
        sched.enqueue(make_group(5000 * NS_PER_MS, Priority.NORMAL, nalu_id=99))

        self.assertEqual(sched.dropped[Priority.NORMAL], 1)
        self.assertEqual(sched.dropped_count(), 1)
        first = sched.dequeue()
        self.assertEqual(first[0].nalu_id, 1)   # nalu_id 0 fue el más antiguo y se descartó

    def test_dequeue_descarta_paquetes_obsoletos(self):
        clock = FakeClock(now=0)
        sched = PacketScheduler(max_entries=16, max_age_ms=1000, now_fn=clock)

        sched.enqueue(make_group(100 * NS_PER_MS, Priority.NORMAL, nalu_id=1))
        sched.enqueue(make_group(950 * NS_PER_MS, Priority.NORMAL, nalu_id=2))

        clock.set(1100 * NS_PER_MS)   # nalu_id=1 tiene 1000ms exactos de vejez -> no vence
        out = sched.dequeue()
        self.assertEqual(out[0].nalu_id, 1)
        self.assertEqual(sched.dropped_count(), 0)

        clock.set(2000 * NS_PER_MS)   # nalu_id=1 queda con 1900ms -> obsoleto
        sched.enqueue(make_group(1900 * NS_PER_MS, Priority.NORMAL, nalu_id=3))
        sched.enqueue(make_group(1500 * NS_PER_MS, Priority.NORMAL, nalu_id=4))
        stale_ids = []
        while sched.has_packets():
            g = sched.dequeue()
            if g is not None:
                stale_ids.append(g[0].nalu_id)
        self.assertEqual(stale_ids, [3, 4])
        self.assertGreaterEqual(sched.dropped[Priority.NORMAL], 1)

    def test_eviction_respeta_la_prioridad(self):
        clock = FakeClock(now=10 * NS_PER_MS)
        sched = PacketScheduler(max_entries=2, max_age_ms=10_000, now_fn=clock)

        sched.enqueue(make_group(2000 * NS_PER_MS, Priority.CRITICAL, nalu_id=10))
        sched.enqueue(make_group(2000 * NS_PER_MS, Priority.CRITICAL, nalu_id=11))
        sched.enqueue(make_group(2000 * NS_PER_MS, Priority.CRITICAL, nalu_id=12))

        sched.enqueue(make_group(3000 * NS_PER_MS, Priority.NORMAL, nalu_id=20))
        sched.enqueue(make_group(3000 * NS_PER_MS, Priority.NORMAL, nalu_id=21))
        sched.enqueue(make_group(3000 * NS_PER_MS, Priority.NORMAL, nalu_id=22))
        sched.enqueue(make_group(3000 * NS_PER_MS, Priority.NORMAL, nalu_id=23))

        self.assertEqual(sched.dropped[Priority.CRITICAL], 1)   # se descartó nalu_id=10
        self.assertEqual(sched.dropped[Priority.NORMAL], 2)     # nalu_id=20 y 21

        out = sched.dequeue()
        self.assertEqual(out[0].priority, Priority.CRITICAL)    # prioridades intactas
        self.assertEqual(out[0].nalu_id, 11)

    def test_descarte_atomico_del_grupo(self):
        clock = FakeClock(now=10 * NS_PER_MS)
        sched = PacketScheduler(max_entries=2, max_age_ms=10_000, now_fn=clock)

        # nalu_id=1 va fragmentado en 3 pedazos y es el más antiguo: debe eliminarse completo
        sched.enqueue(make_group(2000 * NS_PER_MS, Priority.NORMAL, nalu_id=1, n_fragments=3))
        sched.enqueue(make_group(3000 * NS_PER_MS, Priority.NORMAL, nalu_id=2))
        sched.enqueue(make_group(4000 * NS_PER_MS, Priority.NORMAL, nalu_id=3))

        self.assertEqual(sched.dropped[Priority.NORMAL], 1)
        seen = []
        while sched.has_packets():
            g = sched.dequeue()
            for p in g:
                seen.append((p.nalu_id, p.fragment_index, p.fragment_count))
        self.assertNotIn(1, [n for n, _, _ in seen])            # ningún pedazo de nalu_id=1
        self.assertEqual([n for n, _, _ in seen], [2, 3])

    def test_has_packets_y_dequeue_vacio(self):
        clock = FakeClock(now=0)
        sched = PacketScheduler(max_entries=4, max_age_ms=1000, now_fn=clock)

        self.assertFalse(sched.has_packets())
        self.assertIsNone(sched.dequeue())

        sched.enqueue(make_group(1, Priority.LOW, nalu_id=7))
        self.assertTrue(sched.has_packets())
        self.assertEqual(sched.dequeue()[0].nalu_id, 7)
        self.assertFalse(sched.has_packets())

    def test_enqueue_vacio_no_hace_nada(self):
        clock = FakeClock(now=0)
        sched = PacketScheduler(max_entries=4, max_age_ms=1000, now_fn=clock)

        sched.enqueue([])
        self.assertFalse(sched.has_packets())
        self.assertEqual(sched.dropped_count(), 0)

    def test_max_entries_cero_descarta_todo(self):
        clock = FakeClock(now=0)
        sched = PacketScheduler(max_entries=0, max_age_ms=1000, now_fn=clock)

        sched.enqueue(make_group(1, Priority.NORMAL, nalu_id=5))
        self.assertFalse(sched.has_packets())
        self.assertEqual(sched.dropped_count(), 1)


if __name__ == "__main__":
    unittest.main()