import sys

import numpy as np
import pyqtgraph
import pyqtgraph.exporters
from PyQt5.QtWidgets import QMainWindow, QWidget, QStatusBar, QLabel, QFrame
from PyQt5.QtCore import QTime, Qt, pyqtSignal, pyqtSlot, pyqtBoundSignal, pyqtProperty, QMutex, QMutexLocker, QByteArray
from PyQt5.QtGui import QPixmap, QImage

from skimage.exposure import rescale_intensity

from PyQt5.uic.Compiler.qtproxies import QtCore
from qwt import QwtPlot, QwtPlotGrid, QwtPlotCurve, QwtPlotItem
from qwt.plot_series import QwtSeriesData, QwtPointArrayData, QPointF
from PyQt5 import uic

import ctypes
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import time

import cattrs
import yaml
import pathlib

from pipethread import PipeThread

from galvocontroller import run_daq_tasks

PACKETLENGTH_MULTIPLIER = 1



class MainWindow(QMainWindow):

    cam = ctypes.WinDLL(
        name=r"\Cam Coptronix\USBLC8M_DLL\64Bit\usblc8m64.dll")

    packetlength = None
    is16bit = None
    wpixelcount = None

    PlotRefreshTimer: QTime = None

    data = None

    gv_task = None

    def __init__(self):
        super().__init__()

        self.ui = uic.loadUi(r"mainwindow_layout_v3.ui", self)

        self.init_statusBar()

        self.is16bit = 1 # int value to express combobox selection if 8 or 16 bit
        self.wpixelcount = 4096
        self.packetlength = (self.wpixelcount  * 2) * PACKETLENGTH_MULTIPLIER

        # ls_initialize If the function successes, it returns a message identifier in the range 0xC000
        # through 0xFFFF otherwise it returns 0.
        # todo: The ls_initialize function does not match the API or what are the omitted parameters?
        dwPipeSize = int( 4 * 1024 * 1024)
        print('init: {:x}'.format( self.cam.ls_initialize( dwPipeSize, self.packetlength)))
        # See API doc.
        # The ring-buffer size is dwPipeSize in bytes. So here a ring-buffer size of 4 Megabytes is defined.
        # Reading the amount of packetLength from the hardware FIFO (ringbuffer). This value must be * 2 for 16 bit
        # The two additional parameters are ThreadClass and ThreadPrio (not used here).
        # The ThreadClass and ThreadPrio are C-function priority settings.

        self.create_chart(self.wpixelcount)
        self.configure_2D_imageView()


        self.ThPipe = PipeThread(self)
        self.ThPipe.data_ready.connect(self.OnDataChanged)
        self.ThPipe.img_ready.connect(self.on2D_DataChanged)
        self.PlotRefreshTimer = QTime()
        self.PlotRefreshTimer.start()
        self.plot_mx = QMutex()

        self.read_GvParameters()


    def startpipethread(self, pxlcnt, bits16):
        print('startpipethread ...')
        self.ThPipe.is16bit = bits16
        self.ThPipe.BufSize = pxlcnt * (bits16 + 1)

        self.ThPipe.start()

    def stoppipethread(self):
        print('stoppipethread ...')

        if self.ThPipe.isRunning():

            self.ThPipe.stopthread()
            # self.ThPipe.wait()

            # todo: The ThPipe.stop() does not strictly close but crash the app.
            # But for the moment I don't care if nothing else goes wrong.
            # self.ThPipe.terminate() # for debugging reasons this was at least killing the App more reliably
            self.ThPipe.wait() # original from Qt++ example


    def open_device(self, index):
        print('open_device', index)
        cam = self.cam
        tmp_packetlength = ctypes.c_int32()  # qint32
        tmp_sensortype = ctypes.c_uint16()  # quint16
        tmp_pixelcount = ctypes.c_uint16()  # quint16
        ierr = 0

        current_idx = cam.ls_currentdeviceindex()
        if current_idx >= 0:
            self.close_device()
        else:
            dev_cnt = cam.ls_devicecount()

            if dev_cnt > 0:
                ierr = cam.ls_opendevicebyindex(index)

                if (ierr == 0):
                    ierr = cam.ls_getpacketlength(ctypes.byref(tmp_packetlength))

                    if (ierr == 0):

                        assert self.packetlength is not None, 'packetlength not initialized'
                        if (tmp_packetlength.value != (self.packetlength / PACKETLENGTH_MULTIPLIER)):

                            self.packetlength = int(tmp_packetlength.value * PACKETLENGTH_MULTIPLIER)

                            cam.ls_closedevice()

                            ierr = cam.ls_setpacketlength(self.packetlength)


                            ierr = cam.ls_opendevicebyindex(index)
                            if (ierr != 0):
                                cam.ls_geterrorstring.restype = ctypes.c_char_p
                                self.statusMsg.setText("OPEN DEVICE: " + cam.ls_geterrorstring(ierr).decode('utf-8'))
                                return

                    else:
                        cam.ls_geterrorstring.restype = ctypes.c_char_p
                        self.statusMsg.setText("GET PACKETLENGTH: "+cam.ls_geterrorstring(ierr).decode('utf-8'))


                    ierr = cam.ls_getsensortype(ctypes.byref(tmp_sensortype),ctypes.byref(tmp_pixelcount))


                    if (ierr == 0):
                        self.wsensortype = tmp_sensortype.value
                        self.wpixelcount = tmp_pixelcount.value

                    else:
                        cam.ls_geterrorstring.restype = ctypes.c_char_p
                        self.statusMsg.setText("GET SENSORTYPE: "+ cam.ls_geterrorstring(ierr).decode('utf-8'))


                    self.syncparam()


                    self.init_chart(self.wpixelcount,self.is16bit)


                    self.startpipethread(self.wpixelcount,self.is16bit)

                    self.ui.btn_open.setText("close")
                else:
                    cam.ls_geterrorstring.restype = ctypes.c_char_p
                    self.statusMsg.setText("OPEN DEVICE: "+cam.ls_geterrorstring(ierr).decode('utf-8'))

        if ierr > 0:
            print('open_device exit message ', cam.ls_geterrorstring(ierr).decode('utf-8'))
        else:
            print('open_device exit done')

    def close_device(self):
        # this is called from main. If the app loop has stopped due to cancel or else it runs the subsequent functions.
        print('close_device ...')
        idx = self.cam.ls_currentdeviceindex()

        if (idx >= 0):
            self.stoppipethread()
            self.cam.ls_closedevice()
            self.ui.btn_open.setText("open")

    def syncparam(self):
        print('synchparam ...')

        cam         = self.cam

        bcdversion  = None
        u8tmp       = ctypes.c_uint8() # quint8
        u16tmp      = ctypes.c_uint16() # quint16
        u32tmp      = ctypes.c_uint32() # quint32
        i16tmp      = ctypes.c_uint16() # quint16
        ftmp        = ctypes.c_float() # float

        cur_idx = cam.ls_currentdeviceindex()
        bcdversion = cam.ls_getfwversion(cur_idx)


        if bcdversion >= 0x0114:
            self.ui.btn_trigtime.setEnabled(True)
            self.ui.ed_trigtime.setEnabled(True)

            ierr = cam.ls_getsofttrigtime(ctypes.byref(u32tmp))


            if ierr == 0:
                self.ui.ed_trigtime.setText(str(u32tmp.value))
        else:
            self.ui.ed_trigtime.setText("0")
            self.ui.btn_trigtime.setDisabled(True)
            self.ui.ed_trigtime.setDisabled(True)

        ierr = cam.ls_getstate(ctypes.byref(u8tmp))

        if ierr == 0:
            if (u8tmp.value == 0):
                self.ui.btn_start.setText("start")
            else:
                self.ui.btn_start.setText("stop")

        ierr = cam.ls_getmode(ctypes.byref(u8tmp))

        if ierr == 0:
            self.ui.cb_mode.blockSignals(True)
            self.ui.cb_mode.clear()
            self.ui.cb_mode.addItem("ONE SHOT")
            self.ui.cb_mode.addItem("EXT. TRIGGER")
            self.ui.cb_mode.addItem("FREE RUNNING")
            self.ui.cb_mode.addItem("EXT. EXP. CTRL")

            if (bcdversion >= 0x0114):
                self.ui.cb_mode.addItem("SOFT TRIGGER")

            self.ui.cb_mode.setCurrentIndex(u8tmp.value)
            self.ui.cb_mode.blockSignals(False)

        ierr = cam.ls_getinttime(ctypes.byref(u32tmp))

        if ierr == 0:
            self.ui.ed_inttime.setText(str(u32tmp.value))

        ierr = cam.ls_getextdelay(ctypes.byref(u32tmp))

        if ierr == 0:
            self.ui.ed_delay.setText( str( u32tmp.value))

        ierr = cam.ls_getadcconfig(ctypes.byref(u16tmp))

        if ierr == 0:
            self.ui.cb_fullscale.blockSignals(True)
            self.ui.cb_fullscale.setCurrentIndex((u16tmp.value >> 7) & 0x01)
            self.ui.cb_fullscale.blockSignals(False)

        ierr = cam.ls_getadcpga1(ctypes.byref(u16tmp))

        if ierr == 0:
            self.ui.hs_gain.blockSignals(True)
            self.ui.hs_gain.setValue(u16tmp.value)
            self.ui.hs_gain.blockSignals(False)
            self.ui.lb_gain.setText( str('{:.4f} V/V'.format( 6 / (1 + (5 * ((63 - u16tmp.value) / 63))) )) )

        ierr = cam.ls_getadcoffset1(ctypes.byref(u16tmp))

        if ierr == 0:
            i16tmp_py = u16tmp.value & 0xFF
            if ((u16tmp.value & 0x0100) == 0x0100):
                i16tmp_py = i16tmp_py * (-1)

            self.ui.hs_offset.blockSignals(True)
            self.ui.hs_offset.setValue(i16tmp_py)
            self.ui.hs_offset.blockSignals(False)

            ftmp = i16tmp_py * 1.2
            if (ftmp < -300): ftmp = -300
            if (ftmp > 300): ftmp = 300
            self.ui.lb_offset.setText( str('{:0.1f} mV'.format( ftmp )))

        ierr = cam.ls_getcfg1( ctypes.byref(u8tmp))

        if ierr == 0:

            # labelImages = (u8tmp.value & 0x01)
            # BitMode = (u8tmp.value & 0x02) >> 1
            # numFrames = ((u8tmp.value & 0x7C) >> 2) + 1


            self.ui.cb_imagenum.setCurrentIndex(u8tmp.value & 0x01)
            self.ui.cb_168BitMode.setCurrentIndex(int((u8tmp.value & 0x02) >> 1))
            self.is16bit = self.ui.cb_168BitMode.currentIndex()
            self.ui.sb_numframes.setValue(((u8tmp.value & 0x7C) >> 2)+1)



    def init_statusBar(self):
        self.bar:QStatusBar = self.ui.statusBar

        self.statusMsg = QLabel()
        self.statusMsg.setMinimumSize (350,20)
        self.statusMsg.setFrameShape (QFrame.WinPanel)
        self.statusMsg.setFrameShadow (QFrame.Sunken)

        self.statusFPS = QLabel()
        self.statusFPS.setMinimumSize (175,20)
        self.statusFPS.setFrameShape (QFrame.WinPanel)
        self.statusFPS.setFrameShadow (QFrame.Sunken)

        self.statusMEM = QLabel()
        self.statusMEM.setMinimumSize (80,20)
        self.statusMEM.setFrameShape (QFrame.WinPanel)
        self.statusMEM.setFrameShadow (QFrame.Sunken)

        self.bar.addWidget (self.statusMsg)
        self.bar.addWidget (self.statusFPS)
        self.bar.addWidget (self.statusMEM)

        self.statusMsg.setText ("USB LINE CAMERA")
        self.statusFPS.setText ("FPS: 0")
        self.statusMEM.setText ("MEM: 0")

    def create_chart(self, wpixelcount):
        print('create chart ...')
        self.plot = QwtPlot(self.ui.plotwidget)
        plot = self.plot
        plot.setTitle( "USB Line Camera 8M" )
        plot.setCanvasBackground( Qt.white );
        plot.setAxisScale( QwtPlot.yLeft, 0, 65535)
        plot.setAxisScale( QwtPlot.xBottom, 0, wpixelcount-1)

        grid = QwtPlotGrid()
        grid.attach(plot)

        self.curve = QwtPlotCurve("Curve 1")
        curve = self.curve
        curve.setPen( Qt.blue, 0, Qt.PenStyle.SolidLine)
        curve.setRenderHint( QwtPlotItem.RenderAntialiased, True )

        self.seriesdata = QwtPointArrayData(list(range(0,wpixelcount)), [0]*wpixelcount)
        # for i,point in enumerate(seriesdata):
        #     point = QPointF(i,0)

        curve.setData(self.seriesdata)
        curve.attach(plot)
        # plot.resize( 500, 320 )
        # todo: can we resize the plot with some sliders or some input fields?
        plot.resize(400, 400)
        plot.replot()



    def init_chart(self, wpixelcount, is16bit):
        print('init_chart ...', wpixelcount, is16bit)

        if is16bit == 1:
            self.plot.setAxisScale( QwtPlot.yLeft, 0, 65535)
        else:
            self.plot.setAxisScale( QwtPlot.yLeft, 0, 255)


        self.plot.setAxisScale(QwtPlot.xBottom, 0, wpixelcount - 1)


        self.seriesdata = QwtPointArrayData( list( range( 0, wpixelcount)), [0] * wpixelcount)


        self.plot.replot()


    def on_btn_enum_pressed(self):
        print('on_btn_enum_pressed ...')
        cam = self.cam
        self.close_device()
        self.ui.cb_devices.clear()
        dev_cnt = cam.ls_enumdevices()


        if dev_cnt > 0:
            self.statusMsg.setText("ENUM DEVICES: " + str(dev_cnt) + " DEVICE(S) FOUND")

            for i in range(dev_cnt):
                cam.ls_getproductname.restype = ctypes.c_char_p
                pname = cam.ls_getproductname(i).decode('utf-8')

                cam.ls_getserialnumber.restype = ctypes.c_char_p
                snr = cam.ls_getserialnumber(i).decode('utf-8')

                self.ui.cb_devices.addItem(pname + " " + snr)
                # self.ui.cb_devices.addItem('test')

            self.ui.cb_devices.setCurrentIndex(0)
            currentIndex = self.ui.cb_devices.currentIndex()

            self.open_device(self.ui.cb_devices.currentIndex())
        else:
            self.statusMsg.setText("ENUM DEVICES: NO DEVICES FOUND")


    def on_btn_open_pressed(self):
        self.open_device(self.ui.cb_devices.currentIndex())


    def on_btn_start_pressed(self):

        state = ctypes.c_uint8()
        mode = ctypes.c_uint8()
        ierr = None

        ierr = self.cam.ls_getstate(ctypes.byref(state)) # is acquisition running?

        if ierr == 0:

            state_v = state.value
            state_v = (state_v & 0x01) ^ 0x01 # flip state or if higher values set to 1 or 0
            ierr = self.cam.ls_setstate(state_v)

            if ierr == 0:
                # Get mode can be 0 to 4. Free running is 2.
                # So the start/stop flip only happens if Single Shot (0).
                self.cam.ls_getmode(ctypes.byref(mode))
                mode_v = mode.value

                if state_v == 0 or mode_v == 0:

                    self.ui.btn_start.setText("start")

                else:

                    self.ui.btn_start.setText("stop")


        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        ststr = self.cam.ls_geterrorstring(ierr).decode('utf-8')
        self.ui.statusMsg.setText("SET STATE: " + ststr)


    def on_btn_inttime_pressed(self):
        ierr = None
        u32tmp = ctypes.c_uint32()

        ierr = self.cam.ls_setinttime(int(self.ui.ed_inttime.text()))
        if ierr == 0:
            if self.cam.ls_getinttime(ctypes.byref(u32tmp)) == 0:
                self.ui.ed_inttime.setText(str(u32tmp.value))

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET INT.TIME: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))


    def on_hs_gain_valueChanged(self, value):
        if type(value) is str: return

        ierr = 0
        fgain = None

        ierr = self.cam.ls_setadcpga1(value)

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET GAIN: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))

        fgain = 6 / (1 + (5 * ((63 - float(value)) / 63)))
        self.ui.lb_gain.setText('{:1.4f} V/V'.format(fgain))


    def on_hs_offset_valueChanged(self, value):
        if type(value) is str: return

        newvalue = None
        wvalue = None
        sign = None
        ierr = None

        newvalue = float( value * 1.2 )
        if (newvalue < -300): newvalue = -300
        if (newvalue > 300): newvalue = 300

        if (value < 0):
            sign = 0x0100
        else:
            sign = 0

        wvalue = abs(value) | sign

        ierr = self.cam.ls_setadcoffset1(wvalue)

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET OFFSET: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))

        self.ui.lb_offset.setText('{:1.1f} mV'.format(newvalue))

    def on_cb_mode_currentIndexChanged(self, index):
        if type(index) is str: return
        ierr = None

        ierr = self.cam.ls_setmode(index)

        if ((ierr == 0) and (index == 0)):
            self.ui.btn_start.setText("start")

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET MODE: "+ self.cam.ls_geterrorstring(ierr).decode('utf-8'))

    def on_cb_fullscale_currentIndexChanged(self, index):
        if type(index) is str: return

        ierr = None
        # 1.3.29 ls_SetADCConfig
        # function ls_setadcconfig(wConfig : WORD) : DWORD;
        # ls_SetADCConfig sets the ADC configuration register.
        # A value of 0x0080 sets the input range of ADC to 4V, and a value of 0x0000 to 2V.
        # If the function fails, the return value (dwErr) is non zero.

        # This seems not well explained here.
        # The index is only the selection index for 2 or 4 V range.
        # Bitshifting by << 7 would make the value of (1) to 0x80.
        adc_conf = index << 7
        ierr = self.cam.ls_setadcconfig(adc_conf)

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("FULL SCALE: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))

    def on_btn_savesettings_pressed(self):
        ierr = None

        ierr = self.cam.ls_savesettings()
        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SAVE SETTINGS: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))

    def on_btn_getinfo_clicked(self):
        cam = self.cam
        ierr = None #qint32
        # u16tmp =  # quint16
        i32tmp = ctypes.c_uint32() #quint32

        u32tmp = ctypes.c_uint32() # quint32
        sensor = ctypes.c_uint16() # quint16
        pixel = ctypes.c_uint16() # quint16
        idx = ctypes.c_uint() # int

        # this is the combobox of devices --> needs to be filled first
        idx = self.ui.cb_devices.currentIndex()

        cam.ls_getvendorname.restype = ctypes.c_char_p
        self.ui.lb_vendor.setText(cam.ls_getvendorname(idx).decode('utf-8'))
        cam.ls_getproductname.restype = ctypes.c_char_p
        self.ui.lb_product.setText(cam.ls_getproductname(idx).decode('utf-8'));
        cam.ls_getserialnumber.restype = ctypes.c_char_p
        self.ui.lb_serial.setText(cam.ls_getserialnumber(idx).decode('utf-8'));


        u16tmp = cam.ls_getfwversion(idx)
        major_v = str((u16tmp>>8) & 0xFF)
        minor_v = str((u16tmp) & 0xFF)
        self.ui.lb_mcu1version.setText(major_v + "." + minor_v);

        ierr = cam.ls_getsensortype(ctypes.byref(sensor), ctypes.byref(pixel))
        cam.ls_geterrorstring.restype = ctypes.c_char_p
        serr = cam.ls_geterrorstring(ierr).decode('utf-8')

        cam.ls_getsensorname.restype = ctypes.c_char_p
        sensorname = cam.ls_getsensorname(sensor.value).decode('utf-8')
        self.ui.lb_sensor.setText(str(sensor.value) + " <" + sensorname +">")

        self.ui.lb_pixel.setText(str(pixel.value))

        ierr = cam.ls_getmcusensortype(ctypes.byref(sensor))
        if (ierr == 0):
            sensormcuname = cam.ls_getsensorname(sensor.value).decode('utf-8')
            self.ui.lb_mcu2sensor.setText("0x"+ str(sensor.value) + " <" + sensormcuname + ">")

        ierr = cam.ls_getpacketlength(ctypes.byref(i32tmp))
        if (ierr == 0):
            self.ui.lb_mcu2packet.setText( str(i32tmp.value) + " Bytes")
        else:
            self.ui.lb_mcu2packet.setText("?0")

        ierr = cam.ls_customfirmware(ctypes.byref(u32tmp))
        if (ierr == 0):
            self.ui.lb_custom.setText( str(u32tmp.value))
        else:
            self.ui.lb_custom.setText("?0")

        ### This ls_libversion does not exist actually
        # cam.ls_libversion.restype = ctypes.c_uint32
        # u16tmp = cam.ls_libversion()
        # self.ui.lb_libversion.setText(str((u16tmp.value >> 8) & 0xFF)) + "." + str( (u16tmp.value & 0xFF))

    def on_btn_delay_pressed(self):
        ierr = None
        u32tmp = ctypes.c_uint32()

        ierr = self.cam.ls_setextdelay(int(self.ui.ed_delay.text()))
        if (ierr == 0):
            if (self.cam.ls_getextdelay(ctypes.byref(u32tmp)) == 0):
                self.ui.ed_delay.setText(str(u32tmp.value))

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET EXT.DELAY: " + self.cam.ls_geterrorstring(ierr).decode('utf-8'))

    def on_pb_CFG1_pressed(self):
        # This is setCFG1
        ierr = None
        uccfg1 = None
        # Number of images to be buffered before transferring to the host.
        # This value deteremines the value of dwPacketLength used in
        # functions ls_initialize and ls_setpacketlength.
        # The max. number of images depends on the number of pixels.
        # e.g. for 2048 pixel the max. number of images is:
        # 16Bit mode: 4 images
        # 8Bit mode: 8 images.

        # Bit 0 to 6 are used only.
        # The first line pushes te number of frames to bit 2...6
        # The second line pushes the bit mode to bit 1
        # The third line pushes the imagenum to bit 0.
        # The & suggests that the bits are flipped.
        uccfg1 = (self.ui.sb_numframes.value() & 0x1F) - 1;
        uccfg1 = (uccfg1 << 1) | (self.ui.cb_168BitMode.currentIndex() & 0x01)
        uccfg1 = (uccfg1 << 1) | (self.ui.cb_imagenum.currentIndex() & 0x01)
        ierr = self.cam.ls_setcfg1(uccfg1)
        if (ierr == 0):
            #    Changes takes effect after reboot - Power OFF / ON
            pass

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET CFG1: "+self.cam.ls_geterrorstring(ierr).decode('utf-8'))



    def OnDataChanged(self, buf, BytesRead, BytesAvailable, fps):


        self.statusMEM.setText("MEM: {}".format(BytesAvailable))
        self.statusFPS.setText("FPS: {}".format(fps))

        if self.data is not None:
            # self.curve.setData( np.r_[0:2048], np.sin(np.r_[0:2048]*2*np.pi*0.01)*10000 + 20000 )
            # self.curve.setData( np.r_[0:BytesRead], np.array(buf,dtype=np.uint16) * 10 + 1000)
            self.curve.setData( np.r_[0:BytesRead], self.data ) #,dtype=np.uint16))
            self.plot.replot() # Calling this bare for debugging

        # if self.PlotRefreshTimer.elapsed() > 100:
        #     self.plot.replot()
        #     self.PlotRefreshTimer.restart()



    def configure_2D_imageView(self):
        self.ui.graphicsView.ui.histogram.hide()
        self.ui.graphicsView.ui.roiBtn.hide()
        self.ui.graphicsView.ui.menuBtn.hide()
        # pyqtgraph.GraphicsView.autoLevels()
        # self.ui.graphicsView.autoLevels(False)

    def on_sb_thresh_upper_valueChanged(self, value):
        if type(value) is str: return



    def on_sb_thresh_lower_valueChanged(self, value):
        if type(value) is str: return


    def on2D_DataChanged(self, BytesRead, BytesAvailable, fps):
        self.statusMEM.setText("MEM: {}".format(BytesAvailable))
        self.statusFPS.setText("FPS: {:d}".format(fps))
        # self.statusFPS.setText("FPS: test")

        if self.data is not None:

            if self.PlotRefreshTimer.elapsed() > 0.0001:
                # im_data = np.random.random([400,400])*1

                im_data = self.data
                if self.ui.chb_Rot.isChecked():
                    im_data = np.rot90(im_data, k=1)
                if self.ui.chb_Flip.isChecked():
                    im_data = np.flip(im_data)


                # todo: we currently brute force the threshold values with each plot update.
                # This seems not to make too much trouble but we can changes this if it becomes a problem.
                if self.ui.chb_autolevels.isChecked():
                    self.ui.graphicsView.setImage(im_data)
                    self.ui.sb_thresh_lower.setValue(float(self.ui.graphicsView.getLevels()[0]))
                    self.ui.sb_thresh_upper.setValue(float(self.ui.graphicsView.getLevels()[1]))
                else:
                    self.ui.graphicsView.setImage(im_data, autoLevels = False, levels = (self.ui.sb_thresh_lower.value(), self.ui.sb_thresh_upper.value()))



                self.PlotRefreshTimer.restart()

    def collect_meta_data(self):
        '''
        Retrieve configuration data and write those into the metadata of the image to be stored.
        Return metadata.
        '''
        metadata = PngInfo()
        metadata.add_text('intensity scale gui', '[{:}, {:}]'.format(self.ui.sb_thresh_lower.value(), self.ui.sb_thresh_upper.value()))
        metadata.add_text('int time', self.ui.ed_inttime.text())
        metadata.add_text('delay', self.ui.ed_delay.text())
        metadata.add_text('trig time', self.ui.ed_trigtime.text())
        fgain = 6 / (1 + (5 * ((63 - float(self.ui.hs_gain.value())) / 63)))
        metadata.add_text('gain', '{:1.4f} V/V'.format(fgain))
        newvalue = float(self.ui.hs_offset.value() * 1.2)
        if (newvalue < -300): newvalue = -300
        if (newvalue > 300): newvalue = 300
        metadata.add_text('offset', '{:1.1f} mV'.format(newvalue))
        metadata.add_text('full scale', self.ui.cb_fullscale.currentText())
        metadata.add_text('bit size mode', self.ui.cb_168BitMode.currentText())
        metadata.add_text('number of frames', str(self.ui.sb_numframes.value()))
        metadata.add_text('is rot90', str(self.ui.chb_Rot.isChecked()))
        metadata.add_text('is flipped', str(self.ui.chb_Flip.isChecked()))
        metadata.add_text('comment', self.ui.le_comment.text())
        return metadata

    def on_btn_save_imgView_pressed(self):
        imgexp = pyqtgraph.exporters.ImageExporter(self.ui.graphicsView.imageItem)
        #imgexp.parameters()['width'] = 100 # from https://pyqtgraph.readthedocs.io/en/latest/user_guide/exporting.html
        tstamp_folder = time.strftime('%Y-%m-%d', time.localtime())
        tstamp_file = time.strftime('%y-%m-%d-%H-%M-%S', time.localtime())
        basepath = pathlib.Path(r"\LF-SLO\Data")
        # fpath = pathlib.Path(r"c:\Data\LFSLO")

        folder = basepath.joinpath(tstamp_folder)
        if not folder.exists(): folder.mkdir()

        filepath = folder.joinpath('lfslo-' + tstamp_file + '.png')
        assert not filepath.exists()
        print(f"save to {filepath.as_posix()}")

        imdata = np.array(self.data)
        imdata = rescale_intensity(image = imdata, in_range=(int(self.ui.sb_thresh_lower.value()), int(self.ui.sb_thresh_upper.value())))


        im = Image.fromarray(imdata)
        im.save(filepath.as_posix(), pnginfo = self.collect_meta_data())

        # Using image export from pyqtgraph saves the display image and if the window size is scaled smaller
        # the image is scaled down. So this is not what we want to save.
        # imgexp.export(filepath.as_posix())



    def on_btn_trigtime_clicked(self):
        ierr = 0
        u32tmp = ctypes.c_uint32()

        ierr = self.cam.ls_setsofttrigtime( int( self.ui.ed_trigtime.text()))
        if (ierr == 0):
            if (self.cam.ls_getsofttrigtime (ctypes.byref( u32tmp )) == 0):
                self.ui.ed_trigtime.setText( str(u32tmp.value))

        self.cam.ls_geterrorstring.restype = ctypes.c_char_p
        self.statusMsg.setText("SET TRIG TIME: "+self.cam.ls_geterrorstring(ierr).decode('utf-8'))

    def save_GvParameters(self):
        values = {'freq': self.ui.dbsb_freq.value(),
                  'ampl': self.ui.dbsb_amp.value(),
                  'offset': self.ui.dbsb_offset.value(),
                  'smpRate': self.ui.sb_smpRate.value(),
                  'smpNr': self.ui.sb_smpNr.value()}
        with open('galvo_settings.yaml','w+') as fp:
            yaml.dump(data=values, stream = fp)

    def read_GvParameters(self):
        values = None
        if pathlib.Path('galvo_settings.yaml').exists():
            with open('galvo_settings.yaml','r+') as fp:
                values = yaml.safe_load(stream = fp)
            self.ui.dbsb_freq.setValue(values['freq'])
            self.ui.dbsb_amp.setValue(values['ampl'])
            self.ui.dbsb_offset.setValue(values['offset'])
            self.ui.sb_smpRate.setValue(values['smpRate'])
            self.ui.sb_smpNr.setValue(values['smpNr'])
        else:
            print('no galvo settings. Use Default values.')

    def setEnabled_GvParameters(self, to_status):
        self.ui.dbsb_freq.setEnabled(to_status)
        self.ui.dbsb_amp.setEnabled(to_status)
        self.ui.dbsb_offset.setEnabled(to_status)
        self.ui.sb_smpRate.setEnabled(to_status)
        self.ui.sb_smpNr.setEnabled(to_status)

    def on_dbsb_offset_valueChanged(self, value):
        current_offset = self.ui.dbsb_offset.value()
        if type(value) is float:
            if (current_offset + self.ui.dbsb_amp.value()) >= 10.0:
                current_offset = 10.0 - self.ui.dbsb_amp.value()
                self.ui.dbsb_offset.setValue(current_offset)

    def on_dbsb_amp_valueChanged(self, value):
        current_amp = self.ui.dbsb_amp.value()
        if type(value) is float:
            if (current_amp + self.ui.dbsb_offset.value()) >= 10.0:
                current_amp = 10.0 - self.ui.dbsb_offset.value()
                self.ui.dbsb_amp.setValue(current_amp)

    def on_btn_galvo_start_pressed(self):
        print('galvo start')
        self.save_GvParameters()
        if self.gv_task is None:
            self.setEnabled_GvParameters(to_status=False)
            sampling_rate = self.ui.sb_smpRate.value()
            number_of_samples = self.ui.sb_smpNr.value()
            frequency = self.ui.dbsb_freq.value()
            amplitude = self.ui.dbsb_amp.value()
            offset = self.ui.dbsb_offset.value()
            self.gv_task = run_daq_tasks(
                sampling_rate,
                number_of_samples,
                frequency,
                amplitude,
                offset,
                phase_in=0.0,
                cam_duty=0.999,
                do_start=True)

    def on_btn_galvo_stop_pressed(self):
        print('galvo stop')
        if self.gv_task is not None:
            self.setEnabled_GvParameters(to_status=True)
            self.gv_task['ramp_task'].stop()
            self.gv_task['ramp_task'].close()
            self.gv_task['trig_task'].stop()
            self.gv_task['trig_task'].close()
            self.gv_task = None

    def on_btn_galvo_start2_pressed(self):
        print('galvo start2')
        self.save_GvParameters()
        if self.gv_task is None:
            self.setEnabled_GvParameters(to_status=False)
            self.setEnabled_GvParameters(to_status=False)
            sampling_rate = self.ui.sb_smpRate.value()
            number_of_samples = self.ui.sb_smpNr.value()
            frequency = self.ui.dbsb_freq.value()
            amplitude = self.ui.dbsb_amp.value()
            offset = self.ui.dbsb_offset.value()
            self.gv_task = run_daq_tasks(
                sampling_rate,
                number_of_samples,
                frequency,
                amplitude,
                offset,
                phase_in=0.0,
                cam_duty=0.999,
                do_start=True)

    def on_btn_galvo_stop2_pressed(self):
        print('galvo stop2')
        if self.gv_task is not None:
            self.setEnabled_GvParameters(to_status=True)
            self.gv_task['ramp_task'].stop()
            self.gv_task['ramp_task'].close()
            self.gv_task['trig_task'].stop()
            self.gv_task['trig_task'].close()
            self.gv_task = None
