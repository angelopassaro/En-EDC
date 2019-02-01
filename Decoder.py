import concurrent.futures
import lzma
import os
from binascii import unhexlify
from struct import unpack
from sys import byteorder


class Decoder:
    def __init__(self, path):
        self.BASE_PATH = path + "/"
        self.__errors = []

        self.__base_stream = []
        self.__enhancement_stream = []

    @property
    def base_path(self):
        return self.BASE_PATH

    def __decoder(self):

        with open(self.base_path + "base", "wb") as base, \
                open(self.base_path + "enhancement", "wb") as enhancement:

            for _ in range(3):
                file = self.base_path + "tmp{}".format(_)

                print(file)
                f = open(file, "rb")

                second = False
                length_base = ""
                length_error = ""

                for x in range(os.stat(f.name).st_size):

                    s = f.read(1)
                    if not second:
                        if s.decode() == '#':
                            length_base = int(length_base, 16)
                            second = True
                        else:
                            length_base += s.decode()
                    else:
                        if s.decode() == '#':
                            length_error = int(length_error, 16)
                            break
                        else:
                            length_error += s.decode()

                self.__errors.append(lzma.decompress(f.read(length_error)))
                self.__base_stream.append(lzma.decompress(f.read(length_base)))
                self.__enhancement_stream.append(lzma.decompress(f.read()))

                base.write(self.__base_stream[len(self.__base_stream) - 1])
                enhancement.write(self.__enhancement_stream[len(self.__enhancement_stream) - 1])

                f.close()

    def __enhancement(self):

        with open(self.base_path + "enhancement", "rb") as delta, open(
                self.base_path + "base", "rb") as low, open(self.base_path + 'lastresult', "wb") as out:

            delta_len = os.stat(delta.name).st_size
            low_len = os.stat(low.name).st_size

            for x in range(delta_len):
                d = delta.read(2)
                l = low.read(1)

                if x > low_len:
                    out.write(d)
                else:
                    result = int.from_bytes(l, byteorder=byteorder) + unpack('h', d)[0]
                    out.write(bytes([result]))

    def __mse(self, *data):

        error = []

        with concurrent.futures.ThreadPoolExecutor(3) as executor:
            errors = {executor.submit(self.__compute_mse, base, enhancement) for base, enhancement in zip(*data)}
            concurrent.futures.wait(errors)
            for future in concurrent.futures.as_completed(errors):
                error.append(future.result())

        return sum(error) // 3

    @staticmethod
    def __compute_mse(base, enhancement):
        error = (int.from_bytes(base, byteorder=byteorder) - int.from_bytes(enhancement, byteorder=byteorder)) ** 2
        return error

    def __check_error(self, error):

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

        if third == self.__errors[2]:
            print("Nessuna modifica. Miglioramento del file")
            self.__enhancement()
        else:
            print("File modificato durante il trasferimento nessun miglioramento")

        [os.remove(self.base_path + file) for file in os.listdir(self.base_path) if
         file != 'base' and file != 'lastresult']

    def decode(self):
        self.__decoder()
        error = self.__mse(self.__base_stream, self.__enhancement_stream)
        self.__check_error(error)
