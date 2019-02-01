import concurrent.futures
import lzma
import os
import subprocess
from binascii import unhexlify
from multiprocessing import Process
from shutil import copy
from struct import pack
from sys import byteorder


class Encoder:

    def __init__(self):
        self.BASE_PATH = ""

        self.__original = ""
        self.__base = ""
        self.__delta = ""

        self.__img = ['jpg', 'png']
        self.__video = ['mp4']
        self.__resolution = ['352x240', '640x360', '800x480']
        self.__audio = ['aac', 'flac', 'mp3']
        self.__quality = 0

    def set_environment(self):

        # Prendo in input la path col file da inviare
        file = input("Inserire la path del file da inviare:")

        # Controllo se la path esiste e se il file indicato è un file
        if not os.path.exists(file) or not os.path.isfile(file):
            print("Path o file non esistente")
            exit(0)

        path = "/".join(file.split('/')[:-1])
        name, extension = file.split(".")

        # Creo la directory principale e copio il file indicato all'interno
        self.base_path = path + "/main/"
        self.__original = "{0}/main/originale.{1}".format(path, extension)
        try:
            os.mkdir(self.base_path)
        except FileExistsError:
            print("Cartella già esistente. Eliminare {0}".format(self.base_path))
            exit(0)

        copy(file, self.__original)

        os.mkdir(self.base_path + "compressione")
        os.mkdir(self.base_path + "compressione" + "/file")
        os.mkdir(self.base_path + "compressione" + "/enhancement")

        if extension in self.__video:
            print("Scegli la risoluzione:")
            for c, n in enumerate(self.__resolution):
                print("{0}. {1}.".format(c, n))

            quality = int(input("Scrivi il numero:"))

            if quality > len(self.__resolution):
                exit()

            self.__base = self.__original.split('.')[0] + self.__resolution[quality].split("x")[1] + "p." + extension

            subprocess.run(['ffmpeg', '-i', self.__original, '-s', self.__resolution[quality], self.__base])

            print("convertito")

        elif extension in self.__img:
            self.__base = self.__original.split('.')[0] + "low." + extension
            subprocess.run(['ffmpeg', '-i', self.__original, '-q:v', '30', self.__base])

        elif extension in self.__audio:
            self.__base = self.__original.split('.')[0] + "low." + extension
            subprocess.run(
                ['ffmpeg', '-i', self.__original, '-vcodec', 'copy', '-acodec', extension, '-ab', '32k', self.__base])
        else:
            print("Formato {0} non supportato".format(extension))
            exit()

    """
    Crea il layer di enhancement
    """

    def __compute_delta(self):

        original_len = os.stat(self.__original).st_size
        low_len = os.stat(self.__base).st_size

        self.__delta = self.base_path + "enhancement"

        with open(self.__original, "rb") as original, open(self.__base, "rb") as low, open(
                self.__delta, "wb") as delta:
            for x in range(original_len):
                l = low.read(1)
                o = original.read(1)

                if x > low_len:
                    delta.write(o)
                else:
                    result = int.from_bytes(o, byteorder=byteorder) - int.from_bytes(l, byteorder=byteorder)
                    delta.write(pack('h', result))

    """
    splita la sorgente in tre parti da poter inviare ai compressori
    """

    @staticmethod
    def __splitter(path_file):
        with open(path_file, "rb") as f:
            length = os.stat(path_file).st_size // 3
            return [f.read(length) for _ in range(3)]

    """
    Invia i messaggi da comprimere ai compressori
    """

    def __split_encoder(self, path_file, data):
        processes = [(Process(target=self.__encoder, args=(c, message, path_file,))) for c, message in enumerate(data)]
        [x.start() for x in processes]
        [x.join() for x in processes]

    """
    Controlla se il file è un multiplo di 3 altrimenti aggiunge un padding 0
    """

    @staticmethod
    def __padding_file(path_file):
        size_file = os.stat(path_file).st_size
        rest = size_file % 3
        if rest == 0:
            print("no padding\n")
        elif rest % 3 != 0:
            print("padding\n")
            padding = 3 - rest
            with open(path_file, "ab") as f:
                f.write(bytearray(int('0x00', 16) for _ in range(padding)))

    """
    Comprime il file 
    """

    @staticmethod
    def __encoder(number, message, path_file):

        out_file = (path_file + '{0}{1}' + '{2}').format('/part', number, '.xz')

        with open(out_file, "wb") as f:
            f.write(lzma.compress(bytes(message)))

    """
    Calcolo errore quadratico medio
    """

    def __mse(self, *data):
        if len(data) > 2:
            exit()

        error = []

        with concurrent.futures.ThreadPoolExecutor(3) as executor:
            errors = {executor.submit(self.__compute_mse, base, enhancement) for base, enhancement in zip(*data)}
            concurrent.futures.wait(errors)
            for future in concurrent.futures.as_completed(errors):
                error.append(future.result())

        return sum(error) // 3

    @staticmethod
    def __compute_mse(base, enhancement):
        return (int.from_bytes(base, byteorder=byteorder) - int.from_bytes(enhancement, byteorder=byteorder)) ** 2

    @staticmethod
    def __take_part(x):
        return x[:-3]

    """  
    Divide il rumore in due parti ,da inserire nei primi due messaggi, e calcola l'xor, da inserire nel terzo 
    """

    @staticmethod
    def __enhancement_layer(error):

        error = error.to_bytes(error.bit_length(), byteorder=byteorder)

        length = len(error)
        n = 0

        for x in reversed(error):
            if x != 0:
                break
            else:
                n += 1

        length = length - n

        if length % 2 == 0:
            first, second = error[0:length // 2], error[length // 2:length]
        else:
            first, second = error[0:(length // 2) + 1], error[(length // 2):length]

        third = bytes([c1 ^ c2 for c1, c2 in zip(unhexlify(first.hex()), unhexlify(second.hex()))])

        return first, second, third

    def __create_pack(self, enhancement, *files):

        processes = [(Process(target=self.__packer, args=(file, delta, error, c))) for c, (file, delta, error) in
                     enumerate(zip(sorted(files[0], key=self.__take_part), sorted(files[1], key=self.__take_part),
                                   enhancement))]
        [x.start() for x in processes]
        [x.join() for x in processes]

        # Elimina i file compressi
        print("Eliminazione file .xz")

        [os.remove(self.base_path + "compressione/" + file) for file in
         os.listdir(self.base_path + "compressione/") if file.endswith('xz')]

    def __packer(self, file, delta, error, c):
        error = lzma.compress(bytes(error)) if type(error) is bytes else exit()

        with open(self.base_path + "compressione/{0}{1}".format("tmp", c), "ab") as outfile, open(
                self.base_path + "compressione/file/" + file,
                "rb") as infile, open(self.base_path + "compressione/enhancement/" + delta, "rb") as indelta:
            length = os.stat(infile.name).st_size

            # Creo l'header
            outfile.write(hex(length).encode())
            outfile.write("#".encode())
            outfile.write(hex(len(error)).encode())
            outfile.write("#".encode())

            outfile.write(error)
            # Scrivo il layer base
            outfile.write(infile.read())
            # Scrivo il layer enhancement
            outfile.write(indelta.read())

    def encode(self):

        self.__padding_file(self.__base)
        self.__compute_delta()

        self.__padding_file(self.__delta)

        base = self.__splitter(self.__base)
        self.__split_encoder(self.base_path + "compressione/file", base)

        delta = self.__splitter(self.__delta)
        self.__split_encoder(self.base_path + "compressione/enhancement", delta)

        base_files = os.listdir(self.base_path + "compressione/file")
        enhancement_files = os.listdir(self.base_path + "compressione/enhancement")

        error = self.__mse(base, delta)

        enhancement = self.__enhancement_layer(error)

        self.__create_pack(enhancement, base_files, enhancement_files)

    @property
    def base_path(self):
        return self.BASE_PATH

    @base_path.setter
    def base_path(self, path):
        self.BASE_PATH = path
