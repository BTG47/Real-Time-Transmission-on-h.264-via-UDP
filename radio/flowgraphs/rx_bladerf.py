#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: BladeRF RX over ZMQ PDU (H.264 via GNU Radio)
# Description: Reference RX flowgraph: receives GMSK at 2.45 GHz / 20 Msps with a BladeRF via gr-bladeRF, correlates the access code, decodes the burst header (16-bit length), re-packs the payload bits and forwards the PMT PDU (pmt::serialize_str(cons(dict, u8vector))) over ZMQ PUSH bound to tcp://127.0.0.1:5556.
# GNU Radio version: 3.10.12.0

from gnuradio import blocks
from gnuradio import digital
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import gr, pdu
from gnuradio import zeromq
import bladeRF
import time
import threading




class rx_bladerf(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "BladeRF RX over ZMQ PDU (H.264 via GNU Radio)", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Blocks
        ##################################################

        self.zeromq_push_msg_sink_0 = zeromq.push_msg_sink('tcp://127.0.0.1:5556', 100, True)
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.byte_t, 'packet_len')
        self.digital_gmsk_demod_0 = digital.gmsk_demod(
            samples_per_symbol=8,
            gain_mu=0.175,
            mu=0.5,
            omega_relative_limit=0.005,
            freq_error=0.0,
            verbose=False,log=False)
        self.digital_correlate_access_code_xx_ts_0 = digital.correlate_access_code_bb_ts(digital.packet_utils.default_access_code,
          0, 'packet_len')
        self.blocks_repack_bits_bb_0 = blocks.repack_bits_bb(1, 8, 'packet_len', False, gr.GR_MSB_FIRST)
        self.bladeRF_source_0 = bladeRF.source(
            args="numchan=" + str(1)
                 + ",metadata=" + 'False'
                 + ",bladerf=" +  str('0')
                 + ",verbosity=" + 'warning'
                 + ",feature=" + 'default'
                 + ",sample_format=" + '16bit'
                 + ",fpga=" + str('')
                 + ",fpga-reload=" + 'False'
                 + ",use_ref_clk=" + 'False'
                 + ",ref_clk=" + str(int(10e6))
                 + ",buflen=" + str(int(4096))
                 + ",buffers=" + str(int(512))
                 + ",in_clk=" + 'ONBOARD'
                 + ",out_clk=" + str(False)
                 + ",use_dac=" + 'False'
                 + ",dac=" + str(10000)
                 + ",xb200=" + 'none'
                 + ",tamer=" + 'internal'
                 + ",sampling=" + 'internal'
                 + ",lpf_mode="+'disabled'
                 + ",smb="+str(int(38.4e6))
                 + ",dc_calibration="+'LPF_TUNING'
                 + ",trigger0="+'False'
                 + ",trigger_role0="+'master'
                 + ",trigger_signal0="+'J51_1'
                 + ",trigger1="+'False'
                 + ",trigger_role1="+'master'
                 + ",trigger_signal1="+'J51_1'
                 + ",bias_tee0="+'False'
                 + ",bias_tee1="+'False'


        )
        self.bladeRF_source_0.set_sample_rate(20e6)
        self.bladeRF_source_0.set_center_freq(2.45e9,0)
        self.bladeRF_source_0.set_bandwidth(20e6,0)
        self.bladeRF_source_0.set_dc_offset_mode(2, 0)
        self.bladeRF_source_0.set_iq_balance_mode(2, 0)
        self.bladeRF_source_0.set_gain_mode(False, 0)
        self.bladeRF_source_0.set_gain(40, 0)
        self.bladeRF_source_0.set_if_gain(20, 0)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, 'pdus'), (self.zeromq_push_msg_sink_0, 'in'))
        self.connect((self.bladeRF_source_0, 0), (self.digital_gmsk_demod_0, 0))
        self.connect((self.blocks_repack_bits_bb_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0), (self.blocks_repack_bits_bb_0, 0))
        self.connect((self.digital_gmsk_demod_0, 0), (self.digital_correlate_access_code_xx_ts_0, 0))





def main(top_block_cls=rx_bladerf, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
