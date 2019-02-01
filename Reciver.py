import concurrent.futures
import os
from socket import socket, AF_INET, SOCK_STREAM, SHUT_RDWR, MSG_WAITALL

from Decoder import Decoder


def reciver_file(th):
    s = socket(AF_INET, SOCK_STREAM)
    s.connect(('localhost', 20000))     # Se su una macchina diversa dal sender sostituire localhost con l'ip

    name = s.recv(1024).decode()

    with open(base_path + "/{0}".format(name),
              "wb") as f:
        print("Client {0}: attendo ...".format(th))

        buff = int(s.recv(1024).decode())  # size file
        s.send("OK".encode())
        f.write(s.recv(buff, MSG_WAITALL))

        print("Decoder {0}: File ricevuto. Chiusura connessione.".format(th))
        s.shutdown(SHUT_RDWR)
        s.close()


if __name__ == '__main__':

    DEBUG = 0   # Settare a 1 se si vuole alterare lo stream

    path = input("Inserire la path dove salvare il file:")

    if not os.path.exists("/".join(path.split("/")[:-1])):
        print("Path non valida")
        exit()

    if not os.path.exists(path):
        os.mkdir(path)

    decoder = Decoder(path)

    base_path = decoder.base_path

    with concurrent.futures.ThreadPoolExecutor(3) as executor:
        clients = {executor.submit(reciver_file, _) for _ in range(3)}
        concurrent.futures.wait(clients)

    if DEBUG:
        import lzma

        error = ""
        length_base = ""
        length_read = 0

        with open(base_path + "/tmp0", "rb") as test, open(base_path + "/edit0", "wb") as tmp:

            second = False
            length_error = ""

            for x in range(os.stat(test.name).st_size):

                s = test.read(1)
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

            error = test.read(length_error)
            length_read = tmp.write(lzma.decompress(test.read(length_base)))
            tmp.write(lzma.decompress(test.read()))

        os.remove(base_path + "/tmp0")

        input("Modifica il file edit0 in {0}".format(base_path))

        with open(base_path + "/edit0", "rb") as tmp, open(base_path + "/tmp0", "wb") as test:
            test.write(hex(length_base).encode())
            test.write("#".encode())
            test.write(hex(length_error).encode())
            test.write("#".encode())

            test.write(error)
            test.write(lzma.compress(tmp.read(length_read)))
            test.write(lzma.compress(tmp.read()))

        os.remove(base_path + "/edit0")

    print("Ricostruzione file")
    decoder.decode()
    print("Ricostruzione completata.")
