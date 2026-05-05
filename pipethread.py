import numpy as np
from PyQt5.QtCore import QThread, QMutexLocker, QMutex, pyqtSignal, QTime
import ctypes
from ctypes import wintypes as w
import time # debugging
# import matplotlib.pyplot as pp


class PipeThread(QThread):

    stop = None
    stop_mx = None
    BufSize = None
    is16bit = None
    mw = None

    data_refresh = QTime

    data_ready = pyqtSignal(list, int, int, int)

    # todo: Due to the fact that we may not need the data sync of the emit function we may drop the data emission entirely
    img_ready = pyqtSignal(int, int, int)

    def __init__(self, mainWindow):
        super().__init__()
        self.mw = mainWindow
        self.stop = False
        self.stop_mx = QMutex()
        self.data_refresh = QTime()
        self.data_refresh.start()


    def run(self):
        cam = self.mw.cam

        ctBytesRead = ctypes.c_int32()
        ctBytesAvailable = ctypes.c_int32()
        ctFps = ctypes.c_int32()

        timeout = 5000

        # todo: The example suggests hardcoding a BufSize = 2048 if it was 0. Why?
        # For the moment if it is working I leave it as is.
        # But it may refer to the use of the 16 bit vs 8 bit data format.
        # The hardcoded part here may be coincidental if the example code was not complete.
        if self.BufSize == 0:
            self.BufSize = 4096 # 2 * 2048 pixel

        npCamBuf = np.array([0]*self.BufSize, dtype=np.uint16)
        ctCamBuf = npCamBuf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16))

        np2DImageBuf = np.zeros([int(self.BufSize/2)+1, int(self.BufSize/2)+1],dtype=np.uint16)

        print('enter loop ...')
        while True:
        # for i in range(1):
            if self.shouldstop(): break

            print_test_timing = False
            if print_test_timing:
                print('access pipe ...')
                time.sleep(1.01)
                # If the camera read is active we need to allow for some delay.
                # Although, the delay may be naturally provided by the camera read function.
                t = time.time()
                print('time', t)

            simulate_data = False
            if simulate_data:
                BytesRead = 4096
                BytesAvailable = 222
                fps = 333
                if self.data_refresh.elapsed() > 0.001:
                    npBuf_lst = list(np.random.randint(size=4096, low=0, high=1500, dtype=np.uint16) + 3000)
                    self.data_ready.emit([],BytesRead, BytesAvailable, fps)
                    self.mw.data = npBuf_lst
                    self.data_refresh.restart()

            camera_read = False
            if camera_read:
                ierr = cam.ls_waitforpipe(timeout)

                getBytesAvailable = 0
                ierr = cam.ls_getpipe(ctCamBuf, getBytesAvailable, ctypes.byref(ctBytesRead))
                BytesAvailable = ctBytesRead.value
                # todo: 2D reconstruction --> reading the lines and assemble into 2D array somewhere around here.
                # We may actually make a second function for that so we can monitor different lines for debugging.
                # The tab widget is already there.

                if ctBytesRead.value >= self.BufSize:
                    ierr = cam.ls_getpipe(ctCamBuf, self.BufSize, ctypes.byref(ctBytesRead))
                    fps = cam.ls_getfps()
                    if ctBytesRead.value > 0:
                        fps = fps / self.BufSize
                        camBuf_lst = list(npCamBuf) # ctCamBuf is the pointer pointing to npCamBuf!
                        BytesRead = ctBytesRead.value
                        # Qtimer smallest unit is 1 ms. So 0 or a unit < 1 ms is only some delay to measure it.
                        if self.data_refresh.elapsed() > 0.0001:
                            # print('data', type(camBuf_lst[0]), camBuf_lst[0:10], BytesRead, BytesAvailable, fps)
                            self.data_ready.emit([], BytesRead, BytesAvailable, fps)
                            self.mw.data = npCamBuf
                            self.data_refresh.restart()
                        # time.sleep(0.01)

            camRead_and_2D_data = True
            if camRead_and_2D_data:

                # Loop over BufSize lines to create square image matrix.
                # We can change this to other ratios later if this is not suitable.
                for i in range(int(self.BufSize/2)):
                    if self.shouldstop(): break

                    ierr0 = cam.ls_waitforpipe(timeout)

                    getBytesAvailable = 0
                    ierr1 = cam.ls_getpipe(ctCamBuf, getBytesAvailable, ctypes.byref(ctBytesRead))
                    BytesAvailable = ctBytesRead.value

                    if ctBytesRead.value >= self.BufSize:
                        # ctCamBuf is a pointer from npCamBuf. So data are in npCamBuf in the end.
                        ierr2 = cam.ls_getpipe(ctCamBuf, self.BufSize, ctypes.byref(ctBytesRead))
                        fps = cam.ls_getfps()
                        if ctBytesRead.value > 0:
                            fps = fps / self.BufSize
                            BytesRead = ctBytesRead.value
                            # Qtimer smallest unit is 1 ms. So 0 or a unit < 1 ms is only some delay to measure it.
                            # todo: using only half of the BufSize here is not plausible yet. Why would this be like this?
                            np2DImageBuf[i,:int(self.BufSize/2)] = npCamBuf[:int(self.BufSize/2)]
                            self.mw.data = np2DImageBuf
                            self.img_ready.emit( BytesRead, BytesAvailable, int(fps))

    print('PipeThread.run exit ...')

    def shouldstop(self):
        with QMutexLocker( self.stop_mx ):
            return self.stop

    def stopthread(self):
        with QMutexLocker( self.stop_mx):
            self.stop = True


