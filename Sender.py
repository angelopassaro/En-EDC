import os
from multiprocessing import Queue
from socketserver import BaseRequestHandler, TCPServer
from threading import Thread
from Encoder import Encoder


class ServerHandler(BaseRequestHandler):

    def handle(self):
        print("Ricevuta una connessione da: ", self.client_address)

        file = files.get()
        name = file.split('/')[-1]
        self.request.send(name.encode())

        size = os.stat(base_path + name).st_size

        with open(base_path + name, "rb") as fin:
            self.request.send(str(size).encode())  # invio la dimensione del file
            if self.request.recv(1024).decode() == "OK":
                self.request.sendfile(fin)

    def finish(self):
        print("Invio completo")


if __name__ == '__main__':

    encoder = Encoder()

    encoder.set_environment()
    base_path = encoder.base_path + "/compressione/"

    encoder.encode()

    print("Pronto per inviare ...")

    files = Queue()

    for _ in range(3):
        files.put(base_path + "/tmp" + str(_))

    serv = TCPServer(('', 20000), ServerHandler)

    for n in range(2):
        t = Thread(target=serv.serve_forever)
        t.daemon = True
        t.start()

    serv.serve_forever()
