from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from main_window_ui import Ui_MainWindow
from matplotlib.backends.backend_qtagg import FigureCanvas
from matplotlib.figure import Figure
from core import AcPlayer


class Signaller(QObject):
    signal = Signal()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.__stat_timer = QTimer()
        self.__stat_timer.setInterval(250)
        self.__stat_timer.timeout.connect(self.__update_stat)
        self.__stat_timer.start()

        self.__signaller = Signaller()
        self.__signaller.signal.connect(self.__update_ui)

        self.__ac_player = AcPlayer()
        self.__ac_player.on_change = lambda: self.__signaller.signal.emit()

        self.ui.connect.clicked.connect(self.connect_clicked)
        self.ui.startPlay.clicked.connect(self.startPlay_clicked)
        self.ui.startRecord.clicked.connect(self.startRecord_clicked)
        self.ui.startRecordVolume.clicked.connect(self.startRecordVolume_clicked)
        self.ui.startDraw.clicked.connect(self.startDraw_clicked)

        for i in range(self.ui.samplesPerSec.count()):
            self.ui.samplesPerSec.setItemData(i, int(self.ui.samplesPerSec.itemText(i)), Qt.UserRole)

        for i in range(self.ui.bitsPerSample.count()):
            self.ui.bitsPerSample.setItemData(i, int(self.ui.bitsPerSample.itemText(i)), Qt.UserRole)

        self.__canvas = FigureCanvas(Figure())
        self.ui.verticalLayout.addWidget(self.__canvas)
        self.__ax = self.__canvas.figure.subplots()
        self.__ax.grid(True)
        self.__line1 = self.__ax.plot([], [])[0]
        self.__line2 = self.__ax.plot([], [])[0]
        self.__timer = self.__canvas.new_timer()
        self.__timer.add_callback(self.__update_canvas)
        self.__timer.interval = 0

        self.__init_graph()

        self.__update_ui()

    def __update_canvas(self):
        with self.__ac_player.buffer_mutex:
            self.__line1.set_ydata(self.__ac_player.values)
            self.__line2.set_ydata(self.__ac_player.volumes)
        self.__canvas.draw()

    def __update_ui(self):
        self.ui.address.setEnabled(not self.__ac_player.connected())
        self.ui.port.setEnabled(not self.__ac_player.connected())
        self.ui.packageSize.setEnabled(not self.__ac_player.connected())
        self.ui.timeout.setEnabled(not self.__ac_player.connected())
        self.ui.password.setEnabled(not self.__ac_player.connected())
        self.ui.samplesPerSec.setEnabled(not self.__ac_player.connected())
        self.ui.bitsPerSample.setEnabled(not self.__ac_player.connected())
        self.ui.volumeT.setEnabled(not self.__ac_player.connected())
        self.ui.volumeK.setEnabled(not self.__ac_player.connected())
        self.ui.viewportSize.setEnabled(not self.__ac_player.connected())
        self.ui.viewportUpdateInterval.setEnabled(not self.__ac_player.connected())

        self.ui.startPlay.setEnabled(self.__ac_player.connected())
        self.ui.startRecord.setEnabled(self.__ac_player.connected())
        self.ui.startRecordVolume.setEnabled(self.__ac_player.connected())
        self.ui.startDraw.setEnabled(self.__ac_player.connected())

        self.ui.connect.setText("Disconnect" if self.__ac_player.connected() else "Connect")
        self.ui.startPlay.setText("Stop Play" if self.__ac_player.playing() else "Start Play")
        self.ui.startRecord.setText("Stop Record" if self.__ac_player.recording() else "Start Record")
        self.ui.startRecordVolume.setText("Stop Record Volume" if self.__ac_player.recording_volume() else "Start Record Volume")
        self.ui.startDraw.setText("Stop Draw" if self.__timer.interval > 0 else "Start Draw")

    def __init_graph(self):
        self.__ax.set_xlim([0, self.ui.viewportSize.value()])
        amplitude = 128 if self.ui.bitsPerSample.currentData() == 8 else 32768
        self.__ax.set_ylim([-amplitude, amplitude])

        with self.__ac_player.buffer_mutex:
            t = [int(i / self.__ac_player.buffer_size * self.ui.viewportSize.value()) for i in range(self.__ac_player.buffer_size)]
            self.__line1.set_data(t, self.__ac_player.values)
            self.__line2.set_data(t, self.__ac_player.volumes)

    def __update_stat(self):
        self.ui.received.setText(str(self.__ac_player.received()))
        self.ui.recorded.setText(str(self.__ac_player.recorded()))
        self.ui.recordedVolumeSamples.setText(str(self.__ac_player.recorded_volume_samples()))
        amplitude = 128 if self.ui.bitsPerSample.currentData() == 8 else 32768
        volume = self.__ac_player.volume() / amplitude * 100
        self.ui.volumeIndicator.setValue(volume)
        self.ui.volumeValue.setText("{:.2f}% ({})".format(volume, int(self.__ac_player.volume())))

    def connect_clicked(self):
        if not self.__ac_player.connected():
            self.__ac_player.connect(
                self.ui.address.text(),
                self.ui.port.value(),
                self.ui.packageSize.value(),
                self.ui.timeout.value(),
                self.ui.password.text(),

                self.ui.samplesPerSec.currentData(),
                self.ui.bitsPerSample.currentData(),
                self.ui.volumeT.value(),
                self.ui.volumeK.value(),

                self.ui.viewportSize.value()
            )
        else:
            self.__ac_player.disconnect()

    def startPlay_clicked(self):
        if not self.__ac_player.playing():
            self.__ac_player.start_play()
        else:
            self.__ac_player.stop_play()

    def startRecord_clicked(self):
        if not self.__ac_player.recording():
            self.__ac_player.start_record()
        else:
            self.__ac_player.stop_record()

    def startRecordVolume_clicked(self):
        if not self.__ac_player.recording_volume():
            self.__ac_player.start_record_volume()
        else:
            self.__ac_player.stop_record_volume()

    def startDraw_clicked(self):
        if self.__timer.interval == 0:
            self.__timer.interval = self.ui.viewportUpdateInterval.value()
            self.__init_graph()
            self.__timer.start()
        else:
            self.__timer.stop()
            self.__timer.interval = 0
        self.__update_ui()
