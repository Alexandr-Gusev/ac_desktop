import socket
import select
import hashlib
from threading import Lock, Thread
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pyaudio
import time
from datetime import datetime
import os
from collections import deque


def write_wav_header(f, samples_per_sec, channels, bits_per_sample):
    """
    DWORD rId; //"RIFF" = 0x46464952
    DWORD rLen; //36 + dLen
    DWORD wId; //"WAVE" = 0x45564157
    DWORD fId; //"fmt " = 0x20746D66
    DWORD fLen; //16
    WORD wFormatTag; //1 (WAVE_FORMAT_PCM)
    WORD nChannels;
    DWORD nSamplesPerSec;
    DWORD nAvgBytesPerSec;
    WORD nBlockAlign;
    WORD wBitsPerSample;
    DWORD dId; //"data" = 0x61746164
    DWORD dLen;
    """

    data = (
        int(0x46464952).to_bytes(4, "little") +
        int(36).to_bytes(4, "little") +
        int(0x45564157).to_bytes(4, "little") +
        int(0x20746D66).to_bytes(4, "little") +
        int(16).to_bytes(4, "little") +
        int(1).to_bytes(2, "little") +
        int(channels).to_bytes(2, "little") +
        int(samples_per_sec).to_bytes(4, "little") +
        int(samples_per_sec * channels * bits_per_sample / 8).to_bytes(4, "little") +
        int(channels * bits_per_sample / 8).to_bytes(2, "little") +
        int(bits_per_sample).to_bytes(2, "little") +
        int(0x61746164).to_bytes(4, "little") +
        int(0).to_bytes(4, "little")
    )

    f.write(data)


def fix_wav_header(f, recorded):
    f.seek(4)
    f.write(int(36 + recorded).to_bytes(4, "little"))

    f.seek(40)
    f.write(int(recorded).to_bytes(4, "little"))


def send_play_cmd(s, password, samples_per_sec, bits_per_sample):
    p = hashlib.md5(password.encode("utf-8")).hexdigest().encode("utf-8")
    data = (
        int(3).to_bytes(1, "little") +
        len(p).to_bytes(4, "little") +
        p +
        int(samples_per_sec).to_bytes(4, "little") +
        int(bits_per_sample).to_bytes(4, "little")
    )
    s.send(data)
    data = s.recv(1)
    if data != b"\x01":
        raise RuntimeError("send_play_cmd: unexpected response: %s" % data)


class AcPlayer:
    def __init__(self):
        if not os.path.exists("data"):
            os.mkdir("data")

        self.__s = None
        self.__thread = None
        self.__received = 0

        self.__out_mutex = Lock()
        self.__out = None

        self.__f_mutex = Lock()
        self.__f = None
        self.__recorded = 0

        self.__f_volume_mutex = Lock()
        self.__f_volume = None
        self.__recorded_volume_samples = 0

        self.__max_amplitude = 0
        self.__count_of_amplitudes = 0
        self.__volume = 0

        self.buffer_mutex = Lock()
        self.buffer_size = 0
        self.values = []
        self.volumes = []

        self.on_change = None

    def connected(self):
        return self.__s is not None

    def playing(self):
        return self.__out is not None

    def recording(self):
        return self.__f is not None

    def recording_volume(self):
        return self.__f_volume is not None

    def received(self):
        return self.__received

    def recorded(self):
        return self.__recorded

    def recorded_volume_samples(self):
        return self.__recorded_volume_samples

    def volume(self):
        return self.__volume

    def connect(
        self,
        address, port, package_size, timeout, password,
        samples_per_sec, bits_per_sample, volume_T, volume_K,
        viewport_size
    ):
        self.__package_size = package_size
        self.__timeout = timeout
        self.__samples_per_sec = samples_per_sec
        self.__bits_per_sample = bits_per_sample
        self.__volume_N = int(samples_per_sec * volume_T / 100)
        self.__volume_K = volume_K

        self.__received = 0
        self.__recorded = 0
        self.__recorded_volume_samples = 0
        self.__max_amplitude = 0
        self.__count_of_amplitudes = 0
        self.__volume = 0

        with self.buffer_mutex:
            self.buffer_size = int(viewport_size * samples_per_sec / 1000)
            self.values = deque([0 for _ in range(self.buffer_size)], maxlen=self.buffer_size)
            self.volumes = deque([0 for _ in range(self.buffer_size)], maxlen=self.buffer_size)

        try:
            self.__s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.on_change and self.on_change()
            self.__s.settimeout(timeout / 1000)
            self.__s.connect((address, port))
            send_play_cmd(self.__s, password, samples_per_sec, bits_per_sample)
        except:
            try:
                self.__s.close()
            except:
                pass
            self.__s = None
            self.on_change and self.on_change()
            raise

        self.__thread = Thread(target=self.__target)
        self.__thread.start()

    def disconnect(self):
        try:
            self.__s.close()
        except:
            pass
        self.__thread.join()
        self.__s = None
        self.on_change and self.on_change()

    def start_play(self):
        with self.__out_mutex:
            try:
                self.__out = pyaudio.PyAudio().open(
                    format=pyaudio.paInt8 if self.__bits_per_sample == 8 else pyaudio.paInt16,
                    channels=1,
                    rate=self.__samples_per_sec,
                    output=True
                )
                self.on_change and self.on_change()
            except:
                self.__out = None
                self.on_change and self.on_change()
                raise

    def stop_play(self):
        with self.__out_mutex:
            if self.__out is not None:
                try:
                    self.__out.close()
                    self.__out = None
                    self.on_change and self.on_change()
                except:
                    self.__out = None
                    self.on_change and self.on_change()
                    raise

    def start_record(self):
        with self.__f_mutex:
            try:
                self.__recorded = 0
                self.__f = open(time.strftime("data/%Y-%m-%d %H-%M-%S.wav"), "w+b")
                self.on_change and self.on_change()
                write_wav_header(self.__f, self.__samples_per_sec, 1, self.__bits_per_sample)
            except:
                try:
                    self.__f.close()
                except:
                    pass
                self.__f = None
                self.on_change and self.on_change()
                raise

    def stop_record(self):
        with self.__f_mutex:
            if self.__f is not None:
                try:
                    fix_wav_header(self.__f, self.__recorded)
                    self.__f.close()
                    self.__f = None
                    self.on_change and self.on_change()
                except:
                    try:
                        self.__f.close()
                    except:
                        pass
                    self.__f = None
                    self.on_change and self.on_change()
                    raise

    def start_record_volume(self):
        with self.__f_volume_mutex:
            try:
                self.__recorded_volume_samples = 0
                self.__f_volume = open(time.strftime("data/%Y-%m-%d %H-%M-%S.txt"), "w")
                self.on_change and self.on_change()
            except:
                try:
                    self.__f_volume.close()
                except:
                    pass
                self.__f_volume = None
                self.on_change and self.on_change()
                raise

    def stop_record_volume(self):
        with self.__f_volume_mutex:
            if self.__f_volume is not None:
                try:
                    self.__f_volume.close()
                    self.__f_volume = None
                    self.on_change and self.on_change()
                except:
                    try:
                        self.__f_volume.close()
                    except:
                        pass
                    self.__f_volume = None
                    self.on_change and self.on_change()
                    raise

    def __target(self):
        try:
            timeout = self.__timeout / 1000
            bytes_per_sample = int(self.__bits_per_sample / 8)
            rem = b""
            while True:
                sockets = [self.__s]
                rlist, _, xlist = select.select(sockets, [], sockets, timeout)
                if xlist:
                    break
                if rlist:
                    data = rem + self.__s.recv(self.__package_size)

                    n = len(data)
                    if n == 0:
                        break

                    if n % 2 == 1:
                        rem = data[-1:]
                        data = data[:-1]
                        n -= 1
                    else:
                        rem = b""

                    self.__received += n

                    with self.__out_mutex:
                        if self.__out is not None:
                            try:
                                self.__out.write(data)
                            except Exception as e:
                                print("AcPlayer.__target: player error: %s" % e)
                                try:
                                    self.__out.close()
                                except:
                                    pass
                                self.__out = None
                                self.on_change and self.on_change()

                    with self.__f_mutex:
                        if self.__f is not None:
                            try:
                                self.__f.write(data)
                                self.__recorded += n
                            except Exception as e:
                                print("AcPlayer.__target: recorder error: %s" % e)
                                try:
                                    self.__f.close()
                                except:
                                    pass
                                self.__f = None
                                self.on_change and self.on_change()

                    with self.buffer_mutex:
                        i = 0
                        while i < n:
                            value = int.from_bytes(data[i:i + bytes_per_sample], "little", signed=True)
                            self.values.append(value)

                            amplitude = abs(value)
                            if amplitude > self.__max_amplitude:
                                self.__max_amplitude = amplitude
                            self.__count_of_amplitudes += 1
                            if self.__count_of_amplitudes >= self.__volume_N:
                                self.__volume += (self.__max_amplitude - self.__volume) * self.__volume_K
                                with self.__f_volume_mutex:
                                    if self.__f_volume is not None:
                                        try:
                                            self.__f_volume.write("{}\t{:.2f}\n".format(datetime.now().strftime("%Y.%m.%d %H:%M:%S.%f"), self.__volume))
                                            self.__recorded_volume_samples += 1
                                        except Exception as e:
                                            print("AcPlayer.__target: volume recorder error: %s" % e)
                                            try:
                                                self.__f_volume.close()
                                            except:
                                                pass
                                            self.__f_volume = None
                                            self.on_change and self.on_change()
                                self.__max_amplitude = 0
                                self.__count_of_amplitudes = 0
                            self.volumes.append(self.__volume)

                            i += bytes_per_sample
        except Exception as e:
            print("AcPlayer.__target: %s" % e)
        try:
            self.__s.close()
        except:
            pass
        self.__s = None
        self.on_change and self.on_change()
        self.stop_play()
        self.stop_record()
        self.stop_record_volume()


if __name__ == "__main__":
    start_play = True
    start_record = True
    start_record_volume = True
    start_draw = True

    address = "127.0.0.1"
    port = 9000
    package_size = 4096
    timeout = 5000
    password = "0000"

    samples_per_sec = 44100
    bits_per_sample = 16
    volume_T = 10
    volume_K = 0.1

    viewport_size = 20000

    viewport_interval = 200

    ac_player = AcPlayer()
    ac_player.connect(
        address,
        port,
        package_size,
        timeout,
        password,

        samples_per_sec,
        bits_per_sample,
        volume_T,
        volume_K,

        viewport_size
    )

    if start_play:
        ac_player.start_play()

    if start_record:
        ac_player.start_record()

    if start_record_volume:
        ac_player.start_record_volume()

    if start_draw:
        fig, ax = plt.subplots()

        ax.set_xlim([0, viewport_size])
        amplitude = 128 if bits_per_sample == 8 else 32768
        ax.set_ylim([-amplitude, amplitude])

        with ac_player.buffer_mutex:
            t = [int(i / ac_player.buffer_size * viewport_size) for i in range(ac_player.buffer_size)]
            line1 = ax.plot(t, ac_player.values)[0]
            line2 = ax.plot(t, ac_player.volumes)[0]

        def animate(_):
            if not ac_player.connected():
                plt.close(fig)
                return []
            with ac_player.buffer_mutex:
                line1.set_ydata(ac_player.values)
                line2.set_ydata(ac_player.volumes)
            return [line1, line2]

        an = animation.FuncAnimation(
            fig, animate,
            interval=viewport_interval,
            cache_frame_data=False,
            blit=True
        )

        ax.grid(True)
        plt.show()
        ac_player.disconnect()
    else:
        def cmd_target():
            while True:
                cmd = input("Enter exit to exit: ")
                if cmd == "exit":
                    ac_player.disconnect()
                    break

        cmd_thread = Thread(target=cmd_target)
        cmd_thread.start()
        cmd_thread.join()
