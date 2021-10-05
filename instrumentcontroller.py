import random
import time

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
from forgot_again.file import load_ast_if_exists, pprint_to_file

from instr.instrumentfactory import mock_enabled, SourceFactory, AnalyzerFactory, GeneratorFactory, OscilloscopeFactory
from measureresult import MeasureResult
from secondaryparams import SecondaryParams

GIGA = 1_000_000_000
MEGA = 1_000_000
KILO = 1_000
MILLI = 1 / 1_000
MICRO = 1 / 1_000_000
NANO = 1 / 1_000_000_000


class InstrumentController(QObject):
    pointReady = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        addrs = load_ast_if_exists('instr.ini', default={
            'Осциллограф': 'GPIB1::7::INSTR',
            'Генератор вход': 'GPIB1::19::INSTR',
            'Генератор опорный': 'GPIB1::6::INSTR',
            'Источник': 'GPIB1::3::INSTR',
        })

        self.requiredInstruments = {
            'Осциллограф': OscilloscopeFactory(addrs['Осциллограф']),
            'Генератор вход': GeneratorFactory(addrs['Генератор вход']),
            'Генератор опорный': GeneratorFactory(addrs['Генератор опорный']),
            'Источник': SourceFactory(addrs['Источник']),
        }

        self.deviceParams = {
            'Приёмник': {
                'F': 1,
            },
        }

        self.secondaryParams = SecondaryParams(required={
            'ref_f': [
                'Fоп=',
                {'start': 10.0, 'end': 3000.0, 'step': 10.0, 'value': 100.0, 'suffix': 'MHz'}
            ],
            'ref_p': [
                'Pоп=',
                {'start': -60.0, 'end': 0.0, 'step': 1.0, 'value': 0.0, 'suffix': ' дБм'}
            ],
            'src_u': [
                'Uпит=',
                {'start': 3.0, 'end': 3.5, 'step': 0.1, 'value': 3.3, 'suffix': ' В'}
            ],
            'src_i_max': [
                'Iпот.макс=',
                {'start': 10.0, 'end': 80.0, 'step': 1.0, 'value': 60.0, 'suffix': ' В'}
            ],
        })
        self.secondaryParams.load_from_config('params.ini')

        self._instruments = dict()
        self.found = False
        self.present = False
        self.hasResult = False

        self.result = MeasureResult()

    def __str__(self):
        return f'{self._instruments}'

    # region connections
    def connect(self, addrs):
        print(f'searching for {addrs}')
        for k, v in addrs.items():
            self.requiredInstruments[k].addr = v
        self.found = self._find()

    def _find(self):
        self._instruments = {
            k: v.find() for k, v in self.requiredInstruments.items()
        }
        return all(self._instruments.values())

    def check(self, token, params):
        print(f'call check with {token} {params}')
        device, secondary = params
        self.present = self._check(token, device, secondary)
        print('sample pass')

    def _check(self, token, device, secondary):
        print(f'launch check with {self.deviceParams[device]} {self.secondaryParams}')
        self._init()
        return True
    # endregion

    # region calibrations
    def calibrate(self, token, params):
        print(f'call calibrate with {token} {params}')
        return self._calibrate(token, self.secondaryParams)

    def _calibrateLO(self, token, secondary):
        print('run calibrate LO with', secondary)
        result = {}
        self._calibrated_pows_lo = result
        return True

    def _calibrateRF(self, token, secondary):
        print('run calibrate RF')
        result = {}
        self._calibrated_pows_rf = result
        return True

    def _calibrateMod(self, token, secondary):
        print('calibrate mod gen')
        result = {}
        self._calibrated_pows_mod = result
        return True
    # endregion

    # region initialization
    def _clear(self):
        self.result.clear()

    def _init(self):
        self._instruments['Осциллограф'].send('*RST')
        self._instruments['Генератор вход'].send('*RST')
        self._instruments['Генератор опорный'].send('*RST')
        self._instruments['Источник'].send('*RST')
    # endregion

    def measure(self, token, params):
        print(f'call measure with {token} {params}')
        device, _ = params
        try:
            self.result.set_secondary_params(self.secondaryParams)
            self.result.set_primary_params(self.deviceParams[device])
            self._measure(token, device)
            # self.hasResult = bool(self.result)
            self.hasResult = True  # TODO HACK
        except RuntimeError as ex:
            print('runtime error:', ex)

    def _measure(self, token, device):
        param = self.deviceParams[device]
        secondary = self.secondaryParams.params
        print(f'launch measure with {token} {param} {secondary}')

        self._clear()
        _ = self._measure_tune(token, param, secondary)
        self.result.set_secondary_params(self.secondaryParams)
        return True

    def _measure_tune(self, token, param, secondary):
        osc = self._instruments['Осциллограф']
        gen_rf = self._instruments['Генератор вход']
        gen_ref = self._instruments['Генератор опорный']
        src = self._instruments['Источник']

        ref_f = secondary['ref_f'] * MEGA
        ref_p = secondary['ref_p']

        src_v = secondary['src_u']
        src_i_max = secondary['src_i_max'] * MILLI

        osc.send('*RST')
        gen_ref.send('*RST')
        gen_rf.send('*RST')
        src.send('*RST')

        # setup
        # osc.send(f':ACQ:AVERage {osc_`avg`}')

        # osc.send(':TRIGger:MODE EDGE')
        # osc.send(':TRIGger:EDGE:SOURCe CHANnel1')
        # osc.send(':TRIGger:LEVel CHANnel1,0')
        # osc.send(':TRIGger:EDGE:SLOPe POSitive')

        # osc.send(':MEASure:VAMPlitude channel1')
        # osc.send(':MEASure:VAMPlitude channel2')
        # osc.send(':MEASure:PHASe CHANnel1,CHANnel2')
        # osc.send(':MEASure:FREQuency CHANnel1')

        # gen_rf.send(f':OUTP:MOD:STAT OFF')

        src.send(f'APPLY p6v,{src_v}V,{src_i_max}mA')
        # src.send(f'APPLY p25v,{src_u_d}V,{src_i_d}mA')

        # pow_rf_values = [round(x, 3) for x in np.arange(start=rf_p_min, stop=rf_p_max + 0.0001, step=rf_p_step)] \
        #     if rf_p_min != rf_p_max else [rf_p_min]
        # freq_rf_values = [round(x, 3) for x in np.arange(start=rf_f_min, stop=rf_f_max + 0.0001, step=rf_f_step)] \
        #     if rf_f_min != rf_f_max else [rf_f_min]

        freq_rf_values = ['0_5', '1', '2', '5', '10', '20', '50']
        pow_rf_values = ['1', '1_25', '1_5']
        pows = {
            '1': -104,
            '1_25': -102,
            '1_5': -104,
        }

        r"""
        1. load waveform - :WMEMory1:LOAD "C:\Users\Administrator\Documents\Yastrebov\test2.wfm"
        2. turn 1 chan off - :CHAN1:DISP OFF
        3. add chan3 to chan1 - :FUNCtion1:ADD channel3,channel1
        4. show result - :FUNCtion1:DISPlay
        """

        # gen_ref.send(f':OUTP:MOD:STAT OFF')
        gen_ref.send(f'SOUR:POW {ref_p}dbm')
        gen_ref.send(f'SOUR:FREQ {ref_f}dbm')
        gen_ref.send(f'OUTP:STAT ON')

        # measurement
        timebases = [
            2.5 * 2 * MICRO, 2.5 * 2 * MICRO, 2.5 * 2 * MICRO,
            2.5 * 2 * MICRO, 2.5 * 2 * MICRO, 2.5 * 2 * MICRO,
            1 * 2 * MICRO, 1 * 2 * MICRO, 1 * 2 * MICRO,
            500 * 2 * NANO, 500 * 2 * NANO, 500 * 2 * NANO,
            500 * 2 * NANO, 250 * 2 * NANO, 250 * 2 * NANO,
            100 * 2 * NANO, 100 * 2 * NANO, 100 * 2 * NANO,
            50 * 2 * NANO, 50 * 2 * NANO, 50 * 2 * NANO,
        ]
        osc.send(':CHAN1:DISP OFF')
        osc.send(':CHAN2:DISP OFF')
        src.send('OUTP ON')

        index = 0
        for rf_freq in freq_rf_values:
            rf_freq_num = (float(rf_freq.replace('_', '.')) + 1_600) * MEGA
            gen_rf.send(f'SOUR:FREQ {rf_freq_num}')
            for rf_p in pow_rf_values:

                if token.cancelled:
                    src.send('OUTP OFF')
                    gen_rf.send(f'OUTP:STAT OFF')
                    time.sleep(0.2)

                    gen_rf.send(f'SOUR:POW {pow_rf_values[0]}dbm')
                    gen_rf.send(f'SOUR:FREQ {freq_rf_values[0]}Hz')

                    osc.send('*RST')
                    osc.send(':CHAN1:DISP OFF')
                    osc.send(':CHAN2:DISP OFF')
                    raise RuntimeError('measurement cancelled')

                timebase = timebases[index]
                osc.send(f':TIMEBASE:RANGE {timebase}s')
                index += 1
                osc.send(f':chan1:SCALE 1V')  # V
                osc.send(f':chan2:SCALE 1V')

                gen_rf.send(f'SOUR:POW {pows[rf_p]}dbm')
                gen_ref.send(f'OUTP:STAT ON')
                # TODO skip 5 - 1
                if not mock_enabled:
                    time.sleep(0.1)

                chan = 1
                osc.send(f':WMEMory{chan}:LOAD "C:\\Users\\Administrator\\Documents\\Yastrebov\\{rf_freq}M{rf_p}V{chan}ch.csv"')
                osc.send(f':WMEMory{chan}:YOFFset 0')
                osc.send(f':WMEMory{chan}:YRANge 2V')

                chan = 2
                osc.send(f':WMEMory{chan}:LOAD "C:\\Users\\Administrator\\Documents\\Yastrebov\\{rf_freq}M{rf_p}V{chan}ch.csv"')
                osc.send(f':WMEMory{chan}:YOFFset 0')
                osc.send(f':WMEMory{chan}:YRANge 2V')

                if not mock_enabled:
                    time.sleep(1.3)

                r"""
                1. load waveform - :WMEMory1:LOAD "C:\Users\Administrator\Documents\Yastrebov\test2.wfm"
                2. turn 1 chan off - :CHAN1:DISP OFF
                3. add chan3 to chan1 - :FUNCtion1:ADD channel3,channel1
                4. show result - :FUNCtion1:DISPlay
                """

        src.send('OUTP OFF')
        osc.send('*RST')
        osc.send(':CHAN1:DISP OFF')
        osc.send(':CHAN2:DISP OFF')
        return []


    def _add_measure_point(self, data):
        print('measured point:', data)
        self.result.add_point(data)
        self.pointReady.emit()

    def saveConfigs(self):
        pprint_to_file('params.ini', self.secondaryParams.params)

    @pyqtSlot(dict)
    def on_secondary_changed(self, params):
        self.secondaryParams.params = params

    @property
    def status(self):
        return [i.status for i in self._instruments.values()]
